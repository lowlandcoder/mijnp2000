# Ontvanger voor P2000 (169,65 MHz, FLEX).
# rtl_fm stemt af en demoduleert, multimon-ng decodeert FLEX, en publiceer.py
# zet elke melding als JSON op een MQTT-onderwerp.
#
# Belangrijk: de gebruikte stick is een RTL-SDR Blog V4. Die heeft het
# stuurprogramma van rtl-sdr-blog nodig; de standaardversie uit Debian
# ondersteunt de V4 niet en geeft "PLL not locked" zonder ontvangst. Daarom
# wordt dat stuurprogramma hieronder uit de bron gebouwd.

# --- Bouwlaag: het rtl-sdr-blog-stuurprogramma compileren ------------------
FROM debian:bookworm-slim AS build

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates git cmake build-essential pkg-config \
        libusb-1.0-0-dev \
    && git clone https://github.com/rtlsdrblog/rtl-sdr-blog /tmp/src \
    && cd /tmp/src && mkdir build && cd build \
    && cmake ../ -DINSTALL_UDEV_RULES=ON -DDETACH_KERNEL_DRIVER=ON \
    && make -j"$(nproc)" \
    && make install DESTDIR=/out

# --- Draailaag: alleen wat nodig is om te draaien --------------------------
FROM debian:bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        libusb-1.0-0 \
        multimon-ng \
        python3 \
        python3-paho-mqtt \
    && rm -rf /var/lib/apt/lists/*

# Het zelfgebouwde stuurprogramma en de rtl-tools overnemen.
COPY --from=build /out/usr/local /usr/local
RUN ldconfig

WORKDIR /app
COPY publiceer.py /app/publiceer.py
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

ENTRYPOINT ["/app/entrypoint.sh"]
