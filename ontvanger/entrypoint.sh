#!/bin/sh
# Start de ontvangstketen: rtl_fm stemt af op 169,65 MHz en demoduleert FM,
# multimon-ng decodeert het FLEX-protocol, publiceer.py leest de tekstregels
# en zet ze op MQTT.
#
# De instelling RTL_CMD kan het rtl_fm-commando overschrijven, bijvoorbeeld om
# gain (-g) of correctie (-p) toe te voegen als de ontvangst matig is.
set -e

RTL_CMD="${RTL_CMD:-rtl_fm -f 169.65M -M fm -s 22050 -l 0}"

# DEBUG=1 laat de meldingen van rtl_fm en multimon-ng in de logs zien
# (afstemmen, apparaat openen, decoderen). Handig om te controleren of de
# stick werkt. Zet op 0 zodra alles loopt, om de logs rustig te houden.
DEBUG="${DEBUG:-1}"

echo "P2000-ontvanger start: ${RTL_CMD} | multimon-ng -a FLEX"
if [ "${DEBUG}" = "1" ]; then
    exec sh -c "${RTL_CMD} | multimon-ng -a FLEX -t raw /dev/stdin | python3 -u /app/publiceer.py"
else
    exec sh -c "${RTL_CMD} 2>/dev/null | multimon-ng -a FLEX -t raw /dev/stdin 2>/dev/null | python3 -u /app/publiceer.py"
fi
