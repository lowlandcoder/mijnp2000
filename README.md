# MijnP2000

Ontvangst en weergave van P2000-meldingen (169,65 MHz, FLEX) van de Nederlandse
hulpdiensten, met een RTL-SDR-stick op de sdr-server. De opzet bestaat uit één
ontvanger en meerdere afnemers, met MQTT als schakelpunt:

- **Ontvanger** (`ontvanger/`): een container op de sdr-server die ontvangt,
  FLEX decodeert en elke melding als JSON op MQTT zet.
- **Afnemer — Home Assistant**: leest hetzelfde MQTT-onderwerp en stuurt
  seintjes naar de telefoon, met filters per regio. (Later, als Home Assistant
  draait.)
- **Afnemer — archiefpagina** `mijnp2000.lab023.nl`: een kleine backend op de
  lab023-server leest MQTT, schrijft de meldingen in een SQLite-database,
  vertaalt capcodes naar regio, en toont ze met filter op regio en instelbare
  geschiedenis tot zeven dagen. Op `/kaart` staat daarnaast een eigen kaart met
  de meldingen van het laatste uur binnen een instelbare straal. De opmaak volgt sinds 16-08-2026 de compacte
  weergave van p2000.page; sinds 23-08-2026 met kleinere letters en standaard
  ingeklapte capcodes, en met een samengevoegde capcode-lijst van ± 88.000
  codes. Zie `archief/README.md`.

De broker draait al: Mosquitto op de lab023-server (192.168.2.38), poort 1883,
met verplichte aanmelding.

## Onderdelen

- `ontvanger/` — de P2000-ontvangercontainer. Zie `ontvanger/README.md`.
- `archief/` — de backend en de pagina `mijnp2000.lab023.nl`. Zie
  `archief/README.md`.
- `waakhond/` — bewaking op server023 die elke vijf minuten controleert of de
  verwerking nog loopt, de ontvanger zo nodig herstart en dat meldt. Zie
  `waakhond/README.md`.
- `homeassistant/` — de automatisering die van een waakhondmelding een
  telefoonmelding maakt.

## Bewaking

Sinds 29-08-2026 zet de ontvanger elke minuut een bewaard bericht op
`p2000/status` met de tijd van de laatste gedecodeerde melding. De waakhond op
server023 leest die stand elke vijf minuten.

Dat vult een gat dat Docker niet dicht: valt `rtl_fm` weg, dan stopt de
container en start Docker hem vanzelf opnieuw, maar blijft de keten leven
terwijl er niets meer gedecodeerd wordt, dan heet de container nog steeds
"draait" en loopt de pagina stil achter. Bij een stilte van meer dan 15
minuten vraagt de waakhond de containerstand op bij `mijnsdr-bediening` op de
sdr-server, herstart hij de ontvanger en meldt hij dat via mail en via Home
Assistant. Hoogstens drie herstarts per zes uur; daarna volgt alleen nog een
melding, want een herstart repareert geen slecht afgestemde antenne.

## Stand van zaken

- [x] Broker met wachtwoord en open poort (in de stack `mijnhuis`).
- [x] Ontvangercontainer gebouwd (rtl-sdr-blog-stuurprogramma voor de V4).
- [x] Ontvanger uitgerold en getest op de sdr-server; meldingen op MQTT.
- [x] Archiefpagina met database en regiofilter gebouwd.
- [x] Archiefpagina uitgerold op de lab023-server en capcode-lijst geplaatst.
- [x] Opmaak van de pagina naar het voorbeeld van p2000.page (16-08-2026).
- [x] Capcodes standaard ingeklapt, kleinere letters en samengevoegde
      capcode-lijst van ± 88.000 codes (23-08-2026).
- [x] Hartslag op `p2000/status` en waakhond op server023, met herstart via
      de bedieningsdienst en meldingen via mail en Home Assistant
      (29-08-2026).
- [x] Waakhond aangescherpt: een ronde per vijf minuten en ingrijpen na 15
      minuten stilte, en de gain van de ontvanger van 40 naar 30 dB, omdat de
      stick tweemaal op een avond van de USB-bus viel (07-09-2026).
- [x] Adresherkenning voor de kaartpin: straat, huisnummer, postcode en plaats
      uit de meldingtekst, zonder capcodes, rit- en eenheidsnummers
      (09-09-2026).
- [x] Publiceren met `~/publiceer.sh mijnp2000` werkt weer, doordat
      `.publiceer-compose` naar `archief/` wijst; `robots.txt` en het weren van
      scanverkeer toegevoegd aan de nginx-instelling (09-09-2026).
- [x] Eigen kaartpagina op `/kaart`: meldingen van de afgelopen 60 minuten
      binnen een instelbare straal, met een kolom ernaast en pins die in twee
      richtingen met de kolom meelichten. Adressen worden omgezet met de PDOK
      Locatieserver en bewaard in de eigen database (12-09-2026).
- [ ] Home Assistant als afnemer van de meldingen zelf, met filters per regio
      en seintjes naar de telefoon.

## Eigen stick

Sinds 16-08-2026 zitten er twee RTL-SDR-sticks in de sdr-server. De tweede
stick heeft in de EEPROM serienummer `00000002` en de naam `p2000` gekregen en
is vast aan deze ontvanger toegewezen. De eerste stick (`00000001`) blijft
wisselen tussen ADS-B en RTL433.

De toewijzing gebeurt met de optie `-d 00000002` in `RTL_CMD`, dus op
serienummer en niet op apparaatnummer. Het apparaatnummer hangt af van de
volgorde waarin de sticks worden gezien en kan bij een herstart verschuiven.

## Privacy

P2000-meldingen bevatten soms adressen en af en toe namen. De pagina wordt
afgeschermd via de centrale aanmelding en is voor eigen gebruik. Meldingen niet
breder delen of publiceren.
