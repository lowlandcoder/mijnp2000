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
  DATA_DIR         map voor de capcodes              (standaard /app/data)
  DB_DIR           map voor de database              (standaard DATA_DIR)
  POORT            poort waarop de pagina draait     (standaard 8000)

Voor de kaartpagina (/kaart), alle vier mogen leeg blijven:
  KAART_POSTCODE   postcode van het middelpunt       (bijvoorbeeld 2011 AB)
  KAART_LAT        breedtegraad van het middelpunt   (gaat voor op de postcode)
  KAART_LON        lengtegraad van het middelpunt
  KAART_STRAAL_KM  straal van het gebied in km       (standaard 12)
  KAART_MINUTEN    venster in minuten                (standaard 60)
  CARTO_KEY        sleutel voor de basiskaart        (zonder sleutel: watermerk)
"""

import csv
import json
import os
import sqlite3
import threading
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

import paho.mqtt.client as mqtt
from flask import Flask, jsonify, request, send_from_directory
from waitress import serve

DATA_DIR = os.environ.get("DATA_DIR", "/app/data")
DB_DIR = os.environ.get("DB_DIR", DATA_DIR)
DB_PATH = os.path.join(DB_DIR, "p2000.db")
CAPCODES_PATH = os.path.join(DATA_DIR, "capcodes.csv")
RETENTIE_DAGEN = int(os.environ.get("RETENTIE_DAGEN", "7"))
POORT = int(os.environ.get("POORT", "8000"))

MQTT_HOST = os.environ.get("MQTT_HOST", "")
MQTT_PORT = int(os.environ.get("MQTT_PORT", "1883"))
MQTT_TOPIC = os.environ.get("MQTT_TOPIC", "p2000/bericht")
MQTT_USER = os.environ.get("MQTT_USER", "")
MQTT_PASSWORD = os.environ.get("MQTT_PASSWORD", "")

# --- Instellingen voor de kaartpagina -------------------------------------
# Blijft alles leeg, dan blijft de archiefpagina gewoon werken en meldt de
# kaartpagina dat het middelpunt nog ontbreekt.
KAART_POSTCODE = os.environ.get("KAART_POSTCODE", "").strip()
KAART_LAT = os.environ.get("KAART_LAT", "").strip()
KAART_LON = os.environ.get("KAART_LON", "").strip()
KAART_STRAAL_KM = os.environ.get("KAART_STRAAL_KM", "12").strip() or "12"
KAART_MINUTEN = os.environ.get("KAART_MINUTEN", "60").strip() or "60"

# Sleutel voor de basiskaart van CARTO. Gaat via /api/kaartinstellingen naar de
# browser, zodat de sleutel in .env op de server kan blijven staan en niet in de
# repository. Blijft de sleutel leeg, dan werkt de kaart gewoon, alleen ligt er
# een watermerk over de tegels.
CARTO_KEY = os.environ.get("CARTO_KEY", "").strip()

# Hoeveel nieuwe adressen er per verzoek bij PDOK worden opgezocht. De rest
# volgt bij de volgende ronde van de pagina, zodat een verzoek kort blijft en de
# dienst niet in een keer wordt volgelopen.
PDOK_PER_VERZOEK = 25
PDOK_URL = "https://api.pdok.nl/bzk/locatieserver/search/v3_1/free"
PDOK_KOP = {"User-Agent": "mijnp2000-kaart/1.0 (lab023.nl, eigen gebruik)"}

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
        # Opgezochte locaties, zodat hetzelfde adres maar een keer naar PDOK gaat.
        # gevonden = 0 bewaart ook een misser, zodat die niet elke ronde opnieuw
        # wordt opgevraagd.
        conn.execute(
            """CREATE TABLE IF NOT EXISTS locaties (
                zoekterm TEXT PRIMARY KEY,
                soort TEXT,
                lat REAL,
                lon REAL,
                gevonden INTEGER NOT NULL DEFAULT 0,
                naam TEXT,
                tijd TEXT
            )"""
        )
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
                    "omschrijving": (rij.get("omschrijving") or "").strip(),
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


def details_van_capcodes(capcodes_tekst):
    """Zet de opgeslagen capcode-string om naar een lijst met details per code,
    en bepaalt de eerste bekende plaats (voor de kaartverwijzing)."""
    codes = []
    plaats = ""
    for code in (capcodes_tekst or "").split():
        info = capcodes_map.get(code, {})
        if info.get("plaats") and not plaats:
            plaats = info["plaats"]
        codes.append(
            {
                "capcode": code,
                "regio": info.get("regio", ""),
                "discipline": info.get("discipline", ""),
                "plaats": info.get("plaats", ""),
                "omschrijving": info.get("omschrijving", ""),
            }
        )
    return codes, plaats


@app.route("/api/meldingen")
def api_meldingen():
    # Regio's: 'regios' (komma-gescheiden, meerdere) of 'regio' (enkel).
    regios = [r.strip() for r in request.args.get("regios", "").split(",") if r.strip()]
    enkel = request.args.get("regio", "").strip()
    if enkel and enkel not in regios:
        regios.append(enkel)
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
    if regios:
        # OR: een melding hoort bij een van de gekozen regio's.
        deel = " OR ".join("regios LIKE ?" for _ in regios)
        voorwaarden.append(f"({deel})")
        params.extend(f"%{r}%" for r in regios)
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

    uitvoer = []
    for rij in rijen:
        melding = dict(rij)
        melding["codes"], melding["plaats"] = details_van_capcodes(melding.get("capcodes", ""))
        uitvoer.append(melding)
    return jsonify(uitvoer)


# --- Locaties opzoeken bij de PDOK Locatieserver ---------------------------
# De pagina haalt straat en plaats uit de meldingtekst (adres.js) en vraagt hier
# de coordinaten op. Huisnummers gaan niet mee: de pin komt daarmee in de goede
# straat en er gaat zo weinig mogelijk naar buiten. Elke zoekterm wordt een keer
# opgezocht en daarna uit de eigen database gehaald.
PDOK_FILTER = {
    "plaats": "type:woonplaats",
    "weg": "type:(weg OR adres)",
    "postcode": "type:(postcode OR adres)",
}


def _punt_uit_centroide(tekst):
    """Zet 'POINT(4.63 52.38)' om naar (lat, lon)."""
    try:
        binnenin = tekst[tekst.index("(") + 1 : tekst.index(")")]
        lon, lat = binnenin.split()
        return float(lat), float(lon)
    except Exception:
        return None


def pdok_zoek(zoekterm, soort):
    """Vraagt een zoekterm op bij PDOK. Geeft (lat, lon, naam) of None."""
    vraag = urllib.parse.urlencode(
        {
            "q": zoekterm,
            "fq": PDOK_FILTER.get(soort, PDOK_FILTER["weg"]),
            "rows": "1",
            "fl": "weergavenaam,centroide_ll",
        }
    )
    verzoek = urllib.request.Request(f"{PDOK_URL}?{vraag}", headers=PDOK_KOP)
    with urllib.request.urlopen(verzoek, timeout=6) as antwoord:
        gegevens = json.loads(antwoord.read().decode("utf-8"))
    treffers = gegevens.get("response", {}).get("docs", []) or []
    if not treffers:
        return None
    punt = _punt_uit_centroide(treffers[0].get("centroide_ll", "") or "")
    if not punt:
        return None
    return punt[0], punt[1], treffers[0].get("weergavenaam", "")


def locaties_uit_db(termen):
    """Leest de al opgezochte termen uit de database."""
    if not termen:
        return {}
    uit = {}
    with db_lock:
        conn = get_db()
        for stuk in range(0, len(termen), 200):
            deel = termen[stuk : stuk + 200]
            vragen = ",".join("?" for _ in deel)
            rijen = conn.execute(
                f"SELECT zoekterm, lat, lon, gevonden FROM locaties WHERE zoekterm IN ({vragen})",
                deel,
            ).fetchall()
            for rij in rijen:
                uit[rij["zoekterm"]] = (
                    {"lat": rij["lat"], "lon": rij["lon"]} if rij["gevonden"] else None
                )
        conn.close()
    return uit


def bewaar_locatie(zoekterm, soort, uitkomst):
    lat = uitkomst[0] if uitkomst else None
    lon = uitkomst[1] if uitkomst else None
    naam = uitkomst[2] if uitkomst else ""
    with db_lock:
        conn = get_db()
        conn.execute(
            "INSERT OR REPLACE INTO locaties (zoekterm, soort, lat, lon, gevonden, naam, tijd)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                zoekterm,
                soort,
                lat,
                lon,
                1 if uitkomst else 0,
                naam,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        conn.commit()
        conn.close()


def zoek_locatie(zoekterm, soort):
    """Zoekt een term op als die nog niet bekend is en bewaart de uitkomst."""
    bekend = locaties_uit_db([zoekterm])
    if zoekterm in bekend:
        return bekend[zoekterm]
    try:
        uitkomst = pdok_zoek(zoekterm, soort)
    except Exception as fout:
        print(f"PDOK mislukt voor '{zoekterm}':", fout, flush=True)
        return None
    bewaar_locatie(zoekterm, soort, uitkomst)
    return {"lat": uitkomst[0], "lon": uitkomst[1]} if uitkomst else None


def middelpunt():
    """Het middelpunt van het gebied: eerst uit KAART_LAT en KAART_LON, anders
    uit de postcode. Is er geen van beide, dan None."""
    try:
        if KAART_LAT and KAART_LON:
            return {"lat": float(KAART_LAT), "lon": float(KAART_LON)}
    except ValueError:
        print("KAART_LAT of KAART_LON is geen getal; middelpunt overgeslagen.", flush=True)
    if KAART_POSTCODE:
        return zoek_locatie(KAART_POSTCODE.upper(), "postcode")
    return None


@app.route("/kaart")
def kaart():
    return send_from_directory("static", "kaart.html")


@app.route("/api/kaartinstellingen")
def api_kaartinstellingen():
    punt = middelpunt()
    try:
        straal = float(KAART_STRAAL_KM)
    except ValueError:
        straal = 12.0
    try:
        minuten = int(float(KAART_MINUTEN))
    except ValueError:
        minuten = 60
    return jsonify(
        {
            "middelpunt": punt,
            "straal_km": straal,
            "minuten": minuten,
            "basiskaart": {"sleutel": CARTO_KEY},
        }
    )


@app.route("/api/locaties", methods=["POST"])
def api_locaties():
    """Zet zoektermen om naar coordinaten. Verzoek:
         {"termen": [{"zoekterm": "Zijlweg Haarlem", "soort": "weg"}, ...]}
       Antwoord: per zoekterm {"lat":..,"lon":..}, null als er niets is gevonden,
       of de term ontbreekt in het antwoord als hij deze ronde niet meer paste."""
    gegevens = request.get_json(silent=True) or {}
    termen = gegevens.get("termen") or []
    gevraagd = []
    for item in termen[:500]:
        zoekterm = (item.get("zoekterm") or "").strip()
        soort = item.get("soort") if item.get("soort") in PDOK_FILTER else "weg"
        if zoekterm:
            gevraagd.append((zoekterm, soort))

    uit = locaties_uit_db([term for term, _ in gevraagd])
    nieuw = 0
    for zoekterm, soort in gevraagd:
        if zoekterm in uit:
            continue
        if nieuw >= PDOK_PER_VERZOEK:
            break
        uit[zoekterm] = zoek_locatie(zoekterm, soort)
        nieuw += 1
    return jsonify(uit)


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
