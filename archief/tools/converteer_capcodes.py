#!/usr/bin/env python3
"""Zet een of meer capcode-bronnen om naar het capcodes.csv van de archiefbackend.

Herkent drie formaten automatisch:

  * p2000.bommel.net (landelijk), export via https://p2000.bommel.net/cap2csv.php
    Puntkomma-gescheiden, met aanhalingstekens en zonder kopregel. Vaste
    kolomvolgorde: Code; Discipline; Regio; Plaats; Omschrijving; Short.
  * cyberjunky/RTL-SDR-P2000Receiver-HA (db_capcodes.txt)
    Komma-gescheiden, met kopregel: capcode, discipline, region, location, ...
  * Het eigen uitvoerformaat zelf (capcodes.csv), zodat een bestaande lijst als
    bron kan dienen bij het samenvoegen.

Bij meerdere bronnen geldt: de eerste bron wint. Een capcode uit een latere
bron wordt alleen toegevoegd als die nog niet bestaat, of als die meer velden
gevuld heeft dan de eerdere regel (dan worden alleen de lege velden aangevuld).

Regionamen worden gelijkgetrokken naar de schrijfwijze van p2000.bommel.net
(bijvoorbeeld "Brabant-Zuidoost" wordt "Brabant Zuid-Oost"), zodat het
regiofilter op de pagina geen dubbele regio's toont.

De uitvoer heeft de vijf kolommen die de backend verwacht:
    capcode,regio,discipline,plaats,omschrijving

De capcode wordt links met nullen aangevuld tot negen cijfers, zodat die
overeenkomt met wat de ontvanger publiceert (bijvoorbeeld 0100000 -> 000100000).

Gebruik:
    python3 converteer_capcodes.py <bron1.csv> [bron2.csv ...] <uitvoer.csv>
"""

import csv
import re
import sys

# Canonieke regionamen (schrijfwijze van p2000.bommel.net).
CANONIEKE_REGIOS = [
    "Amsterdam-Amstelland",
    "Brabant Noord",
    "Brabant Zuid-Oost",
    "Drenthe",
    "Flevoland",
    "Friesland",
    "Gelderland Midden",
    "Gelderland Zuid",
    "Gooi en Vechtstreek",
    "Groningen",
    "Haaglanden",
    "Hollands Midden",
    "IJsselland",
    "Kennemerland",
    "Landelijk",
    "Limburg Noord",
    "Limburg Zuid",
    "Midden- en West-Brabant",
    "Noord- en Oost-Gelderland",
    "Noord-Holland Noord",
    "Rotterdam-Rijnmond",
    "Twente",
    "Utrecht",
    "Zaanstreek-Waterland",
    "Zeeland",
    "Zuid-Holland Zuid",
]

def sleutel(naam):
    """Vergelijkingssleutel: kleine letters, alleen letters en cijfers."""
    return re.sub(r"[^a-z0-9]", "", naam.lower())

# Sleutel -> canonieke naam, plus afwijkende schrijfwijzen uit andere bronnen.
REGIO_MAP = {sleutel(naam): naam for naam in CANONIEKE_REGIOS}
REGIO_MAP.update({
    "noordoostgelderland": "Noord- en Oost-Gelderland",  # cyberjunky
    "ijsseland": "IJsselland",                            # tikfout in cyberjunky
    "26": "Landelijk",                                    # Kustwacht/KNRM-code
})

def normaliseer_regio(naam):
    naam = naam.strip()
    return REGIO_MAP.get(sleutel(naam), naam)


def lees_bron(pad):
    """Lees één bronbestand en lever rijen (capcode, regio, discipline, plaats, omschrijving)."""
    with open(pad, encoding="utf-8", errors="replace") as bestand:
        regels = bestand.read().splitlines()
    regels = [r for r in regels if r.strip() and not r.lstrip().startswith("#")]
    if not regels:
        return []

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
                zoek(rij, "omschrijving", "description"),
            )
    else:
        # bommel-volgorde: code; discipline; regio; plaats; omschrijving; short
        databron = rijen_ruw

        def velden(rij):
            haal = lambda i: rij[i] if i < len(rij) else ""
            return haal(0), haal(2), haal(1), haal(3), haal(4)

    rijen = []
    for rij in databron:
        code, regio, discipline, plaats, omschrijving = velden(rij)
        cijfers = "".join(c for c in code if c.isdigit())
        if not cijfers:
            continue
        rijen.append(
            {
                "capcode": cijfers.zfill(9),
                "regio": normaliseer_regio(regio),
                "discipline": discipline.strip(),
                "plaats": plaats.strip(),
                "omschrijving": omschrijving.strip(),
            }
        )
    return rijen


def main():
    if len(sys.argv) < 3:
        print("Gebruik: converteer_capcodes.py <bron1.csv> [bron2.csv ...] <uitvoer.csv>")
        sys.exit(1)
    bronnen, uitvoer = sys.argv[1:-1], sys.argv[-1]

    per_capcode = {}
    telling = []
    for pad in bronnen:
        rijen = lees_bron(pad)
        if not rijen:
            print(f"Bronbestand {pad} is leeg of onleesbaar.")
            sys.exit(1)
        nieuw = aangevuld = 0
        for rij in rijen:
            bestaand = per_capcode.get(rij["capcode"])
            if bestaand is None:
                per_capcode[rij["capcode"]] = rij
                nieuw += 1
            else:
                # Eerste bron wint; alleen lege velden aanvullen.
                gevuld = False
                for veld in ("regio", "discipline", "plaats", "omschrijving"):
                    if not bestaand[veld] and rij[veld]:
                        bestaand[veld] = rij[veld]
                        gevuld = True
                if gevuld:
                    aangevuld += 1
        telling.append(f"{pad}: {len(rijen)} regels, {nieuw} nieuw, {aangevuld} aangevuld")

    rijen = [per_capcode[c] for c in sorted(per_capcode)]

    with open(uitvoer, "w", newline="", encoding="utf-8") as bestand:
        schrijver = csv.DictWriter(
            bestand, fieldnames=["capcode", "regio", "discipline", "plaats", "omschrijving"]
        )
        schrijver.writeheader()
        schrijver.writerows(rijen)

    for regel in telling:
        print(regel)
    regios = sorted({r["regio"] for r in rijen if r["regio"]})
    print(f"{len(rijen)} capcodes weggeschreven naar {uitvoer}.")
    print(f"Regio's ({len(regios)}): {', '.join(regios)}")


if __name__ == "__main__":
    main()
