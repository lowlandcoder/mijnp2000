# Waakhond MijnP2000

Bewaakt of de P2000-verwerking nog loopt, herstart de ontvanger als dat niet
zo is, en meldt dat via mail en via Home Assistant. Draait op de
**lab023-server** (server023), elk kwartier gestart door een systemd-timer.

## Waarom dit nodig is

De ontvanger draait op de sdr-server als container `p2000-ontvanger`, met de
keten `rtl_fm | multimon-ng | publiceer.py`.

Valt `rtl_fm` weg, dan krijgt `publiceer.py` einde-invoer, stopt de container
en start Docker hem vanzelf opnieuw. Dat gaat vanzelf goed.

Het geval dat wel misgaat: de keten leeft, maar `multimon-ng` decodeert niets
meer, bijvoorbeeld na het wisselen van de antenne of na een vastgelopen stick.
De container heet dan nog steeds "draait", er komt niets meer op MQTT en de
pagina loopt stil achter. Docker ziet daar niets van, en een gewone
herstartregel helpt dus niet.

## Hoe de controle werkt

1. De ontvanger zet elke minuut een **bewaard** bericht op `p2000/status` met
   de tijd van de laatste gedecodeerde melding. Zie `../ontvanger/README.md`.
2. De waakhond haalt die stand op. Zolang de laatste melding recent is, is
   hij klaar; de sdr-server wordt dan niet eens bevraagd.
3. Duurt de stilte langer dan `STIL_DREMPEL_MINUTEN`, of is de hartslag zelf
   oud, dan vraagt de waakhond de containerstand op bij de bedieningsdienst
   `mijnsdr-bediening` op de sdr-server.
4. Draait de container, dan vraagt hij een herstart met
   `POST /api/herstart`, en meldt hij dat.
5. Draait de container niet, dan gebeurt er niets meer dan melden. Een
   stilstaande container is met opzet gestopt, en dat hoort de waakhond niet
   te doorkruisen.

## Uitkomsten

| Soort | Wat er aan de hand is | Wat de waakhond doet |
| --- | --- | --- |
| `in_orde` | er is recent nog gedecodeerd | niets; alleen melden als het net nog mis was |
| `verwerking_gestopt` | ontvanger draait, maar decodeert niets meer | herstarten en melden |
| `hartslag_oud` | het proces in de container reageert niet meer | herstarten en melden |
| `geen_hartslag` | er staat niets op `p2000/status` | herstarten en melden |
| `container_uit` | de container draait niet | alleen melden |
| `onbereikbaar` | de bedieningsdienst antwoordt niet | alleen melden |
| `limiet` | herstarten heeft niet geholpen | alleen melden |

## Remmen

Een herstart repareert een vastgelopen stick of proces. Een slecht afgestemde
antenne repareert hij niet. Zonder rem zou de waakhond dan elk kwartier
opnieuw herstarten. Daarom:

- controle elk kwartier, maar pas ingrijpen na 30 minuten stilte;
- na een herstart 5 minuten rust, zodat de ontvanger op gang kan komen;
- hoogstens 3 herstarts per 6 uur, daarna alleen nog een melding met de tekst
  dat herstarten niet helpt;
- hetzelfde probleem wordt hoogstens eens per 6 uur opnieuw gemeld;
- zodra de verwerking weer loopt, volgt een herstelmelding.

De stand tussen twee controles staat in
`/var/lib/mijnp2000-waakhond/status.json`.

## Melden

Twee kanalen, naar het patroon van mijnradar. Een kanaal staat aan zodra de
instellingen die het nodig heeft gevuld zijn; staat er geen enkel kanaal aan,
dan controleert de waakhond wel en meldt hij niet.

- **Mail** via SMTP naar de adressen in `ALERT_NAAR`.
- **Home Assistant** via een bericht op `p2000/waakhond`. De automatisering
  staat in `../homeassistant/`. Het bericht bevat een kant-en-klare `titel` en
  `tekst`, dus Home Assistant hoeft niets uit te rekenen.

Het bericht gaat zonder retain de deur uit. Met een bewaard bericht zou Home
Assistant bij elke herstart de laatste melding opnieuw binnenkrijgen en
opnieuw de telefoon laten trillen.

## Inrichting op de lab023-server (eenmalig)

1. Python-koppeling voor MQTT installeren:

       sudo apt install python3-paho-mqtt

2. Het script plaatsen:

       sudo mkdir -p /opt/mijnp2000-waakhond
       sudo cp ~/mijnp2000/waakhond/waakhond.py /opt/mijnp2000-waakhond/

3. De instellingen plaatsen en invullen:

       sudo mkdir -p /etc/mijnp2000
       sudo cp ~/mijnp2000/waakhond/waakhond.env.voorbeeld /etc/mijnp2000/waakhond.env
       sudo chmod 600 /etc/mijnp2000/waakhond.env
       sudo nano /etc/mijnp2000/waakhond.env

   Zet `ALLEEN_MELDEN=1` zolang de waakhond nog wordt beproefd.

4. Beproeven zonder timer:

       sudo -u peter env $(sudo cat /etc/mijnp2000/waakhond.env | grep -v '^#' | xargs) \
         python3 /opt/mijnp2000-waakhond/waakhond.py --stand

5. De timer aanzetten:

       sudo cp ~/mijnp2000/waakhond/systemd/mijnp2000-waakhond.* /etc/systemd/system/
       sudo systemctl daemon-reload
       sudo systemctl enable --now mijnp2000-waakhond.timer

   Stand en uitvoer bekijken met `systemctl list-timers` en
   `journalctl -u mijnp2000-waakhond.service -n 30`.

6. Werkt alles, dan `ALLEEN_MELDEN=0` zetten en de timer opnieuw laten lopen.

## Beproeven

| Opdracht | Wat het doet |
| --- | --- |
| `waakhond.py --stand` | alleen kijken: hartslag, oordeel, containerstand, kanalen |
| `waakhond.py --droog` | een hele ronde, wel melden maar niet herstarten |
| `waakhond.py --proef` | een proefmelding over alle kanalen die aanstaan |
| `systemctl start mijnp2000-waakhond.service` | een ronde nu, zoals de timer die doet |

Meekijken op de hartslag zelf:

    mosquitto_sub -h 192.168.2.38 -u p2000 -P <wachtwoord> -t 'p2000/status' -v

## Let op

- De waakhond spreekt de bedieningsdienst rechtstreeks aan op poort 8330 en
  niet via `mijnsdr.lab023.nl`, want die weg gaat langs de centrale
  aanmelding. De kop `X-Bedien-Sleutel` stuurt hij dus zelf mee.
- `BEDIEN_SLEUTEL` moet gelijk zijn aan die in `/opt/mijnsdr-bediening/.env`
  op de sdr-server. Wijkt hij af, dan volgt een 403 en lukt de herstart niet.
- Rolt de ontvanger nog de oude versie zonder hartslag uit, dan ziet de
  waakhond `geen_hartslag` en gaat hij herstarten. Eerst de ontvanger
  bijwerken, daarna pas de timer aanzetten.
- Wordt de drempel `STIL_DREMPEL_MINUTEN` korter gezet dan het kwartier
  tussen twee controles, dan kan er worden herstart terwijl de ontvanger nog
  aan het opstarten is.
