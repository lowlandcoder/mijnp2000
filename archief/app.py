#!/usr/bin/env python3
"""Archief voor P2000-meldingen.

Deze backend doet drie dingen tegelijk:
  1. Meelezen op het MQTT-onderwerp waar de ontvanger op publiceert en elke
     melding opslaan in een SQLite-database.
  2. Capcodes vertalen naar regio en discipline met een capcode-bestand.
  3. De pagina en een JSON-API aanbieden waarmee de meldingen te bekijken zijn,
     met filter op regio en een instelbare periode.

Oude meldingen worden automatisch opgeschoond na de bewaartermijn.

Instellingen komen uit omgevingsvariabelen (in te vullen in docker-compose):
  MQTT_HOST, MQTT_PORT, MQTT_TOPIC, MQTT_USER, MQTT_PASSWORD  broker
  RETENTIE_DAGEN   bewaartermijn in dagen           (standaard 7)
  DATA_DIR         map voor database en capcodes     (standaard /app/data)
  POORT            poort waarop de pagina draait     (standaard 8000)
"""

import csv
import json
import os
import sqlite3
import threading
import time
from datetime import datetime, timedelta, timezone

import paho.mqtt.client as mqtt
from flask import Flask, jsonify, request, send_from_directory
from waitress import serve

DATA_DIR = os.environ.get("DATA_DIR", "/app/data")
DB_PATH = os.path.join(DATA_DIR, "p2000.db")
CAPCODES_PATH = os.path.join(DATA_DIR, "capcodes.csv")
RETENTIE_DAGEN = int(os.environ.get("RETENTIE_DAGEN", "7"))
POORT = int(os.environ.get("POORT", "8000"))

MQTT_HOST = os.environ.get("MQTT_HOST", "")
MQTT_PORT = int(os.environ.get("MQTT_PORT", "1883"))
MQTT_TOPIC = os.environ.get("MQTT_TOPIC", "p2000/bericht")
MQTT_USER = os.environ.get("MQTT_USER", "")
MQTT_PASSWORD = os.environ.get("MQTT_PASSWORD", "")

db_lock = threading.Lock()
capcodes_map = {}  # capcode -> {"regio", "discipline", "plaats"}


# --- Database --------------------------------------------------------------
def get_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with db_lock:
        conn = get_db()
        conn.execute(
            """CREATE TABLE IF NOT EXISTS meldingen (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ontvangen TEXT NOT NULL,
                tijd_flex TEXT,
                capcodes TEXT,
                soort TEXT,
                bericht TEXT,
                regios TEXT,
                disciplines TEXT
            )"""
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ontvangen ON meldingen(ontvangen)")
        conn.execute("PRAGMA journal_mode=WAL")
        conn.commit()
        conn.close()


# --- Capcodes vertalen naar regio en discipline ----------------------------
def laad_capcodes():
    """Leest capcodes.csv met kolommen: capcode, regio, discipline, plaats."""
    global capcodes_map
    nieuw = {}
    if os.path.exists(CAPCODES_PATH):
        with open(CAPCODES_PATH, newline="", encoding="utf-8") as bestand:
            for rij in csv.DictReader(bestand):
                code = (rij.get("capcode") or "").strip()
                if not code or code.startswith("#"):
                    continue
                nieuw[code] = {
                    "regio": (rij.get("regio") or "").strip(),
                    "discipline": (rij.get("discipline") or "").strip(),
                    "plaats": (rij.get("plaats") or "").strip(),
                }
    capcodes_map = nieuw


def vertaal(capcodes):
    regios, disciplines = set(), set()
    for code in capcodes:
        info = capcodes_map.get(code)
        if info:
            if info["regio"]:
                regios.add(info["regio"])
            if info["discipline"]:
                disciplines.add(info["discipline"])
    return sorted(regios), sorted(disciplines)


def bewaar(melding):
    capcodes = melding.get("capcodes", []) or []
    regios, disciplines = vertaal(capcodes)
    with db_lock:
        conn = get_db()
        conn.execute(
            "INSERT INTO meldingen (ontvangen, tijd_flex, capcodes, soort, bericht, regios, disciplines)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                melding.get("ontvangen"),
                melding.get("tijd_flex"),
                " ".join(capcodes),
                melding.get("soort"),
                melding.get("bericht"),
                ", ".join(regios),
                ", ".join(disciplines),
            ),
        )
        conn.commit()
        conn.close()


# --- MQTT meelezen ---------------------------------------------------------
def on_connect(client, userdata, flags, rc):
    client.subscribe(MQTT_TOPIC, qos=1)
    print(f"Verbonden met broker, meeleest op '{MQTT_TOPIC}'.", flush=True)


def on_message(client, userdata, msg):
    try:
        bewaar(json.loads(msg.payload.decode("utf-8")))
    except Exception as fout:
        print("Fout bij verwerken van een melding:", fout, flush=True)


def mqtt_lus():
    client = mqtt.Client(client_id="p2000-archief")
    if MQTT_USER:
        client.username_pw_set(MQTT_USER, MQTT_PASSWORD)
    client.on_connect = on_connect
    client.on_message = on_message
    while True:
        try:
            client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
            client.loop_forever()
        except Exception as fout:
            print("MQTT-verbinding mislukt, opnieuw over 5s:", fout, flush=True)
            time.sleep(5)


# --- Opschonen na de bewaartermijn -----------------------------------------
def opschoon_lus():
    while True:
        grens = (datetime.now(timezone.utc) - timedelta(days=RETENTIE_DAGEN)).isoformat()
        with db_lock:
            conn = get_db()
            conn.execute("DELETE FROM meldingen WHERE ontvangen < ?", (grens,))
            conn.commit()
            conn.close()
        time.sleep(3600)


# --- Webpagina en API ------------------------------------------------------
app = Flask(__name__, static_folder="static", static_url_path="")


@app.route("/")
def index():
    return send_from_directory("static", "index.html")


@app.route("/api/regios")
def api_regios():
    with db_lock:
        conn = get_db()
        rijen = conn.execute("SELECT DISTINCT regios FROM meldingen WHERE regios != ''").fetchall()
        conn.close()
    regios = set()
    for rij in rijen:
        for deel in rij["regios"].split(","):
            deel = deel.strip()
            if deel:
                regios.add(deel)
    return jsonify(sorted(regios))


@app.route("/api/meldingen")
def api_meldingen():
    regio = request.args.get("regio", "").strip()
    uren = request.args.get("uren", "").strip()
    zoek = request.args.get("zoek", "").strip()
    try:
        limiet = min(int(request.args.get("limiet", "500")), 2000)
    except ValueError:
        limiet = 500

    voorwaarden, params = [], []
    if uren:
        try:
            grens = (datetime.now(timezone.utc) - timedelta(hours=float(uren))).isoformat()
            voorwaarden.append("ontvangen >= ?")
            params.append(grens)
        except ValueError:
            pass
    if regio:
        voorwaarden.append("regios LIKE ?")
        params.append(f"%{regio}%")
    if zoek:
        voorwaarden.append("bericht LIKE ?")
        params.append(f"%{zoek}%")

    where = ("WHERE " + " AND ".join(voorwaarden)) if voorwaarden else ""
    query = (
        "SELECT ontvangen, tijd_flex, capcodes, soort, bericht, regios, disciplines"
        f" FROM meldingen {where} ORDER BY ontvangen DESC LIMIT ?"
    )
    params.append(limiet)
    with db_lock:
        conn = get_db()
        rijen = conn.execute(query, params).fetchall()
        conn.close()
    return jsonify([dict(rij) for rij in rijen])


def main():
    if not MQTT_HOST:
        print("MQTT_HOST is niet ingesteld; stoppen.", flush=True)
        return
    init_db()
    laad_capcodes()
    threading.Thread(target=mqtt_lus, daemon=True).start()
    threading.Thread(target=opschoon_lus, daemon=True).start()
    print(
        f"Archief gestart. Capcodes geladen: {len(capcodes_map)}. "
        f"Bewaartermijn: {RETENTIE_DAGEN} dagen. Pagina op poort {POORT}.",
        flush=True,
    )
    serve(app, host="0.0.0.0", port=POORT)


if __name__ == "__main__":
    main()
