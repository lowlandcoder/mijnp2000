# Ontvanger voor P2000 (169,65 MHz, FLEX).
# rtl_fm stemt af en demoduleert, multimon-ng decodeert FLEX, en publiceer.py
# zet elke melding als JSON op een MQTT-onderwerp.

FROM debian:bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        rtl-sdr \
        multimon-ng \
        python3 \
        python3-paho-mqtt \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY publiceer.py /app/publiceer.py
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

ENTRYPOINT ["/app/entrypoint.sh"]
