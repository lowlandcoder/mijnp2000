# Archief-backend voor P2000: leest MQTT mee, slaat op in SQLite en toont de
# pagina mijnp2000.lab023.nl.

FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py /app/app.py
COPY static /app/static

# De database en het capcode-bestand staan in een gekoppeld volume.
VOLUME ["/app/data"]
EXPOSE 8000

CMD ["python", "app.py"]
