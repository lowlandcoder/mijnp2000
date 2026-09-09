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
- een persoonlijk plaatsnamenfilter (sinds 23-08-2026): een lijst plaatsnamen,
  gescheiden door komma's, met een eigen aan/uit-schakelaar in het
  filterpaneel. Staat het aan, dan worden alleen meldingen getoond waarin een
  van die plaatsnamen voorkomt (in de plaats, de meldingtekst of de standplaats
  van een capcode). De vergelijking gaat op hele woorden, dus "haarlem" raakt
  niet ook Haarlemmermeer. De regel onder de balk meldt hoeveel meldingen het
  filter verbergt. Lijst en schakelaar worden per apparaat bewaard;
- bij een eerste bezoek staat de regio Kennemerland aan; een andere keuze wordt
  per apparaat in de browser onthouden. De standaardregio staat bovenin
  `static/script.js` in de lijst `STANDAARD_REGIOS`;
- een kleur per dienst (brandweer rood, ambulance geel, politie blauw,
  lifeliner paars), in de titel van de melding en in de balk links;
- een kaartpin rechts in elke melding die de herkende locatie in Google Maps
  opent; zie "Locatie voor de kaartpin";
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
  in Google Maps opent. Is er geen locatie herkend, dan is de pin dof en niet
  aan te klikken;
- een vaste balk bovenin met een lopende klok, en knoppen voor de startpagina,
  het geluid, de filters, de landelijke kaart, zoeken en schermvullend;
- de filters (regio, periode, zoeken, verversen) zitten achter de oranje
  filterknop en nemen zo geen ruimte in als ze niet nodig zijn.

Omdat `huisstijl.css` niet meer wordt ingeladen, heeft een wijziging in de
gedeelde huisstijl geen gevolgen voor deze pagina. Het bestand blijft wel in
`static/` staan, zodat `verspreid-huisstijl.ps1` zonder foutmelding blijft
werken.

## Locatie voor de kaartpin

Tot 09-09-2026 ging bijna de hele meldingtekst mee als zoekopdracht naar Google
Maps. Objectnamen, eenheids- en ritnummers en plaatsafkortingen kwamen zo in de
zoekopdracht terecht en zetten de pin regelmatig op een verkeerde plek.

Sinds 09-09-2026 haalt `leesAdres` in `static/script.js` gericht de locatie uit
de tekst, in deze volgorde:

1. **Postcode als ankerpunt.** Staat er een postcode in (`2011 AB`, ook zonder
   spatie geschreven), dan staat het adres ervoor en de plaats erachter.
2. **Straatuitgang.** Anders wordt gezocht naar een woord met een Nederlandse
   straatuitgang (`-straat`, `-laan`, `-weg`, `-plein`, `-hof` en verder).
   Uitgangen die ook in plaatsnamen voorkomen (`-dam`, `-burg`, `-poort`)
   tellen alleen mee als er een huisnummer achter staat.
3. **Laatste twee naamwoorden.** Heeft de melding een prioriteit (`A1`, `P 1`)
   maar geen straatuitgang, dan zijn de laatste twee naamwoorden vrijwel altijd
   de locatie en de plaats, zoals in "Vuursteen Heemskerk".
4. **Snelweg.** Anders telt een weg als `A9` of `N205` als locatie.
5. **Standplaats van de capcode** als de tekst geen plaats geeft.

Het huisnummer wordt apart herkend, ook met een letter of een reeks (`4a`,
`12-14`). Een getal van vier cijfers met een plaatsnaam erachter is geen
huisnummer maar de cijfers van de postcode: in "Paleisstraat 1012 Amsterdam"
wordt `1012` dus als postcode meegegeven en niet als huisnummer.

Weggelaten worden: prioriteit, capcodes, rit- en eenheidsnummers (`13106`,
`12-162`, `BDH-01`, `SGH 88`), objectcodes van zes cijfers, tekst tussen
haakjes zoals `(dia: ja)`, plaatsafkortingen in hoofdletters (`HELLVS`,
`ROTTDM`) en woorden als "Rit", "bon" en "VWS".

De herkende locatie staat in de zweeftekst van de pin, zodat te zien is wat er
naar de kaart gaat. Wordt er niets herkend en geeft ook de capcode geen plaats,
dan blijft de pin dof en zonder koppeling.

De regels staan in `static/script.js` en zijn zonder server te beproeven:

    node --check static/script.js

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

## Publiceren

Deze site heeft geen docroot: de pagina zit in de container en nginx stuurt
door naar `127.0.0.1:8200`. Publiceren betekent dus: de container opnieuw
bouwen. Sinds 09-09-2026 doet het generieke script dat zelf, omdat
`.publiceer-compose` in de wortel van de repo naar `archief` wijst:

    ~/publiceer.sh mijnp2000

Daarvoor liep dat vast op de melding dat `/var/www/mijnp2000` niet bestaat,
want het script zocht het compose-bestand alleen in de wortel van de repo. Met
de hand kan het ook:

    cd ~/mijnp2000-repo/archief
    sudo docker compose up -d --build

Bouwen vanuit `archief/` is nodig, want daar staat `.env` met het
MQTT-wachtwoord. De pagina zit in het image, dus zonder opnieuw bouwen blijft
de oude versie draaien.

## robots.txt

De pagina hoort niet in zoekmachines. Omdat er geen docroot is, komt
`robots.txt` uit de gedeelde map `/var/www/robots/` op de server. Het blok
staat in `nginx-mijnp2000.conf` en moet in het 443-blok terechtkomen, met
`auth_request off;` zodat het bestand zonder aanmelden te lezen is.
Controleren:

    curl -s -o /dev/null -w "%{http_code}\n" https://mijnp2000.lab023.nl/robots.txt

Bij `200` is het goed; bij `302` gaat het verzoek nog langs de aanmelding.

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

   Controleer daarna dat `include snippets/lab023-login.conf;`,
   `include snippets/lab023-blokkeer.conf;` en het blok voor `/robots.txt` in
   het 443-blok staan.
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
