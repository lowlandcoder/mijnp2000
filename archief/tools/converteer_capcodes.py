#!/usr/bin/env python3
"""Zet een capcode-bron om naar het capcodes.csv dat de archiefbackend gebruikt.

Herkent twee openbare bronnen automatisch:

  * p2000.bommel.net (landelijk), export via https://p2000.bommel.net/cap2csv.php
    Puntkomma-gescheiden, met aanhalingstekens en zonder kopregel. Vaste
    kolomvolgorde: Code; Discipline; Regio; Plaats; Omschrijving; Short.
  * cyberjunky/RTL-SDR-P2000Receiver-HA (db_capcodes.txt)
    Komma-gescheiden, met kopregel: capcode, discipline, region, location, ...

De uitvoer heeft de vier kolommen die de backend verwacht:
    capcode,regio,discipline,plaats

De capcode wordt links met nullen aangevuld tot negen cijfers, zodat die
overeenkomt met wat de ontvanger publiceert (bijvoorbeeld 0100000 -> 000100000).

Gebruik:
    python3 converteer_capcodes.py <bron.csv> <uitvoer.csv>
"""

import csv
import sys


def main():
    if len(sys.argv) != 3:
        print("Gebruik: converteer_capcodes.py <bron.csv> <uitvoer.csv>")
        sys.exit(1)
    bron, uitvoer = sys.argv[1], sys.argv[2]

    with open(bron, encoding="utf-8", errors="replace") as bestand:
        regels = bestand.read().splitlines()
    regels = [r for r in regels if r.strip()]
    if not regels:
        print("Bronbestand is leeg.")
        sys.exit(1)

    # Scheidingsteken bepalen aan de hand van de eerste regel.
    delim = ";" if regels[0].count(";") >= regels[0].count(",") else ","
    rijen_ruw = list(csv.reader(regels, delimiter=delim))

    # Is er een kopregel? (bevat 'code' of 'capcode')
    kop = [c.strip().lower() for c in rijen_ruw[0]]
    heeft_kop = any(c in ("code", "capcode") for c in kop)

    if heeft_kop:
        index = {naam: i for i, naam in enumerate(kop)}

        def zoek(rij, *namen):
            for naam in namen:
                i = index.get(naam)
                if i is not None and i < len(rij):
                    return rij[i]
            return ""

        databron = rijen_ruw[1:]

        def velden(rij):
            return (
                zoek(rij, "capcode", "code"),
                zoek(rij, "regio", "region"),
                zoek(rij, "discipline"),
                zoek(rij, "plaats", "location"),
            )
    else:
        # bommel-volgorde: code; discipline; regio; plaats; omschrijving; short
        databron = rijen_ruw

        def velden(rij):
            haal = lambda i: rij[i] if i < len(rij) else ""
            return haal(0), haal(2), haal(1), haal(3)

    rijen = []
    for rij in databron:
        code, regio, discipline, plaats = velden(rij)
        cijfers = "".join(c for c in code if c.isdigit())
        if not cijfers:
            continue
        rijen.append(
            {
                "capcode": cijfers.zfill(9),
                "regio": regio.strip(),
                "discipline": discipline.strip(),
                "plaats": plaats.strip(),
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
