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

### Vaste stick op serienummer

Er zitten twee sticks in de sdr-server. Deze ontvanger gebruikt vast de stick
met serienummer `00000002` en de naam `p2000`; de andere stick (`00000001`)
blijft voor ADS-B en RTL433.

De keuze valt met de optie `-d` in `RTL_CMD`. Die optie neemt niet alleen een
apparaatnummer maar ook een serienummer of een naam, en zoekt zelf de juiste
stick op. Op serienummer kiezen is de veiliger weg: het apparaatnummer hangt af
van de volgorde waarin de sticks worden gezien en kan bij een herstart of bij
het loskoppelen van de andere stick verschuiven.

Onder `devices` wordt de hele usb-bus doorgegeven, dus beide sticks zijn in de
container zichtbaar. Alleen de gekozen stick wordt geopend, dus de andere
container kan tegelijk draaien.

Controleren welke sticks er zijn:

    rtl_test -t

Verwacht wordt een lijst met twee apparaten, waarvan één met serienummer
`00000002`. Staat daar tweemaal `00000001`, dan is de EEPROM van de tweede
stick nog niet geschreven; zie het beheer van de sticks in `mijnsdr`.

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
| `MQTT_USER` | gebruikersnaam op de broker | `p2000` |
| `MQTT_PASSWORD` | wachtwoord | *invullen* |
| `RTL_CMD` | het rtl_fm-commando; hier met vaste gain 30 dB | zie `docker-compose.yml` |
| `STATUS_TOPIC` | onderwerp voor de hartslag; leeg zet de hartslag uit | `p2000/status` |
| `STATUS_SECONDEN` | tijd tussen twee hartslagen | `60` |

Sinds 07-09-2026 staat de gain vast op 30 dB. Daarvoor stond hij op 40 dB. Bij
die waarde viel de stick regelmatig van de USB-bus met foutcode -71, wat past
bij warmte en oversturing. Automatische gain gaf eerder helemaal geen
ontvangst, dus een vaste waarde blijft nodig. Levert 30 dB merkbaar minder
meldingen op, zet hem dan terug naar 40 of probeer 36. Bij een andere antenne
of plek kan opnieuw een andere waarde nodig zijn.

De broker draait als Mosquitto op de lab023-server (192.168.2.38), met poort
1883 gepubliceerd en verplichte aanmelding. De ontvanger en de archiefpagina
gebruiken allebei het account `p2000`; het wachtwoord staat in `.env` naast
het compose-bestand en niet in de repository.

## Hartslag voor de waakhond

Sinds 29-08-2026 zet de ontvanger elke minuut een **bewaard** bericht op
`p2000/status`. Daarin staat wanneer de laatste melding is gedecodeerd en
hoeveel er sinds de vorige hartslag bij kwamen:

    {
      "verzonden": "2026-08-29T12:05:50+00:00",
      "gestart": "2026-08-29T09:31:12+00:00",
      "laatste_melding": "2026-08-29T12:05:44+00:00",
      "stil_seconden": 6,
      "sinds_vorige_hartslag": 14,
      "totaal": 8123,
      "hartslag_seconden": 60
    }

Waarom dit nodig is: valt `rtl_fm` weg, dan krijgt `publiceer.py` einde-invoer,
stopt de container en start Docker hem vanzelf opnieuw. Maar blijft de keten
leven terwijl `multimon-ng` niets meer decodeert, dan ziet Docker daar niets
van. De container heet dan nog steeds "draait", terwijl er niets meer
binnenkomt. Aan `stil_seconden` is dat wel te zien.

Het bericht is bewaard (retain), zodat de waakhond op server023 de laatste
stand in een keer kan ophalen zonder mee te luisteren. Het gaat zonder
bevestiging (qos 0) de deur uit: het bericht komt elke minuut opnieuw, dus een
gemist bericht doet er niet toe, en er groeit geen wachtrij als de broker even
weg is. De hartslag draait in een eigen draad, want de hoofdlus staat juist
stil zodra er niets meer binnenkomt.

Meekijken:

    mosquitto_sub -h 192.168.2.38 -u p2000 -P <wachtwoord> -t 'p2000/status' -v

Wat er met deze stand gebeurt, staat in `../waakhond/README.md`.

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

## Controleren na een wijziging

1. De stack opnieuw uitrollen en de logboeken van de container bekijken.
   Verwacht: een regel waarin rtl_fm meldt welk apparaat is geopend, met
   serienummer `00000002`, en daarna de regel "Verbonden met ...". Binnen
   enkele minuten volgen publicatiemeldingen; P2000 zendt doorlopend.
2. Meelezen op de broker om te controleren of de meldingen aankomen:

       mosquitto_sub -h <broker> -t 'p2000/bericht'

3. Controleren dat de andere containers nog werken. ADS-B en RTL433 horen nu
   naast P2000 te kunnen draaien, elk op een eigen stick.

Meldt rtl_fm "No supported devices found" of "usb_claim_interface error -6",
dan pakt een andere container dezelfde stick. Controleer dan of die container
ook op serienummer kiest en niet op apparaatnummer 0.

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
