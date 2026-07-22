#!/usr/bin/env python3
"""Leest de FLEX-regels van multimon-ng op de standaardinvoer en zet elke
melding als JSON op een MQTT-onderwerp.

Er wordt bewust niets gefilterd en niets verrijkt: de ontvanger publiceert
alle meldingen zo kaal mogelijk. Filteren op regio en het vertalen van
capcodes gebeurt bij de afnemers (Home Assistant en de archiefpagina), zodat
één ontvanger meerdere afnemers kan bedienen.

Instellingen komen uit omgevingsvariabelen (in Portainer in te vullen):
  MQTT_HOST      adres van de bestaande MQTT-broker      (verplicht)
  MQTT_PORT      poort van de broker                     (standaard 1883)
  MQTT_TOPIC     onderwerp om op te publiceren           (standaard p2000/bericht)
  MQTT_USER      gebruikersnaam, leeg = geen aanmelding  (optioneel)
  MQTT_PASSWORD  wachtwoord                              (optioneel)
  MQTT_CLIENT_ID naam van de verbinding                  (standaard p2000-ontvanger)
"""

import json
import os
import sys
import time
from datetime import datetime, timezone

import paho.mqtt.client as mqtt

MQTT_HOST = os.environ.get("MQTT_HOST", "")
MQTT_PORT = int(os.environ.get("MQTT_PORT", "1883"))
MQTT_TOPIC = os.environ.get("MQTT_TOPIC", "p2000/bericht")
MQTT_USER = os.environ.get("MQTT_USER", "")
MQTT_PASSWORD = os.environ.get("MQTT_PASSWORD", "")
MQTT_CLIENT_ID = os.environ.get("MQTT_CLIENT_ID", "p2000-ontvanger")


def maak_verbinding():
    """Maakt verbinding met de broker en houdt die vanzelf in de lucht."""
    if not MQTT_HOST:
        sys.stderr.write("MQTT_HOST is niet ingesteld; stoppen.\n")
        sys.exit(1)

    client = mqtt.Client(client_id=MQTT_CLIENT_ID)
    if MQTT_USER:
        client.username_pw_set(MQTT_USER, MQTT_PASSWORD)
    client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
    client.loop_start()
    return client


def ontleed(regel):
    """Zet één FLEX-regel van multimon-ng om naar een woordenboek.

    Voorbeeldregel:
    FLEX|2021-06-28 16:50:35|1600/2/K/A|12.092|002029568 000126999|ALN|A2 rit ...
    Velden gescheiden door '|': [1] tijd, [4] capcodes (spaties), [5] soort,
    [6] tekst. Niet elke regel is volledig; onvolledige regels worden
    overgeslagen.
    """
    if not regel.startswith("FLEX|"):
        return None
    delen = regel.rstrip("\n").split("|")
    if len(delen) < 7:
        return None

    capcodes = [c for c in delen[4].split() if c]
    tekst = delen[6].strip()
    if not tekst:
        return None

    return {
        "ontvangen": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "tijd_flex": delen[1].strip(),
        "capcodes": capcodes,
        "soort": delen[5].strip(),
        "bericht": tekst,
    }


def main():
    client = maak_verbinding()
    sys.stderr.write(f"Verbonden met {MQTT_HOST}:{MQTT_PORT}, publiceert op '{MQTT_TOPIC}'.\n")

    for regel in sys.stdin:
        melding = ontleed(regel)
        if melding is None:
            continue
        try:
            client.publish(MQTT_TOPIC, json.dumps(melding, ensure_ascii=False), qos=1)
        except Exception as fout:  # verbinding kort weg: doorgaan, paho herstelt zelf
            sys.stderr.write(f"Publiceren mislukt: {fout}\n")
            time.sleep(1)


if __name__ == "__main__":
    main()
