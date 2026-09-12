// Gedeelde functies van MijnP2000: de kleur per dienst en de locatie uit een
// meldingtekst. Twee pagina's gebruiken dit bestand: de archiefpagina (lijst met
// meldingen en een pin naar Google Maps) en de kaartpagina (pin op de eigen
// kaart). Het bevat alleen functies en geen code die de pagina aanraakt, zodat
// het in beide pagina's voor het eigen script kan worden ingeladen.

/* ---------- Kleur per dienst ---------- */
function dienstKlasse(tekst) {
  const t = (tekst || "").toLowerCase();
  if (/lifeliner|traumaheli|\bmmt\b|mobiel medisch/.test(t)) return "lifeliner";
  if (t.includes("brandweer")) return "brandweer";
  if (t.includes("ambulance")) return "ambulance";
  if (t.includes("politie")) return "politie";
  return "overig";
}

function hoofdKlasse(m) {
  const alles = (m.bericht || "") + " " + (m.disciplines || "");
  if (/lifeliner|traumaheli|\bmmt\b/i.test(alles)) return "lifeliner";
  for (const disc of (m.disciplines || "").split(",").map((d) => d.trim()).filter(Boolean)) {
    const k = dienstKlasse(disc);
    if (k !== "overig") return k;
  }
  return "overig";
}

function prioKlasse(bericht) {
  if (/\b(A1|P\s?1|PRIO\s?1|GRIP)\b/i.test(bericht)) return "prio1";
  if (/\b(A2|P\s?2|PRIO\s?2)\b/i.test(bericht)) return "prio2";
  return "";
}

/* ---------- Tijd ---------- */
function minutenGeleden(iso) {
  const d = new Date(iso);
  if (isNaN(d)) return null;
  return Math.max(0, Math.round((Date.now() - d.getTime()) / 60000));
}

const PIN_SVG = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 2a7 7 0 0 0-7 7c0 5.2 7 13 7 13s7-7.8 7-13a7 7 0 0 0-7-7zm0 9.5A2.5 2.5 0 1 1 12 6.5a2.5 2.5 0 0 1 0 5z"></path></svg>';

/* ---------- Locatie uit de meldingtekst halen ----------
   Een P2000-melding bevat naast de locatie ook prioriteit, capcodes,
   eenheids- en ritnummers, plaatsafkortingen en objectcodes. Die woorden
   gingen eerder mee in de zoekopdracht naar de kaart, waardoor de pin op een
   verkeerde plek uitkwam. Daarom wordt nu gericht gezocht naar straatnaam,
   huisnummer, postcode en plaats. Levert dat niets op, dan valt de pin terug
   op de plaats van de capcode; is ook die er niet, dan blijft de pin dof en
   zonder koppeling. */

const HUISNUMMER = /^\d{1,4}(?:[-\/]\d{1,4})?[a-zA-Z]?$/;

const TUSSENVOEGSEL = new Set([
  "van", "de", "den", "der", "ter", "te", "op", "aan", "het", "'t", "in",
  "'s", "ten", "d'", "la", "le", "du",
]);

// Woorddelen waar een Nederlandse straatnaam bijna altijd op eindigt.
const STRAAT_STERK = /(straat|straatje|straatweg|dwarsstraat|laan|laantje|weg|baan|pad|plein|pleintje|markt|kade|dijk|singel|gracht|hof|dreef|park|plantsoen|boulevard|steeg|wal|kanaal|haven|tunnel|viaduct|rotonde|allee|lei|erf|vest|gaarde|hoeve|weide|donk|akker|veld|kamp)$/i;

// Zwakkere uitgangen: die komen ook in plaatsnamen voor (Amsterdam, Zaandam,
// Middelburg), dus die tellen alleen mee als er een huisnummer achter staat.
const STRAAT_ZWAK = /(dam|berg|burg|poort|brug|ring|hoek|es|hout|horst|beek|wetering|vaart|sloot|tocht|werf|gang|kolk|bos|duin|wijk|kerk|molen|zoom|rade|schans|terp)$/i;

// Woorden die nooit een straatnaam of plaatsnaam zijn.
const RUIS = new Set([
  "ambulance", "ambulancepost", "ambu", "brandweer", "politie", "lifeliner",
  "traumahelikopter", "mmt", "oms", "prio", "rit", "grip", "inzet", "post",
  "assistentie", "melding", "brand", "reanimatie", "ongeval", "letsel",
  "aanrijding", "spoed", "nederland", "dia", "directe", "hectometer", "hmp",
  "afrit", "oprit", "richting", "nabij", "gebouw", "woning", "voertuig",
  "container", "automatisch", "brandalarm", "testoproep", "testmelding",
  "test", "oefening", "code", "contact", "meldkamer", "bon", "seh", "einde",
  "bel", "bellen", "graag", "passage", "stank", "meting", "flat", "nablussen",
  "vervoer", "loze", "storing", "controle",
]);

// Een melding met een prioriteit ervoor gaat over een inzet op een locatie.
const PRIORITEIT = /^\s*(?:A\s?[0-2]|B\s?[0-2]|P\s?[1-3]|PRIO\s?[1-3]|GRIP\s?\d)\b/i;

function schoonBericht(tekst) {
  return (tekst || "")
    .replace(/\([^)]*\)/g, " ")                       // (dia: ja) en andere haakjes
    .replace(/\b\d{1,2}:\d{2}(?::\d{2})?\b/g, " ")    // tijdstippen
    .replace(/\brit:?\s*\d+/gi, " ")                  // ritnummer
    .replace(/\bprio\s*\d\b/gi, " ")                  // prioriteit
    .replace(/\b[A-Z]{2,6}[-\s]?\d{2}\b/g, " ")       // eenheden als BDH-01 en SGH 88
    .replace(/\b\d{2}-\d{3}\b/g, " ")                 // eenheden als 12-162
    .replace(/\b\d{5,}\b/g, " ")                      // capcodes, rit- en objectcodes
    .replace(/\b(\d{4})\s?([A-Za-z]{2})\b/g, "$1 $2") // postcode in twee delen
    .replace(/[,;|:+]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

const isWoord = (w) => /^[A-Za-zÀ-ÿ'’.\-]{2,}$/.test(w || "");
const heeftHoofdletter = (w) => /^[A-ZÀ-Ý'’]/.test(w || "");
const isAfkorting = (w) => /^[A-Z]{2,}$/.test(w || "");
const isNaamwoord = (w) =>
  isWoord(w) && heeftHoofdletter(w) && !isAfkorting(w) && !RUIS.has(w.toLowerCase());

/* Bouwt de straatnaam op vanaf het laatste woord ervan en neemt tussenvoegsels
   en hoogstens twee voorafgaande naamwoorden mee, zodat "Jan van Galenstraat"
   en "Paulus Potterstraat" heel blijven. */
function bouwStraat(woorden, eind, plaats) {
  const plaatsdelen = (plaats || "").toLowerCase().split(" ");
  let start = eind;
  let erbij = 0;
  while (start - 1 >= 0 && erbij < 2) {
    const vorig = woorden[start - 1];
    if (TUSSENVOEGSEL.has(vorig.toLowerCase())) { start--; continue; }
    if (!isNaamwoord(vorig)) break;
    if (plaatsdelen.includes(vorig.toLowerCase())) break;
    start--;
    erbij++;
  }
  // Een tussenvoegsel zonder hoofdletter vooraan hoort niet bij de naam.
  while (start < eind && TUSSENVOEGSEL.has(woorden[start].toLowerCase()) &&
         !heeftHoofdletter(woorden[start])) start++;
  return woorden.slice(start, eind + 1).join(" ");
}

/* Plaatsnaam: hoogstens twee aaneengesloten naamwoorden, zodat
   "Hoogvliet Rotterdam" heel blijft en "Hoorn NH" niet de provincie meepakt. */
function leesPlaats(woorden, vanaf) {
  const delen = [];
  for (let i = vanaf; i < woorden.length && delen.length < 2; i++) {
    if (!isNaamwoord(woorden[i])) break;
    delen.push(woorden[i]);
  }
  return delen.join(" ");
}

function leesAdres(bericht, plaatsUitCapcode) {
  const ruw = bericht || "";
  const tekst = schoonBericht(ruw);
  const woorden = tekst.split(" ").filter(Boolean);
  const uit = { straat: "", nummer: "", postcode: "", plaats: "" };

  /* 1. De postcode is het betrouwbaarste ankerpunt: ervoor staat het adres,
        erachter de plaats. */
  let pc = -1;
  for (let i = 0; i + 1 < woorden.length; i++) {
    if (/^\d{4}$/.test(woorden[i]) && /^[A-Za-z]{2}$/.test(woorden[i + 1])) { pc = i; break; }
  }
  if (pc > 0) {
    uit.postcode = woorden[pc] + " " + woorden[pc + 1].toUpperCase();
    uit.plaats = leesPlaats(woorden, pc + 2);
    let eind = pc - 1;
    if (HUISNUMMER.test(woorden[eind])) { uit.nummer = woorden[eind]; eind--; }
    if (eind >= 0 && isWoord(woorden[eind])) uit.straat = bouwStraat(woorden, eind, uit.plaats);
  }

  /* 1b. Bij een verplaatsing naar een ambulancepost staat de plaats juist vóór
         de straat ("Ambulancepost Moordrecht Verbindingsweg"). */
  if (!uit.plaats) {
    const post = woorden.findIndex((w) => /^ambulancepost$/i.test(w));
    if (post !== -1 && isNaamwoord(woorden[post + 1])) uit.plaats = woorden[post + 1];
  }

  /* 2. Geen postcode: zoek een woord met een straatuitgang. Staat er een getal
        achter, dan is dat het huisnummer, tenzij het vier cijfers zijn met een
        plaatsnaam erachter: dan zijn het de cijfers van de postcode, zoals in
        "Paleisstraat 1012 Amsterdam". */
  if (!uit.straat) {
    let keus = -1;
    for (let i = 0; i < woorden.length; i++) {
      const w = woorden[i];
      if (!isNaamwoord(w)) continue;
      const getalErachter = i + 1 < woorden.length && HUISNUMMER.test(woorden[i + 1]);
      if (STRAAT_STERK.test(w) || (STRAAT_ZWAK.test(w) && getalErachter)) {
        if (keus === -1 || getalErachter) keus = i;
      }
    }
    if (keus !== -1) {
      let volgend = keus + 1;
      const getal = woorden[volgend];
      if (getal && HUISNUMMER.test(getal)) {
        if (/^\d{4}$/.test(getal) && isNaamwoord(woorden[volgend + 1])) uit.postcode = getal;
        else uit.nummer = getal;
        volgend++;
      }
      if (!uit.plaats) uit.plaats = leesPlaats(woorden, volgend);
      uit.straat = bouwStraat(woorden, keus, uit.plaats);
    }
  }

  /* 3. Nog geen straat: bij een melding met prioriteit zijn de laatste twee
        naamwoorden vrijwel altijd de locatie en de plaats, ook zonder
        straatuitgang ("Vuursteen Heemskerk", "Spaarnepoort Hoofddorp"). */
  if (!uit.straat && PRIORITEIT.test(ruw)) {
    const reeks = [];
    for (let i = woorden.length - 1; i >= 0; i--) {
      if (isNaamwoord(woorden[i])) reeks.unshift(woorden[i]);
      else if (reeks.length) break;
    }
    if (uit.plaats) {
      const rest = reeks.filter((w) => w.toLowerCase() !== uit.plaats.toLowerCase());
      if (rest.length) uit.straat = rest[rest.length - 1];
    } else if (reeks.length >= 2) {
      uit.straat = reeks[reeks.length - 2];
      uit.plaats = reeks[reeks.length - 1];
    } else if (reeks.length === 1) {
      uit.plaats = reeks[0];
    }
  }

  /* 4. Een snelweg of provinciale weg telt ook als locatie. */
  if (!uit.straat) {
    const snelweg = tekst.replace(PRIORITEIT, " ").match(/\b([AN]\d{1,3})\b/);
    if (snelweg) uit.straat = snelweg[1];
  }

  /* 5. Plaats aanvullen vanuit de capcode als de tekst er geen geeft. */
  if (!uit.plaats && plaatsUitCapcode) uit.plaats = plaatsUitCapcode;

  return uit;
}

/* De locatie zoals die aan de kaart wordt meegegeven. Leeg betekent: geen
   locatie herkend. */
function kaartLocatie(m) {
  const adres = leesAdres(m.bericht, m.plaats);
  const delen = [];
  if (adres.straat) delen.push(adres.straat + (adres.nummer ? " " + adres.nummer : ""));
  const staart = [adres.postcode, adres.plaats].filter(Boolean).join(" ");
  if (staart) delen.push(staart);
  return delen.join(", ");
}
