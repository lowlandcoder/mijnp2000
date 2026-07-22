#!/usr/bin/env python3
"""Zet een capcode-bron om naar het capcodes.csv dat de archiefbackend gebruikt.

De bron heeft de kolommen van cyberjunky/RTL-SDR-P2000Receiver-HA:
    capcode,discipline,region,location,description,remark
De uitvoer heeft de vier kolommen die de backend verwacht:
    capcode,regio,discipline,plaats

Eventuele voorregels vóór de kopregel (bijvoorbeeld van een download) worden
overgeslagen. Gebruik:

    python3 converteer_capcodes.py db_capcodes.txt ../data/capcodes.csv

Een vollere, landelijke bron met dezelfde kolommen kan zo ook worden omgezet.
"""

import csv
import sys


def main():
    if len(sys.argv) != 3:
        print("Gebruik: converteer_capcodes.py <bron> <uitvoer.csv>")
        sys.exit(1)
    bron, uitvoer = sys.argv[1], sys.argv[2]

    with open(bron, encoding="utf-8") as bestand:
        regels = bestand.read().splitlines()

    # Zoek de kopregel; alles ervoor overslaan.
    start = next(
        (i for i, regel in enumerate(regels) if regel.startswith("capcode,discipline,region")),
        None,
    )
    if start is None:
        print("Kopregel 'capcode,discipline,region,...' niet gevonden in de bron.")
        sys.exit(1)

    rijen = []
    for rij in csv.DictReader(regels[start:]):
        code = (rij.get("capcode") or "").strip()
        if not code.isdigit():
            continue
        rijen.append(
            {
                "capcode": code,
                "regio": (rij.get("region") or "").strip(),
                "discipline": (rij.get("discipline") or "").strip(),
                "plaats": (rij.get("location") or "").strip(),
            }
        )

    with open(uitvoer, "w", newline="", encoding="utf-8") as bestand:
        schrijver = csv.DictWriter(bestand, fieldnames=["capcode", "regio", "discipline", "plaats"])
        schrijver.writeheader()
        schrijver.writerows(rijen)

    regios = sorted({r["regio"] for r in rijen if r["regio"]})
    print(f"{len(rijen)} capcodes omgezet naar {uitvoer}.")
    print(f"Regio's ({len(regios)}): {', '.join(regios)}")


if __name__ == "__main__":
    main()
