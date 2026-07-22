# MijnP2000

Ontvangst en weergave van P2000-meldingen (169,65 MHz, FLEX) van de Nederlandse
hulpdiensten, met een RTL-SDR-stick op de sdr-server. De opzet bestaat uit één
ontvanger en meerdere afnemers, met MQTT als schakelpunt:

- **Ontvanger** (`ontvanger/`): een container op de sdr-server die ontvangt,
  FLEX decodeert en elke melding als JSON op MQTT zet.
- **Afnemer — Home Assistant**: leest hetzelfde MQTT-onderwerp en stuurt
  seintjes naar de telefoon, met filters per regio. (Later, als Home Assistant
  draait.)
- **Afnemer — archiefpagina** `mijnp2000.lab023.nl`: een kleine backend leest
  MQTT, schrijft de meldingen in een SQLite-database, vertaalt capcodes naar
  regio, en toont ze in de Lab023-huisstijl met filter op regio en instelbare
  geschiedenis tot zeven dagen. (Volgt na de ontvanger.)

De broker draait al: Mosquitto op de lab023-server (192.168.2.38), poort 1883,
met verplichte aanmelding.

## Onderdelen

- `ontvanger/` — de P2000-ontvangercontainer. Zie `ontvanger/README.md`.
- (volgt) `archief/` — de backend en de pagina `mijnp2000.lab023.nl`.

## Stand van zaken

- [x] Broker met wachtwoord en open poort (in de stack `mijnhuis`).
- [x] Ontvangercontainer gebouwd (rtl-sdr-blog-stuurprogramma voor de V4).
- [x] Ontvanger uitgerold en getest op de sdr-server; meldingen op MQTT.
- [ ] Archiefpagina met database en regiofilter.
- [ ] Home Assistant als afnemer met meldingen naar de telefoon.

## Eén stick

Er is één RTL-SDR-stick op de sdr-server, gedeeld met ADS-B en RTL433. Die kan
maar op één frequentie tegelijk luisteren, dus P2000 draait voorlopig alleen
als de stick daaraan is gegeven. Zodra er een tweede stick is, draait P2000
daar vast op, terwijl de eerste blijft wisselen tussen ADS-B en RTL433.

## Privacy

P2000-meldingen bevatten soms adressen en af en toe namen. De pagina wordt
afgeschermd via de centrale aanmelding en is voor eigen gebruik. Meldingen niet
breder delen of publiceren.
