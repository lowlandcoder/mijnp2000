# P2000-ontvanger

Ontvangt P2000-meldingen (169,65 MHz, FLEX-protocol) met een RTL-SDR-stick en
zet elke melding als JSON op een MQTT-onderwerp. De ontvanger filtert en
verrijkt niets; dat gebeurt bij de afnemers, zodat één ontvanger meerdere
afnemers kan bedienen:

- Home Assistant leest hetzelfde onderwerp en stuurt seintjes naar de telefoon.
- De archiefpagina `mijnp2000.lab023.nl` slaat de meldingen op en toont ze met
  filter op regio en een instelbare periode.

Dit is het eerste onderdeel; de broker bestaat al en de archiefpagina volgt.

## Stick: RTL-SDR Blog V4

De gebruikte stick is een RTL-SDR Blog V4. Dat model heeft het stuurprogramma
van rtl-sdr-blog nodig; de standaard `rtl-sdr` uit Debian ondersteunt de V4
niet en geeft "PLL not locked" zonder ontvangst. De `Dockerfile` bouwt daarom
dat stuurprogramma uit de bron. De containers voor ADS-B en RTL433 werken al,
omdat die hun eigen, nieuwere stuurprogramma meebrengen.

## Bestanden

- `Dockerfile` — bouwt het image met het rtl-sdr-blog-stuurprogramma,
  multimon-ng en het publicatiescript.
- `entrypoint.sh` — start de keten rtl_fm → multimon-ng → publiceer.py.
- `publiceer.py` — leest de FLEX-regels en publiceert ze als JSON op MQTT.
- `docker-compose.yml` — stack voor Portainer, met de instellingen op één plek.

## Berichtvorm op MQTT

Elke melding komt als JSON op het onderwerp (standaard `p2000/bericht`):

    {
      "ontvangen": "2026-07-22T08:15:03+00:00",
      "tijd_flex": "2026-07-22 10:15:02",
      "capcodes": ["002029568", "000126999"],
      "soort": "ALN",
      "bericht": "A2 rit 79824 Sloterweg Badhoevedorp"
    }

De capcodes bepalen de regio en de eenheid. Het vertalen daarvan naar een
leesbare regio gebeurt bewust niet hier, maar in de archiefpagina, met een
capcode-database.

## Instellingen

In Portainer onder `environment` in te vullen:

| Instelling | Betekenis | Waarde |
| --- | --- | --- |
| `MQTT_HOST` | adres van de broker (lab023-server) | `192.168.2.38` |
| `MQTT_PORT` | poort van de broker | `1883` |
| `MQTT_TOPIC` | onderwerp om op te publiceren | `p2000/bericht` |
| `MQTT_USER` | gebruikersnaam op de broker | `admin_mosquitto` |
| `MQTT_PASSWORD` | wachtwoord | *invullen* |
| `RTL_CMD` | het rtl_fm-commando; hier met vaste gain 40 dB | zie `docker-compose.yml` |

Een vaste gain van 40 dB blijkt op deze plek goed te werken; automatische gain
gaf geen ontvangst. Bij een andere antenne of plek kan een andere waarde nodig
zijn (probeer bijvoorbeeld 28 of 49.6).

De broker draait als Mosquitto op de lab023-server (192.168.2.38), met poort
1883 gepubliceerd en verplichte aanmelding. De gebruiker `admin_mosquitto` en
het wachtwoord zijn dezelfde als in de broker en in Zigbee2MQTT.

## Inrichting via Portainer

De stick zit in de sdr-server, dus de ontvanger draait daar, net als de
containers voor ADS-B en RTL433.

1. Repository klonen op de sdr-server, of het image vooraf bouwen en naar een
   register pushen.
2. In Portainer een stack aanmaken op basis van `docker-compose.yml`.
3. Bij `environment` het adres van de bestaande broker invullen (`MQTT_HOST`)
   en zo nodig gebruiker en wachtwoord.
4. Onder `devices` controleren dat de USB-stick wordt doorgegeven. Het pad is
   op de sdr-server te vinden met:

       ls -l /dev/bus/usb

   Vaak volstaat het doorgeven van de hele usb-bus (`/dev/bus/usb:/dev/bus/usb`).
5. De stack uitrollen.

## Één stick: eerst testen, later vast

Er is één RTL-SDR-stick. Die kan maar op één frequentie tegelijk luisteren,
dus P2000, ADS-B en RTL433 kunnen niet samen draaien. Voor een test wordt de
stick tijdelijk aan P2000 gegeven:

1. In Portainer de containers voor ADS-B en RTL433 stoppen.
2. De stack `p2000-ontvanger` starten.
3. De logboeken van de container bekijken. Verwacht: de regel "Verbonden met
   ..." en daarna, binnen enkele minuten, publicatiemeldingen. P2000 zendt
   doorlopend, dus er hoort snel iets binnen te komen.
4. Meelezen op de broker om te controleren of de meldingen aankomen:

       mosquitto_sub -h <broker> -t 'p2000/bericht'

Na de test kan de stick terug naar ADS-B of RTL433. Zodra er een tweede stick
is, draait P2000 vast op die tweede stick, terwijl de eerste blijft wisselen
tussen ADS-B en RTL433. P2000 is daarvoor de beste kandidaat om continu te
draaien, omdat de waarde in de opgebouwde geschiedenis zit.

## Volgende stappen

- Home Assistant later op hetzelfde onderwerp laten meelezen (MQTT-integratie),
  met filters per regio en seintjes naar de telefoon.
- De archiefpagina `mijnp2000.lab023.nl` bouwen: een klein programma dat het
  onderwerp meeleest, de meldingen in een SQLite-database schrijft, capcodes
  naar regio vertaalt, en een pagina in de Lab023-huisstijl toont met filter op
  regio en instelbare geschiedenis tot zeven dagen.

## Geheimen

Geen geheimen in deze map. De broker-gegevens worden in Portainer als
omgevingsvariabelen ingevuld, niet in de repository opgeslagen.
