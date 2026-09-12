/* Werking van de kaartpagina van MijnP2000.
   De pagina toont de meldingen van de afgelopen minuten binnen een straal rond
   een vast middelpunt: links de kaart met een pin per melding, rechts een kolom
   met dezelfde meldingen, nieuwste bovenaan. Een tik in de kolom licht de pin
   op, een tik op de pin licht de melding in de kolom op.

   Wat waar gebeurt:
   - de adresherkenning komt uit melding.js, hetzelfde bestand dat de lijstpagina
     gebruikt;
   - de omzetting van adres naar coordinaten doet de backend (/api/locaties), die
     elk adres een keer bij de PDOK Locatieserver opzoekt en daarna uit de eigen
     database haalt;
   - het middelpunt, de straal en de sleutel voor de basiskaart komen uit
     /api/kaartinstellingen, dus uit het env-bestand op de server.

   Om weinig gegevens naar buiten te sturen en de dienst niet vol te lopen, gaat
   het opzoeken in twee stappen: eerst de plaatsnaam (een korte, steeds
   terugkerende lijst), en alleen voor plaatsen in of net buiten het gebied ook
   de straat. Huisnummers gaan nooit mee. */

/* ================================================================
   INSTELLINGEN
   ================================================================ */
const VERVERS_MS = 30000;      // hoe vaak de meldingen opnieuw worden opgehaald
const MARGE_KM = 15;           // ruimte rond het gebied voor de voorselectie
const MAX_MELDINGEN = 500;     // hoogstens zoveel meldingen per ronde ophalen
const TERMEN_PER_VERZOEK = 50; // zoektermen per verzoek aan de backend
const STRAAL_SLEUTEL = "mijnp2000.straal";

/* Kaartondergrond, gelijk aan mijnradar en mijnais. De lichte laag leest het
   best; kaart.css dimt de tegels zodat ze bij de donkere pagina passen. CARTO
   vraagt sinds augustus 2026 een sleutel: zonder sleutel werkt de kaart gewoon,
   maar ligt er een watermerk over de tegels. */
const KAARTLAAG = "https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png";

const $ = (id) => document.getElementById(id);

let kaart = null;
let tegellaag = null;
let gebiedCirkel = null;
let pinLaag = null;

let middelpunt = null;
let straalKm = 12;
let minuten = 60;

let ruweMeldingen = [];
let inGebied = [];
let zonderLocatie = 0;
let pinPer = new Map();     // sleutel -> pin op de kaart
let actief = null;          // sleutel van de gekozen melding
let beeldGezet = false;     // na de eerste keer het beeld niet meer verschuiven
let bezig = false;
const locaties = new Map(); // zoekterm -> {lat, lon} of null

/* ---------- Klok en stand ---------- */
function zetKlok() {
  $("klok").textContent = new Date().toLocaleTimeString("nl-NL", {
    hour: "2-digit", minute: "2-digit", second: "2-digit",
  });
}

function zetLive(aan) {
  $("live").classList.toggle("stil", !aan);
  $("live").textContent = aan ? "live" : "geen verbinding";
}

function toonFout(tekst) {
  const vak = $("kaartfout");
  vak.textContent = tekst;
  vak.hidden = false;
}

/* ---------- Rekenen met afstand ---------- */
function afstandKm(a, b) {
  const R = 6371;
  const rad = Math.PI / 180;
  const dLat = (b.lat - a.lat) * rad;
  const dLon = (b.lon - a.lon) * rad;
  const s = Math.sin(dLat / 2) ** 2 +
            Math.cos(a.lat * rad) * Math.cos(b.lat * rad) * Math.sin(dLon / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(s));
}

/* ---------- Zoektermen uit een melding ---------- */
function plaatsTerm(adres) {
  return (adres.plaats || "").trim();
}

/* Straat met postcode en plaats erachter, zonder huisnummer. Het huisnummer
   blijft weg: de pin komt daarmee in de goede straat en er gaat zo weinig
   mogelijk naar buiten. */
function wegTerm(adres) {
  const straat = (adres.straat || "").trim();
  if (!straat) return "";
  const staart = [adres.postcode, adres.plaats]
    .map((deel) => (deel || "").trim()).filter(Boolean).join(" ");
  return staart ? straat + " " + staart : "";
}

function sleutelVan(m) {
  return (m.ontvangen || "") + "|" + (m.bericht || "");
}

/* ---------- Coordinaten opvragen bij de backend ---------- */
async function vraagLocaties(termen, soort) {
  for (let i = 0; i < termen.length; i += TERMEN_PER_VERZOEK) {
    const deel = termen.slice(i, i + TERMEN_PER_VERZOEK);
    try {
      const antwoord = await fetch("/api/locaties", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ termen: deel.map((t) => ({ zoekterm: t, soort })) }),
      });
      if (!antwoord.ok) return;
      const uitkomst = await antwoord.json();
      /* Termen die niet in het antwoord staan, paste de backend deze ronde niet
         meer; die blijven onbekend en komen bij de volgende ronde opnieuw
         langs. */
      for (const [term, punt] of Object.entries(uitkomst)) locaties.set(term, punt);
    } catch (e) {
      return;  // backend even niet bereikbaar; volgende ronde opnieuw
    }
  }
}

/* ---------- Meldingen indelen ---------- */
async function bepaalGebied() {
  // Stap 1: plaatsnamen.
  const nieuwePlaatsen = new Set();
  const rijen = ruweMeldingen.map((m) => {
    const adres = leesAdres(m.bericht, m.plaats);
    const plaats = plaatsTerm(adres);
    if (plaats && !locaties.has(plaats)) nieuwePlaatsen.add(plaats);
    return { m, adres, plaats };
  });
  await vraagLocaties([...nieuwePlaatsen], "plaats");

  // Stap 2: alleen straten van plaatsen in of net buiten het gebied.
  const nieuweWegen = new Set();
  for (const rij of rijen) {
    rij.plaatsPunt = rij.plaats ? locaties.get(rij.plaats) || null : null;
    rij.afstandPlaats = rij.plaatsPunt ? afstandKm(rij.plaatsPunt, middelpunt) : null;
    rij.dichtbij = rij.afstandPlaats !== null && rij.afstandPlaats <= straalKm + MARGE_KM;
    rij.wegTerm = rij.dichtbij ? wegTerm(rij.adres) : "";
    if (rij.wegTerm && !locaties.has(rij.wegTerm)) nieuweWegen.add(rij.wegTerm);
  }
  await vraagLocaties([...nieuweWegen], "weg");

  // Stap 3: wat hoort erbij, en wat komt op de kaart?
  inGebied = [];
  zonderLocatie = 0;
  for (const rij of rijen) {
    if (!rij.dichtbij) continue;
    const punt = rij.wegTerm ? locaties.get(rij.wegTerm) || null : null;
    if (punt) {
      if (afstandKm(punt, middelpunt) > straalKm) continue;
      inGebied.push({ ...rij, punt });
    } else if (rij.afstandPlaats <= straalKm) {
      // Plaats valt binnen het gebied, maar het exacte adres is niet bekend:
      // wel in de kolom, niet op de kaart.
      zonderLocatie++;
      inGebied.push({ ...rij, punt: null });
    }
  }
}

/* ---------- Kaart ---------- */
function maakKaart() {
  kaart = L.map("kaart", { zoomControl: true, attributionControl: true });
  kaart.setView([middelpunt.lat, middelpunt.lon], 11);
  tegellaag = L.tileLayer(KAARTLAAG, {
    attribution: "&copy; OpenStreetMap, &copy; CARTO",
    subdomains: "abcd",
    maxZoom: 19,
  }).addTo(kaart);
  pinLaag = L.layerGroup().addTo(kaart);
  L.circleMarker([middelpunt.lat, middelpunt.lon], {
    radius: 4, color: "#ffffff", weight: 1, fillColor: "#f0883e", fillOpacity: 1,
  }).addTo(kaart).bindTooltip("Middelpunt");
  tekenGebied();
}

function zetKaartSleutel(sleutel) {
  if (!sleutel || !tegellaag) return;
  tegellaag.setUrl(KAARTLAAG + "?key=" + encodeURIComponent(sleutel));
}

function tekenGebied() {
  if (gebiedCirkel) gebiedCirkel.remove();
  gebiedCirkel = L.circle([middelpunt.lat, middelpunt.lon], {
    radius: straalKm * 1000,
    color: "#f0883e", weight: 1, dashArray: "4 4", fill: false,
  }).addTo(kaart);
  if (!beeldGezet) {
    kaart.fitBounds(gebiedCirkel.getBounds(), { padding: [10, 10] });
    beeldGezet = true;
  }
}

function kleurVan(klasse) {
  const stijl = getComputedStyle(document.documentElement);
  return {
    vul: (stijl.getPropertyValue("--" + klasse) || "").trim() || "#c4c4c4",
    rand: (stijl.getPropertyValue("--" + klasse + "-rand") || "").trim() || "#555555",
  };
}

function zetPinnen() {
  pinLaag.clearLayers();
  pinPer = new Map();
  for (const rij of inGebied) {
    if (!rij.punt) continue;
    const sleutel = sleutelVan(rij.m);
    const kleur = kleurVan(hoofdKlasse(rij.m));
    const isActief = sleutel === actief;
    const pin = L.circleMarker([rij.punt.lat, rij.punt.lon], {
      radius: isActief ? 11 : 7,
      color: isActief ? "#ffffff" : kleur.rand,
      weight: isActief ? 3 : 2,
      fillColor: kleur.vul,
      fillOpacity: .9,
    });
    pin.bindTooltip(korteTekst(rij.m.bericht), { direction: "top" });
    pin.on("click", () => kies(sleutel, "kaart"));
    pin.addTo(pinLaag);
    if (isActief) pin.bringToFront();
    pinPer.set(sleutel, pin);
  }
}

/* ---------- Kolom ---------- */
function korteTekst(tekst) {
  const t = (tekst || "").trim();
  return t.length > 90 ? t.slice(0, 88) + "…" : t;
}

function veilig(tekst) {
  return (tekst || "").replace(/[&<>"']/g, (teken) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[teken]);
}

function kolomKaartje(rij) {
  const m = rij.m;
  const sleutel = sleutelVan(m);
  const tijd = new Date(m.ontvangen);
  const klok = isNaN(tijd) ? "--:--" : tijd.toLocaleTimeString("nl-NL", {
    hour: "2-digit", minute: "2-digit",
  });
  const min = minutenGeleden(m.ontvangen);
  const plek = kaartLocatie(m);
  return (
    '<article class="kolomkaart dienst-' + hoofdKlasse(m) +
    (sleutel === actief ? " actief" : "") + '" data-sleutel="' + veilig(sleutel) + '">' +
    '<p class="titel">' + veilig(m.bericht || "") + "</p>" +
    '<p class="meta">' +
    '<span class="tijd">' + klok + "</span>" +
    (min === null ? "" : '<span class="geleden">' + min + " min</span>") +
    (plek ? '<span class="plek">' + veilig(plek) + "</span>" : "") +
    (rij.punt ? "" : '<span class="geenpin">niet op de kaart</span>') +
    "</p></article>"
  );
}

function zetKolom() {
  const houder = $("kolomlijst");
  houder.innerHTML = inGebied.map(kolomKaartje).join("");
  $("kolomLeeg").hidden = inGebied.length > 0;
}

function zetStand() {
  const opKaart = inGebied.filter((rij) => rij.punt).length;
  const balk = $("stand");
  balk.textContent = opKaart + (opKaart === 1 ? " melding" : " meldingen") +
    " op de kaart, binnen " + straalKm + " km, laatste " + minuten + " minuten";
  if (zonderLocatie > 0) {
    const extra = document.createElement("span");
    extra.className = "zonder";
    extra.textContent = " · " + zonderLocatie + " zonder herkend adres, alleen in de kolom";
    balk.appendChild(extra);
  }
}

/* ---------- Gedeelde selectie: kolom en kaart wijzen naar dezelfde melding ---------- */
function kies(sleutel, vanwaar) {
  actief = actief === sleutel ? null : sleutel;
  zetPinnen();
  zetKolom();
  if (!actief) return;
  const kaartje = document.querySelector('.kolomkaart[data-sleutel="' + CSS.escape(actief) + '"]');
  const pin = pinPer.get(actief);
  if (vanwaar === "kolom" && pin) {
    kaart.panTo(pin.getLatLng());
  }
  if (vanwaar === "kaart" && kaartje) {
    kaartje.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }
}

function toon() {
  // Een melding die uit het venster is gelopen, is ook geen keuze meer.
  if (actief && !inGebied.some((rij) => sleutelVan(rij.m) === actief)) actief = null;
  zetPinnen();
  zetKolom();
  zetStand();
}

/* ---------- Ronde: meldingen ophalen, indelen en tonen ---------- */
async function ronde() {
  if (bezig || !middelpunt) return;
  bezig = true;
  try {
    const uren = (minuten / 60).toFixed(4);
    const antwoord = await fetch("/api/meldingen?uren=" + uren + "&limiet=" + MAX_MELDINGEN);
    if (!antwoord.ok) throw new Error("API gaf " + antwoord.status);
    ruweMeldingen = await antwoord.json();
    zetLive(true);
    await bepaalGebied();
    toon();
  } catch (e) {
    zetLive(false);
  } finally {
    bezig = false;
  }
}

/* Alleen opnieuw indelen, zonder de meldingen opnieuw op te halen. Dat is wat
   een andere straal nodig heeft. */
async function opnieuwIndelen() {
  if (!middelpunt || bezig) return;
  bezig = true;
  try {
    await bepaalGebied();
    toon();
  } finally {
    bezig = false;
  }
}

/* ---------- Straal bewaren per apparaat ---------- */
function leesBewaardeStraal() {
  try {
    const bewaard = localStorage.getItem(STRAAL_SLEUTEL);
    if (bewaard !== null) {
      const waarde = parseFloat(bewaard);
      if (!isNaN(waarde) && waarde > 0) return waarde;
    }
  } catch (e) { /* opslag niet beschikbaar */ }
  return null;
}

function bewaarStraal(waarde) {
  try {
    localStorage.setItem(STRAAL_SLEUTEL, String(waarde));
  } catch (e) { /* opslag niet beschikbaar */ }
}

/* ---------- Knoppen ---------- */
function zetKnoppen() {
  $("knopPaneel").addEventListener("click", () => {
    const paneel = $("paneel");
    const open = paneel.hidden;
    paneel.hidden = !open;
    $("knopPaneel").setAttribute("aria-expanded", String(open));
    $("knopPaneel").classList.toggle("aan", open);
    if (kaart) setTimeout(() => kaart.invalidateSize(), 50);
  });

  $("knopSchermvullend").addEventListener("click", () => {
    if (document.fullscreenElement) document.exitFullscreen();
    else document.documentElement.requestFullscreen().catch(() => {});
  });

  const regelaar = $("straal");
  regelaar.addEventListener("input", () => {
    straalKm = parseFloat(regelaar.value);
    $("straalWaarde").textContent = straalKm + " km";
  });
  regelaar.addEventListener("change", () => {
    straalKm = parseFloat(regelaar.value);
    bewaarStraal(straalKm);
    tekenGebied();
    opnieuwIndelen();
  });

  $("kolomlijst").addEventListener("click", (gebeurtenis) => {
    const kaartje = gebeurtenis.target.closest(".kolomkaart");
    if (kaartje) kies(kaartje.dataset.sleutel, "kolom");
  });
}

/* ---------- Start ---------- */
async function start() {
  zetKlok();
  setInterval(zetKlok, 1000);
  zetKnoppen();

  let instellingen = null;
  try {
    const antwoord = await fetch("/api/kaartinstellingen");
    instellingen = await antwoord.json();
  } catch (e) {
    zetLive(false);
    toonFout("De instellingen van de kaart zijn niet op te halen. Draait de backend nog?");
    return;
  }

  minuten = instellingen.minuten || 60;
  const bewaard = leesBewaardeStraal();
  straalKm = bewaard !== null ? bewaard : (instellingen.straal_km || 12);
  $("straal").value = straalKm;
  $("straalWaarde").textContent = straalKm + " km";
  $("paneelUitleg").textContent =
    "De kaart toont de meldingen van de afgelopen " + minuten + " minuten waarvan " +
    "het adres binnen deze straal valt. De keuze wordt op dit apparaat bewaard.";
  $("kolomLeeg").textContent =
    "Geen meldingen in dit gebied in de afgelopen " + minuten + " minuten.";

  middelpunt = instellingen.middelpunt || null;
  if (!middelpunt) {
    toonFout("Het middelpunt ontbreekt. Zet KAART_POSTCODE, of KAART_LAT en " +
             "KAART_LON, in het env-bestand op de server en start de container opnieuw.");
    return;
  }

  maakKaart();
  zetKaartSleutel((instellingen.basiskaart || {}).sleutel);
  ronde();
  setInterval(ronde, VERVERS_MS);
}

start();
