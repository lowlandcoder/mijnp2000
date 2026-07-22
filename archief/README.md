# P2000-archief

De archiefpagina `mijnp2000.lab023.nl`: een kleine backend die de
P2000-meldingen van de broker meeleest, opslaat in een SQLite-database en toont
in de Lab023-huisstijl, met filter op regio en een instelbare periode tot zeven
dagen.

Deze container draait op de lab023-server, naast nginx en de broker. De
ontvanger (`../ontvanger`) draait op de sdr-server en publiceert de meldingen op
MQTT; deze backend is een van de afnemers.

## Bestanden

- `app.py` — de backend: leest MQTT mee, slaat op in SQLite, vertaalt capcodes
  naar regio, schoont oude meldingen op en biedt de pagina en een JSON-API.
- `static/` — de pagina: `index.html`, `style.css`, `script.js`, `huisstijl.css`.
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
- een steunkleur per discipline (brandweer rood, ambulance geel, politie blauw,
  lifeliner groen), zowel in de badge als in de rand van de melding;
- een kaartpin per melding die de locatie in Google Maps opent;
- een knop naar de landelijke live-kaart van p2000.page;
- de vertaling per capcode (eenheid, plaats en regio) onder elke melding.

Meldingen ouder dan de bewaartermijn (standaard zeven dagen, instelbaar via
`RETENTIE_DAGEN`) worden elk uur verwijderd.

## Capcode-database: nodig voor het regiofilter

Het filteren op regio werkt alleen met een capcode-database. Zonder die database
worden de meldingen wel opgeslagen en getoond, maar blijft het regioveld leeg.

Het bestand `data/capcodes.csv` heeft vijf kolommen: `capcode`, `regio`,
`discipline`, `plaats`, `omschrijving`. De `omschrijving` levert de vertaling
per capcode op de pagina (bijvoorbeeld "Ambulance 12-162").

De landelijke lijst wordt gemaakt met de omzetter uit `tools/`, uit de openbare
export van p2000.bommel.net (alle veiligheidsregio's):

    curl -s -o /tmp/bommel.csv https://p2000.bommel.net/cap2csv.php
    python3 tools/converteer_capcodes.py /tmp/bommel.csv data/capcodes.csv
    sudo docker compose restart mijnp2000-archief

De omzetter herkent ook het formaat van cyberjunky/RTL-SDR-P2000Receiver-HA.
Het aantal geladen capcodes staat in het logboek bij het opstarten. De lijst
veroudert langzaam; verversen kan door deze drie regels opnieuw te draaien.

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

Het wachtwoord staat in `.env` en blijft buiten de repository. De database en de
echte capcode-lijst staan in `data/` en worden niet meegecommit.
