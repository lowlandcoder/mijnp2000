#!/usr/bin/env python3
"""Waakhond van MijnP2000: bewaakt of de verwerking nog loopt.

Draait op server023 als oneshot-dienst, elk kwartier gestart door een
systemd-timer. De ontvanger zelf draait op de sdr-server.

Wat er bewaakt wordt
--------------------
Valt rtl_fm weg, dan krijgt publiceer.py einde-invoer, stopt de container en
start Docker hem vanzelf opnieuw. Dat gaat vanzelf goed. Het geval dat wel
misgaat: de keten leeft, maar multimon-ng decodeert niets meer. De container
heet dan nog steeds "draait" terwijl er niets meer binnenkomt.

De ontvanger zet daarom elke minuut een bewaard bericht op p2000/status met de
tijd van de laatste gedecodeerde melding. Deze waakhond haalt die stand op,
en bij een te lange stilte:

  1. vraagt hij de containerstand aan de bedieningsdienst op de sdr-server;
  2. draait de container, dan vraagt hij een herstart;
  3. meldt hij dat via mail en via Home Assistant.

Draait de container niet, dan gebeurt er niets meer dan melden. Een container
die stilstaat is bewust gestopt, en dat hoort de waakhond niet te doorkruisen.

Remmen
------
Een herstart repareert een vastgelopen stick of proces. Een slecht afgestemde
antenne repareert hij niet. Daarom hoogstens HERSTART_MAX herstarts binnen
HERSTART_VENSTER_UUR; daarna volgt alleen nog een melding, met de tekst dat
herstarten niet helpt. Na een herstart geldt HERSTART_WACHT_MINUTEN rust,
zodat de ontvanger de tijd krijgt om op gang te komen.

Instellingen staan in /etc/mijnp2000/waakhond.env; zie waakhond.env.voorbeeld.
Een kanaal staat aan zodra de instellingen die het nodig heeft gevuld zijn.
Staat geen enkel kanaal aan, dan controleert de waakhond wel en meldt hij niet.

Beproeven
---------
    python3 waakhond.py --stand    alleen kijken en de uitkomst tonen
    python3 waakhond.py --droog    kijken en melden, maar niet herstarten
    python3 waakhond.py --proef    een proefmelding over alle kanalen sturen
"""

import argparse
import datetime as dt
import json
import logging
import os
import smtplib
import sys
import threading
import urllib.error
import urllib.request
from email.mime.text import MIMEText
from email.utils import formataddr
from zoneinfo import ZoneInfo

log = logging.getLogger("mijnp2000.waakhond")

PAGINA = "https://mijnp2000.lab023.nl"
TZ = ZoneInfo("Europe/Amsterdam")


# ── Instellingen ────────────────────────────────────────────────────────────

def instellingen() -> dict:
    naar = [a.strip() for a in os.environ.get("ALERT_NAAR", "").split(",")
            if a.strip()]
    return {
        # De broker met de hartslag
        "mqtt_host": os.environ.get("MQTT_HOST", "192.168.2.38"),
        "mqtt_port": int(os.environ.get("MQTT_PORT", "1883")),
        "mqtt_user": os.environ.get("MQTT_USER", "p2000"),
        "mqtt_wachtwoord": os.environ.get("MQTT_PASSWORD", ""),
        "status_topic": os.environ.get("STATUS_TOPIC", "p2000/status"),
        "wacht_seconden": float(os.environ.get("HARTSLAG_WACHT_SECONDEN", "15")),
        # De bedieningsdienst op de sdr-server
        "bediening_url": os.environ.get("BEDIENING_URL",
                                        "http://sdrserver:8330").rstrip("/"),
        "bedien_sleutel": os.environ.get("BEDIEN_SLEUTEL", ""),
        "experiment": os.environ.get("BEDIEN_EXPERIMENT", "p2000"),
        # Drempels en remmen
        "stil_minuten": float(os.environ.get("STIL_DREMPEL_MINUTEN", "30")),
        "herstart_wacht_minuten": float(
            os.environ.get("HERSTART_WACHT_MINUTEN", "5")),
        "herstart_max": int(os.environ.get("HERSTART_MAX", "3")),
        "herstart_venster_uur": float(
            os.environ.get("HERSTART_VENSTER_UUR", "6")),
        "melding_wacht_uur": float(os.environ.get("MELDING_WACHT_UUR", "6")),
        "alleen_melden": os.environ.get("ALLEEN_MELDEN", "0") == "1",
        "status_bestand": os.environ.get(
            "STATUS_BESTAND", "/var/lib/mijnp2000-waakhond/status.json"),
        # Kanaal 1: mail
        "naar": naar,
        "smtp_host": os.environ.get("SMTP_HOST", ""),
        "smtp_port": int(os.environ.get("SMTP_PORT", "587")),
        "smtp_user": os.environ.get("SMTP_USER", ""),
        "smtp_wachtwoord": os.environ.get("SMTP_PASSWORD", ""),
        "mail_van": os.environ.get("MAIL_VAN", os.environ.get("SMTP_USER", "")),
        "mail_naam": os.environ.get("MAIL_NAAM", "MijnP2000"),
        # Kanaal 2: MQTT naar Home Assistant
        "meld_topic": os.environ.get("MELD_TOPIC", "p2000/waakhond"),
        "meld_client_id": os.environ.get("MELD_CLIENT_ID",
                                         "mijnp2000-waakhond"),
    }


# ── Kleine hulpjes ──────────────────────────────────────────────────────────

def nu() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def lees_tijd(waarde):
    """Zet een tijd uit de hartslag om; geeft None bij onbruikbare invoer."""
    if not waarde:
        return None
    try:
        moment = dt.datetime.fromisoformat(waarde)
    except (TypeError, ValueError):
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=dt.timezone.utc)
    return moment


def ouderdom(moment) -> float:
    """Seconden geleden, nooit negatief.

    De klokken van server023 en de sdr-server lopen niet op de seconde gelijk.
    Een klein verschil de verkeerde kant op zou anders een negatieve stilte
    geven.
    """
    if moment is None:
        return float("inf")
    return max(0.0, (nu() - moment).total_seconds())


def duur(seconden) -> str:
    """Een duur in hele minuten, met het juiste enkelvoud."""
    if seconden == float("inf"):
        return "onbekend lang"
    aantal = int(round(seconden / 60))
    return f"{aantal} minuut" if aantal == 1 else f"{aantal} minuten"


# ── De hartslag ophalen ─────────────────────────────────────────────────────

def _mqtt_client(client_id):
    """Maakt een client die zowel met paho 1 als met paho 2 werkt.

    Op server023 staat paho 2; die wil weten welke terugroepfuncties worden
    gebruikt. De oude vorm werkt daar nog wel, maar geeft een waarschuwing.
    De terugroepfuncties hieronder passen op allebei de vormen.
    """
    import paho.mqtt.client as mqtt
    try:
        return mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                           client_id=client_id)
    except AttributeError:  # paho 1 kent die keuze niet
        return mqtt.Client(client_id=client_id)


def lees_hartslag(inst):
    """Haalt het bewaarde bericht van STATUS_TOPIC op.

    Het bericht is bewaard (retain), dus de broker stuurt het meteen na het
    aanmelden. Meeluisteren op de meldingen zelf is daardoor niet nodig.
    Geeft None als er binnen de wachttijd niets komt.
    """
    gevonden = {}
    klaar = threading.Event()

    # paho 1 geeft vier waarden mee, paho 2 vijf. Met standaardwaarden past
    # dezelfde functie op allebei.
    def bij_verbinding(client, userdata, flags, reden=None, eigenschappen=None):
        client.subscribe(inst["status_topic"], qos=0)

    def bij_bericht(client, userdata, bericht):
        try:
            gevonden["stand"] = json.loads(bericht.payload.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as fout:
            log.error("Hartslag is niet te lezen: %s", fout)
        klaar.set()

    client = _mqtt_client(inst["meld_client_id"] + "-lezer")
    if inst["mqtt_user"]:
        client.username_pw_set(inst["mqtt_user"], inst["mqtt_wachtwoord"])
    client.on_connect = bij_verbinding
    client.on_message = bij_bericht
    try:
        client.connect(inst["mqtt_host"], inst["mqtt_port"], keepalive=30)
        client.loop_start()
        klaar.wait(inst["wacht_seconden"])
    except OSError as fout:
        log.error("Broker niet bereikbaar: %s", fout)
        return None
    finally:
        try:
            client.loop_stop()
            client.disconnect()
        except Exception:  # noqa: BLE001 - afsluiten mag nooit de run breken
            pass
    return gevonden.get("stand")


# ── De containerstand ophalen ───────────────────────────────────────────────

def lees_containerstand(inst):
    """Vraagt de bedieningsdienst op de sdr-server naar de stand.

    Geeft de regel van het eigen experiment terug, of None als de dienst niet
    bereikbaar is. Dit wordt pas gevraagd als er iets mis lijkt, zodat een
    storing in die dienst geen loos alarm geeft zolang alles gewoon loopt.
    """
    adres = f"{inst['bediening_url']}/api/status"
    try:
        with urllib.request.urlopen(adres, timeout=15) as antwoord:
            gegevens = json.loads(antwoord.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError) as fout:
        log.error("Bedieningsdienst niet bereikbaar: %s", fout)
        return None
    for regel in gegevens.get("experimenten", []):
        if regel.get("id") == inst["experiment"]:
            return regel
    log.error("Experiment %s staat niet in de bedieningsdienst",
              inst["experiment"])
    return None


def vraag_herstart(inst):
    """Vraagt de bedieningsdienst de container opnieuw te starten."""
    adres = f"{inst['bediening_url']}/api/herstart"
    inhoud = json.dumps({"experiment": inst["experiment"]}).encode("utf-8")
    verzoek = urllib.request.Request(adres, data=inhoud, method="POST")
    verzoek.add_header("Content-Type", "application/json")
    if inst["bedien_sleutel"]:
        verzoek.add_header("X-Bedien-Sleutel", inst["bedien_sleutel"])
    try:
        with urllib.request.urlopen(verzoek, timeout=180) as antwoord:
            gegevens = json.loads(antwoord.read().decode("utf-8"))
        gelukt = bool(gegevens.get("gelukt"))
        log.info("Herstart gevraagd: %s", "gelukt" if gelukt else gegevens)
        return gelukt
    except (urllib.error.URLError, OSError, ValueError) as fout:
        log.error("Herstart mislukt: %s", fout)
        return False


# ── De stand op schijf ──────────────────────────────────────────────────────

def lees_status(pad) -> dict:
    try:
        with open(pad, encoding="utf-8") as bestand:
            return json.load(bestand)
    except (OSError, ValueError):
        return {}


def schrijf_status(pad, status) -> None:
    try:
        os.makedirs(os.path.dirname(pad), exist_ok=True)
        tijdelijk = pad + ".nieuw"
        with open(tijdelijk, "w", encoding="utf-8") as bestand:
            json.dump(status, bestand, ensure_ascii=False, indent=2)
        os.replace(tijdelijk, pad)
    except OSError as fout:
        log.error("Stand niet weg te schrijven: %s", fout)


def herstarts_in_venster(status, uur) -> list:
    grens = nu() - dt.timedelta(hours=uur)
    bewaard = []
    for waarde in status.get("herstarts", []):
        moment = lees_tijd(waarde)
        if moment and moment > grens:
            bewaard.append(waarde)
    return bewaard


# ── Beoordelen ──────────────────────────────────────────────────────────────

def beoordeel(inst, hartslag) -> dict:
    """Bepaalt wat er aan de hand is, alleen op grond van de hartslag."""
    if hartslag is None:
        return {
            "soort": "geen_hartslag",
            "uitleg": "Er staat geen hartslag op de broker.",
            "stilte": float("inf"),
            "hartslag_ouderdom": float("inf"),
        }

    hartslag_seconden = float(hartslag.get("hartslag_seconden") or 60)
    oud = ouderdom(lees_tijd(hartslag.get("verzonden")))
    # Ruim: pas na vijf gemiste hartslagen, en nooit korter dan vijf minuten.
    grens_hartslag = max(5 * hartslag_seconden, 300)

    laatste = lees_tijd(hartslag.get("laatste_melding"))
    if laatste is None:
        # Nog nooit een melding verwerkt; dan telt de tijd sinds de start.
        stilte = ouderdom(lees_tijd(hartslag.get("gestart")))
    else:
        stilte = ouderdom(laatste)

    if oud > grens_hartslag:
        return {
            "soort": "hartslag_oud",
            "uitleg": (f"De laatste hartslag is {duur(oud)} oud; het proces "
                       "in de container reageert niet meer."),
            "stilte": stilte,
            "hartslag_ouderdom": oud,
        }

    if stilte > inst["stil_minuten"] * 60:
        return {
            "soort": "verwerking_gestopt",
            "uitleg": (f"Er is al {duur(stilte)} niets meer gedecodeerd, "
                       "terwijl de ontvanger wel doorloopt."),
            "stilte": stilte,
            "hartslag_ouderdom": oud,
        }

    return {
        "soort": "in_orde",
        "uitleg": f"Laatste melding {duur(stilte)} geleden.",
        "stilte": stilte,
        "hartslag_ouderdom": oud,
    }


# ── Het bericht ─────────────────────────────────────────────────────────────

def maak_bericht(inst, oordeel, herstart_gedaan, aantal_herstarts) -> dict:
    soort = oordeel["soort"]
    stil = duur(oordeel["stilte"])

    if soort == "in_orde":
        titel = "MijnP2000 verwerkt weer meldingen"
        tekst = f"De verwerking loopt weer. Laatste melding {stil} geleden."
    elif soort == "container_uit":
        titel = "MijnP2000-ontvanger staat uit"
        tekst = ("De container p2000-ontvanger draait niet. Er is niets "
                 "herstart, want een stilstaande container is meestal met "
                 "opzet gestopt.")
    elif soort == "onbereikbaar":
        titel = "MijnP2000: sdr-server niet te bereiken"
        tekst = ("De verwerking ligt stil en de bedieningsdienst op de "
                 "sdr-server antwoordt niet. Herstarten lukt daardoor niet.")
    elif soort == "limiet":
        titel = "MijnP2000 blijft stil na herstarten"
        tekst = (f"De verwerking ligt al {stil} stil en herstarten "
                 f"heeft niet geholpen ({aantal_herstarts} keer geprobeerd). "
                 "Waarschijnlijk zit het in de antenne, de plaatsing of de "
                 "versterking.")
    elif soort == "geen_hartslag":
        titel = ("MijnP2000 opnieuw gestart"
                 if herstart_gedaan else "MijnP2000 geeft geen hartslag")
        tekst = ("Er staat geen hartslag op de broker. "
                 + ("De container is opnieuw gestart. " if herstart_gedaan
                    else "")
                 + "Controleer of de ontvanger de versie met hartslag draait "
                   "en of de broker bereikbaar is.")
    elif herstart_gedaan:
        titel = "MijnP2000 opnieuw gestart"
        tekst = (f"De verwerking lag {stil} stil. De container "
                 "p2000-ontvanger is opnieuw gestart.")
    else:
        titel = "MijnP2000 verwerkt geen meldingen meer"
        tekst = f"De verwerking ligt {stil} stil. {oordeel['uitleg']}"

    return {
        "verzonden": nu().isoformat(timespec="seconds"),
        "soort": soort,
        "titel": titel,
        "tekst": tekst,
        "uitleg": oordeel["uitleg"],
        "stil_minuten": (None if oordeel["stilte"] == float("inf")
                         else int(round(oordeel["stilte"] / 60))),
        "herstart": herstart_gedaan,
        "herstarts_in_venster": aantal_herstarts,
        "container": "p2000-ontvanger",
        "url": PAGINA,
    }


# ── De kanalen ──────────────────────────────────────────────────────────────

def verstuur_mail(inst, melding) -> None:
    regels = [
        melding["tekst"],
        "",
        f"Toelichting: {melding['uitleg']}",
        f"Moment: {nu().astimezone(TZ).strftime('%d-%m-%Y %H:%M')}",
        f"Herstart uitgevoerd: {'ja' if melding['herstart'] else 'nee'}",
        "",
        f"Pagina: {melding['url']}",
    ]
    msg = MIMEText("\n".join(regels), "plain", "utf-8")
    msg["Subject"] = melding["titel"]
    msg["From"] = formataddr((inst["mail_naam"], inst["mail_van"]))
    msg["To"] = ", ".join(inst["naar"])

    if inst["smtp_port"] == 465:
        server = smtplib.SMTP_SSL(inst["smtp_host"], inst["smtp_port"],
                                  timeout=30)
    else:
        server = smtplib.SMTP(inst["smtp_host"], inst["smtp_port"], timeout=30)
        server.starttls()
    try:
        if inst["smtp_user"]:
            server.login(inst["smtp_user"], inst["smtp_wachtwoord"])
        server.sendmail(inst["mail_van"], inst["naar"], msg.as_string())
    finally:
        server.quit()
    log.info("Melding gemaild naar %d adres(sen)", len(inst["naar"]))


def verstuur_mqtt(inst, melding) -> None:
    """Zet de melding als JSON op de broker, voor Home Assistant.

    Bewust zonder retain: met een bewaard bericht zou Home Assistant bij elke
    herstart de laatste melding opnieuw binnenkrijgen en opnieuw de telefoon
    laten trillen. Wel met bevestiging (qos 1), want dit bericht komt maar een
    keer.
    """
    from paho.mqtt import publish as mqtt_publish

    auth = None
    if inst["mqtt_user"]:
        auth = {"username": inst["mqtt_user"],
                "password": inst["mqtt_wachtwoord"]}
    mqtt_publish.single(
        inst["meld_topic"],
        payload=json.dumps(melding, ensure_ascii=False),
        qos=1,
        retain=False,
        hostname=inst["mqtt_host"],
        port=inst["mqtt_port"],
        client_id=inst["meld_client_id"],
        keepalive=30,
        auth=auth,
    )
    log.info("Melding op MQTT gezet: %s", inst["meld_topic"])


def kanalen(inst) -> dict:
    gekozen = {}
    if inst["naar"] and inst["smtp_host"]:
        gekozen["mail"] = verstuur_mail
    if inst["mqtt_host"] and inst["meld_topic"]:
        gekozen["mqtt"] = verstuur_mqtt
    return gekozen


def meld(inst, melding) -> bool:
    """Verstuurt over elk kanaal dat aanstaat. Geeft terug of iets lukte."""
    gelukt = []
    for naam, verstuur in kanalen(inst).items():
        try:
            verstuur(inst, melding)
            gelukt.append(naam)
        except Exception as fout:  # noqa: BLE001
            log.error("Melden via %s mislukt: %s", naam, fout)
    if gelukt:
        log.info("Gemeld via %s: %s", ", ".join(gelukt), melding["titel"])
    else:
        log.warning("Niet gemeld: geen kanaal gelukt of ingesteld")
    return bool(gelukt)


# ── De ronde ────────────────────────────────────────────────────────────────

def moet_melden(status, soort, wacht_uur) -> bool:
    """Melden bij een verandering, en daarna hoogstens eens per wachttijd."""
    if status.get("soort") != soort:
        return True
    laatste = lees_tijd(status.get("gemeld"))
    if laatste is None:
        return True
    return ouderdom(laatste) > wacht_uur * 3600


def ronde(inst, droog=False) -> dict:
    status = lees_status(inst["status_bestand"])
    hartslag = lees_hartslag(inst)
    oordeel = beoordeel(inst, hartslag)
    herstart_gedaan = False
    gedaan = herstarts_in_venster(status, inst["herstart_venster_uur"])

    if oordeel["soort"] != "in_orde":
        # Pas nu de sdr-server bevragen: zolang alles loopt, hoeft dat niet.
        stand = lees_containerstand(inst)
        if stand is None:
            oordeel["soort"] = "onbereikbaar"
        elif stand.get("staat") != "draait":
            oordeel["soort"] = "container_uit"
            oordeel["uitleg"] = (
                f"De container staat op '{stand.get('staat')}': "
                f"{stand.get('toelichting', '')}".strip())
        else:
            # De ontvanger draait wel. Eerst de remmen langs.
            sinds_herstart = ouderdom(lees_tijd(status.get("laatste_herstart")))
            if sinds_herstart < inst["herstart_wacht_minuten"] * 60:
                log.info("Kort na een herstart; deze ronde niets doen.")
                status["laatste_controle"] = nu().isoformat(timespec="seconds")
                schrijf_status(inst["status_bestand"], status)
                return {"oordeel": oordeel, "herstart": False, "gemeld": False}
            if len(gedaan) >= inst["herstart_max"]:
                oordeel["soort"] = "limiet"
            elif droog or inst["alleen_melden"]:
                log.info("Proefstand: wel melden, niet herstarten.")
            else:
                herstart_gedaan = vraag_herstart(inst)
                if herstart_gedaan:
                    gedaan.append(nu().isoformat(timespec="seconds"))
                    status["laatste_herstart"] = gedaan[-1]

    melding = maak_bericht(inst, oordeel, herstart_gedaan, len(gedaan))
    gemeld = False
    if oordeel["soort"] == "in_orde":
        # Alleen iets laten horen als er eerder wel wat aan de hand was.
        if status.get("soort") not in (None, "in_orde"):
            gemeld = meld(inst, melding)
    elif moet_melden(status, oordeel["soort"], inst["melding_wacht_uur"]):
        gemeld = meld(inst, melding)

    status["soort"] = oordeel["soort"]
    status["laatste_controle"] = nu().isoformat(timespec="seconds")
    status["laatste_uitleg"] = oordeel["uitleg"]
    status["herstarts"] = gedaan
    if gemeld:
        status["gemeld"] = melding["verzonden"]
    schrijf_status(inst["status_bestand"], status)

    log.info("%s | %s | herstart: %s | gemeld: %s", oordeel["soort"],
             oordeel["uitleg"], herstart_gedaan, gemeld)
    return {"oordeel": oordeel, "melding": melding,
            "herstart": herstart_gedaan, "gemeld": gemeld}


def toon_stand(inst) -> int:
    """Kijkt alleen en verandert niets. Handig bij het zoeken naar storingen."""
    hartslag = lees_hartslag(inst)
    print("Hartslag:", json.dumps(hartslag, ensure_ascii=False, indent=2)
          if hartslag else "niet gevonden op " + inst["status_topic"])
    oordeel = beoordeel(inst, hartslag)
    print(f"\nOordeel: {oordeel['soort']}")
    print(f"Toelichting: {oordeel['uitleg']}")
    stand = lees_containerstand(inst)
    print("\nContainer:", json.dumps(stand, ensure_ascii=False, indent=2)
          if stand else "bedieningsdienst niet bereikbaar")
    print("\nKanalen aan:", ", ".join(kanalen(inst)) or "geen")
    print("Stand op schijf:", json.dumps(
        lees_status(inst["status_bestand"]), ensure_ascii=False, indent=2))
    return 0


def proef(inst) -> int:
    """Stuurt een proefmelding over alle kanalen die aanstaan."""
    if not kanalen(inst):
        print("Geen enkel kanaal staat aan. Vul /etc/mijnp2000/waakhond.env.",
              file=sys.stderr)
        return 1
    melding = maak_bericht(inst, {"soort": "proef", "stilte": 0.0,
                                  "uitleg": "Proefbericht van de waakhond."},
                           False, 0)
    melding["titel"] = "Proefmelding MijnP2000-waakhond"
    melding["tekst"] = ("Proefbericht van de waakhond. Komt deze melding aan, "
                        "dan werkt de hele keten.")
    melding["proef"] = True
    return 0 if meld(inst, melding) else 1


def main() -> int:
    ontleder = argparse.ArgumentParser(description="Waakhond van MijnP2000")
    ontleder.add_argument("--stand", action="store_true",
                          help="Alleen kijken en de uitkomst tonen")
    ontleder.add_argument("--droog", action="store_true",
                          help="Wel melden, niet herstarten")
    ontleder.add_argument("--proef", action="store_true",
                          help="Een proefmelding over alle kanalen sturen")
    keuzes = ontleder.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(levelname)s %(message)s")
    inst = instellingen()

    if keuzes.stand:
        return toon_stand(inst)
    if keuzes.proef:
        return proef(inst)
    ronde(inst, droog=keuzes.droog)
    return 0


if __name__ == "__main__":
    sys.exit(main())
