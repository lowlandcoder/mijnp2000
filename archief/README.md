# P2000-archief

De archiefpagina `mijnp2000.lab023.nl`: een kleine backend die de
P2000-meldingen van de broker meeleest, opslaat in een SQLite-database en toont
op een brede, compacte pagina, met filter op regio en een instelbare periode tot
zeven dagen.

Deze container draait op de lab023-server, naast nginx en de broker. De
ontvanger (`../ontvanger`) draait op de sdr-server en publiceert de meldingen op
MQTT; deze backend is een van de afnemers.

## Bestanden

- `app.py` — de backend: leest MQTT mee, slaat op in SQLite, vertaalt capcodes
  naar regio, schoont oude meldingen op en biedt de pagina en een JSON-API.
- `static/` — de pagina: `index.html`, `style.css`, `script.js`. Het bestand
  `huisstijl.css` staat er nog wel, maar wordt niet meer ingeladen; zie
  "Opmaak van de pagina".
- `Dockerfile`, `requirements.txt`, `docker-compose.yml` — om de container te
  bouwen en te draaien.
- `nginx-mijnp2000.conf` — doorschakeling met centrale aanmelding.
- `data/capcodes.voorbeeld.csv` — voorbeeld van het capcode-bestand.

## Hoe het werkt

De backend houdt één verbinding met de broker open en schrijft elke melding weg
in `data/p2000.db`. Bij het opslaan worden de capcodes vertaald naar regio en
discipline met `data/capcodes.csv`. De pagina haalt de meldingen op via de
API en toont ze, nieuwste bovenaan. Mogelijkheden op de pagina:

- filteren op meerdere regio's tegelijk, op periode en op een zoekwoord;
- bij een eerste bezoek staat de regio Kennemerland aan; een andere keuze wordt
  per apparaat in de browser onthouden. De standaardregio staat bovenin
  `static/script.js` in de lijst `STANDAARD_REGIOS`;
- een kleur per dienst (brandweer rood, ambulance geel, politie blauw,
  lifeliner paars), in de titel van de melding en in de balk links;
- een kaartpin rechts in elke melding die de locatie in Google Maps opent;
- een knop naar de landelijke live-kaart van p2000.page;
- de vertaling per capcode (eenheid, dienst en regio) en een cursieve regel met
  de eenheid en de standplaats. Dit blok staat sinds 23-08-2026 standaard
  ingeklapt; een tik op de melding klapt het uit en weer in. Het aantal
  capcodes staat in een klein wisselknopje in de metaregel;
- een seintje bij een nieuwe melding, aan of uit met de luidsprekerknop.

Meldingen ouder dan de bewaartermijn (standaard zeven dagen, instelbaar via
`RETENTIE_DAGEN`) worden elk uur verwijderd.

## Opmaak van de pagina

De pagina volgt sinds 16-08-2026 bewust niet de glaslook van de Lab023-huisstijl,
maar de weergave van p2000.page. Reden: op een telefoon paste er in de oude
opzet nauwelijks informatie op het scherm. De keuzes:

- donkergrijze achtergrond (`#131313`) met meldingen op `#2b2b2b`, over de volle
  breedte van het scherm en zonder afgeronde hoeken;
- de melding zelf als vetgedrukte titel van 14 pixels (13 op de telefoon), in de
  kleur van de dienst. Op 23-08-2026 zijn alle letters, marges en de pinkolom
  verkleind, zodat er op een telefoon meer meldingen op het scherm passen;
- daaronder de tijd (uren en minuten vet, seconden lichter), een rood blokje met
  het aantal minuten geleden, de datum, en badges voor prioriteit en regio;
- daaronder de capcodes, elk op een eigen regel in grijs, standaard ingeklapt en
  uit te klappen met een tik op de melding;
- een grijze pinkolom rechts over de volle hoogte van de melding, die de locatie
  in Google Maps opent;
- een vaste balk bovenin met een lopende klok, en knoppen voor de startpagina,
  het geluid, de filters, de landelijke kaart, zoeken en schermvullend;
- de filters (regio, periode, zoeken, verversen) zitten achter de oranje
  filterknop en nemen zo geen ruimte in als ze niet nodig zijn.

Omdat `huisstijl.css` niet meer wordt ingeladen, heeft een wijziging in de
gedeelde huisstijl geen gevolgen voor deze pagina. Het bestand blijft wel in
`static/` staan, zodat `verspreid-huisstijl.ps1` zonder foutmelding blijft
werken.

## Capcode-database: nodig voor het regiofilter

Het filteren op regio werkt alleen met een capcode-database. Zonder die database
worden de meldingen wel opgeslagen en getoond, maar blijft het regioveld leeg.

Het bestand `data/capcodes.csv` heeft vijf kolommen: `capcode`, `regio`,
`discipline`, `plaats`, `omschrijving`. De `omschrijving` levert de vertaling
per capcode op de pagina (bijvoorbeeld "Ambulance 12-162").

De lijst staat in de repository en wordt gemaakt met de omzetter uit `tools/`,
uit twee openbare bronnen:

  * p2000.bommel.net (landelijk, actueel maar beknopt, zo'n 9.600 capcodes);
  * cyberjunky/RTL-SDR-P2000Receiver-HA op GitHub (zeer volledig, zo'n 88.000
    capcodes, maar sinds 2023 niet meer bijgewerkt).

De omzetter voegt beide samen: de eerste bron wint, latere bronnen vullen
alleen ontbrekende capcodes en lege velden aan. Regionamen worden daarbij
gelijkgetrokken naar de schrijfwijze van bommel.net, zodat het regiofilter geen
dubbele regio's toont. Sinds 23-08-2026 staat de samengevoegde lijst
(± 88.000 capcodes) in `data/capcodes.csv`.

Verversen kan op de server (of op de pc, daarna committen en pushen):

    curl -s -o /tmp/bommel.csv https://p2000.bommel.net/cap2csv.php
    curl -s -o /tmp/cyberjunky.txt https://raw.githubusercontent.com/cyberjunky/RTL-SDR-P2000Receiver-HA/main/db_capcodes.txt
    python3 tools/converteer_capcodes.py /tmp/bommel.csv /tmp/cyberjunky.txt data/capcodes.csv
    sudo docker compose restart mijnp2000-archief

Het aantal geladen capcodes staat in het logboek bij het opstarten. De lijst
veroudert langzaam; verversen hoeft maar af en toe. Let op: gebeurt het
verversen op de server, dan wijkt `data/capcodes.csv` daar af van de
repository en kan een volgende `git pull` weigeren. Herstel dat met
`git checkout -- archief/data/capcodes.csv` of verwerk de verversing voortaan
via de pc en de repository.

## Instellingen

In `docker-compose.yml` onder `environment`:

| Instelling | Betekenis | Waarde |
| --- | --- | --- |
| `MQTT_HOST` | adres van de broker | `192.168.2.38` |
| `MQTT_PORT` | poort van de broker | `1883` |
| `MQTT_TOPIC` | onderwerp om mee te lezen | `p2000/bericht` |
| `MQTT_USER` | gebruikersnaam op de broker | `admin_mosquitto` |
| `MQTT_PASSWORD` | wachtwoord (via `.env`) | *invullen* |
| `RETENTIE_DAGEN` | bewaartermijn in dagen | `7` |

## Inrichting op de lab023-server

1. Repository klonen (of bijwerken) op de lab023-server.
2. `.env` maken met het wachtwoord:

       cd archief
       cp .env.voorbeeld .env
       nano .env

3. Eventueel `data/capcodes.csv` plaatsen voor het regiofilter.
4. De container bouwen en starten:

       sudo docker compose up -d --build

   De backend luistert nu op `127.0.0.1:8200`.
5. DNS-regel voor `mijnp2000.lab023.nl` aanmaken.
6. De nginx-conf plaatsen en activeren:

       sudo cp nginx-mijnp2000.conf /etc/nginx/sites-available/mijnp2000
       sudo ln -s /etc/nginx/sites-available/mijnp2000 /etc/nginx/sites-enabled/
       sudo nginx -t && sudo systemctl reload nginx

7. HTTPS instellen:

       sudo certbot --nginx -d mijnp2000.lab023.nl

   Controleer daarna dat `include snippets/lab023-login.conf;` in het 443-blok
   staat.
8. Op `mijnsdr.lab023.nl` de kaart MijnP2000 activeren: in `script.js` de
   `actief: false` weghalen en het domein invullen.

## Afscherming en privacy

De pagina loopt via de centrale aanmelding en is voor eigen gebruik.
P2000-meldingen bevatten soms adressen en af en toe namen. Niet breder delen of
publiceren.

## Geheimen

Het wachtwoord staat in `.env` en blijft buiten de repository. De database
staat in het gekoppelde volume en wordt niet meegecommit; de capcode-lijst
`data/capcodes.csv` staat wel in de repository, want die bevat alleen openbare
gegevens.
