#!/bin/sh
# Start de ontvangstketen: rtl_fm stemt af op 169,65 MHz en demoduleert FM,
# multimon-ng decodeert het FLEX-protocol, publiceer.py leest de tekstregels
# en zet ze op MQTT.
#
# De instelling RTL_CMD kan het rtl_fm-commando overschrijven, bijvoorbeeld om
# gain (-g) of correctie (-p) toe te voegen als de ontvangst matig is.
set -e

RTL_CMD="${RTL_CMD:-rtl_fm -f 169.65M -M fm -s 22050 -l 0}"

echo "P2000-ontvanger start: ${RTL_CMD} | multimon-ng -a FLEX"
exec sh -c "${RTL_CMD} 2>/dev/null | multimon-ng -a FLEX -t raw /dev/stdin 2>/dev/null | python3 -u /app/publiceer.py"
