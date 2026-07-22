#!/usr/bin/env python3
"""Zet een capcode-bron om naar het capcodes.csv dat de archiefbackend gebruikt.

Herkent twee openbare bronnen automatisch:

  * p2000.bommel.net (landelijk), export via https://p2000.bommel.net/cap2csv.php
    kolommen o.a.: Code, Discipline, Regio, Korps/sector, Plaats, Omschrijving
  * cyberjunky/RTL-SDR-P2000Receiver-HA (db_capcodes.txt)
    kolommen: capcode, discipline, region, location, description, remark

De uitvoer heeft de vier kolommen die de backend verwacht:
    capcode,regio,discipline,plaats

De capcode wordt links met nullen aangevuld tot negen cijfers, zodat die
overeenkomt met wat de ontvanger publiceert (bijvoorbeeld 1500122 -> 001500122).

Gebruik:
    python3 converteer_capcodes.py <bron.csv> <uitvoer.csv>
"""

import csv
import sys


def kolom(velden, *namen):
    """Vind de kolomnaam die overeenkomt met een van de gegeven namen."""
    laag = {v.lower().strip(): v for v in velden}
    for naam in namen:
        if naam in laag:
            return laag[naam]
    return None


def main():
    if len(sys.argv) != 3:
        print("Gebruik: converteer_capcodes.py <bron.csv> <uitvoer.csv>")
        sys.exit(1)
    bron, uitvoer = sys.argv[1], sys.argv[2]

    with open(bron, encoding="utf-8", errors="replace") as bestand:
        tekst = bestand.read()

    # Sla eventuele voorregels vóór de kopregel over.
    regels = tekst.splitlines()
    start = 0
    for i, regel in enumerate(regels):
        laag = regel.lower()
        if ("capcode" in laag or "code" in laag) and ("regio" in laag or "region" in laag):
            start = i
            break
    schoon = "\n".join(regels[start:])

    # Scheidingsteken raden (komma, puntkomma of tab).
    try:
        dialect = csv.Sniffer().sniff(schoon[:2000], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel

    lezer = csv.DictReader(schoon.splitlines(), dialect=dialect)
    velden = lezer.fieldnames or []
    k_code = kolom(velden, "capcode", "code")
    k_regio = kolom(velden, "regio", "region")
    k_disc = kolom(velden, "discipline")
    k_plaats = kolom(velden, "plaats", "location")
    if not k_code:
        print("Geen capcode-kolom gevonden. Kopregel:", velden)
        sys.exit(1)

    rijen = []
    for rij in lezer:
        ruw = (rij.get(k_code) or "").strip()
        cijfers = "".join(c for c in ruw if c.isdigit())
        if not cijfers:
            continue
        rijen.append(
            {
                "capcode": cijfers.zfill(9),
                "regio": (rij.get(k_regio) or "").strip() if k_regio else "",
                "discipline": (rij.get(k_disc) or "").strip() if k_disc else "",
                "plaats": (rij.get(k_plaats) or "").strip() if k_plaats else "",
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
