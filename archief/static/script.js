// Werking van de MijnP2000-pagina.
// De weergave volgt p2000.page: een balk bovenin met klok en knoppen, filters
// achter een knop, en per melding een compacte regel met een gekleurde titel
// per dienst, de tijd met het aantal minuten geleden en een pin rechts naar de
// kaart. De capcodes met vertaling staan standaard ingeklapt; een tik op de
// melding klapt ze uit.

const $ = (id) => document.getElementById(id);

/* ---------- Klok bovenin ---------- */
function zetKlok() {
  $("klok").textContent = new Date().toLocaleTimeString("nl-NL", {
    hour: "2-digit", minute: "2-digit", second: "2-digit",
  });
}

/* ---------- Bewaarde keuzes ---------- */
const STANDAARD_REGIOS = ["Kennemerland"];
const STANDAARD_PLAATSEN = "haarlem, driehuis, zandvoort, bloemendaal, ijmuiden";
const REGIO_SLEUTEL = "mijnp2000.regios";
const GELUID_SLEUTEL = "mijnp2000.geluid";
const PLAATSEN_SLEUTEL = "mijnp2000.plaatsen";
const PLAATSFILTER_SLEUTEL = "mijnp2000.plaatsfilter";

let eigenKeuze = false;   // true zodra er een bewaarde keuze is
let geluidAan = false;
let eersteRonde = true;   // bij het opbouwen geen seintje en geen oplichten
let bekendeSleutels = new Set();
let openSleutels = new Set();  // meldingen waarvan de capcodes zijn uitgeklapt

function leesBewaardeRegios() {
  try {
    const bewaard = localStorage.getItem(REGIO_SLEUTEL);
    if (bewaard !== null) {
      eigenKeuze = true;
      return new Set(JSON.parse(bewaard));
    }
  } catch (e) { /* opslag niet beschikbaar of onleesbaar */ }
  return new Set(STANDAARD_REGIOS);
}

function bewaarRegios() {
  eigenKeuze = true;
  try {
    localStorage.setItem(REGIO_SLEUTEL, JSON.stringify([...gekozenRegios]));
  } catch (e) { /* opslag niet beschikbaar */ }
}

let gekozenRegios = leesBewaardeRegios();

/* ---------- Persoonlijk plaatsnamenfilter ----------
   Een lijst plaatsnamen, gescheiden door komma's. Staat het filter aan, dan
   worden alleen meldingen getoond waarin een van die plaatsnamen voorkomt:
   in de plaats van de melding, in de tekst van de melding of in de standplaats
   van een capcode. Er wordt op hele woorden vergeleken, zodat "haarlem" niet
   ook Haarlemmermeer oplevert. De lijst en de stand van de schakelaar worden
   per apparaat bewaard. */

function leesPlaatsInstellingen() {
  let tekst = STANDAARD_PLAATSEN;
  let aan = false;
  try {
    const bewaard = localStorage.getItem(PLAATSEN_SLEUTEL);
    if (bewaard !== null) tekst = bewaard;
    aan = localStorage.getItem(PLAATSFILTER_SLEUTEL) === "aan";
  } catch (e) { /* opslag niet beschikbaar */ }
  return { tekst, aan };
}

function bewaarPlaatsInstellingen() {
  try {
    localStorage.setItem(PLAATSEN_SLEUTEL, $("plaatsen").value);
    localStorage.setItem(PLAATSFILTER_SLEUTEL, $("plaatsAan").checked ? "aan" : "uit");
  } catch (e) { /* opslag niet beschikbaar */ }
}

function plaatsPatronen() {
  return $("plaatsen").value
    .split(",")
    .map((p) => p.trim())
    .filter(Boolean)
    .map((p) => new RegExp("\\b" + p.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + "\\b", "i"));
}

function pastBijPlaatsen(m, patronen) {
  const teksten = [m.plaats || "", m.bericht || ""];
  for (const c of m.codes || []) if (c.plaats) teksten.push(c.plaats);
  return patronen.some((patroon) => teksten.some((t) => patroon.test(t)));
}

/* ---------- Regiolijst in het filterpaneel ---------- */
async function vulRegios() {
  try {
    const regios = await (await fetch("/api/regios")).json();

    // Staat de standaardregio nog niet in de gegevens, laat het filter dan los,
    // anders blijft de lijst bij een eerste bezoek leeg.
    if (!eigenKeuze) {
      let aangepast = false;
      for (const regio of [...gekozenRegios]) {
        if (!regios.includes(regio)) { gekozenRegios.delete(regio); aangepast = true; }
      }
      if (aangepast) haalMeldingen();
    }

    const houder = $("regioOpties");
    const bestaand = [...houder.querySelectorAll("input")].map((v) => v.value).join("|");
    if (bestaand === regios.join("|")) {
      // Alleen de vinkjes bijwerken; de lijst zelf is niet veranderd.
      houder.querySelectorAll("input").forEach((v) => { v.checked = gekozenRegios.has(v.value); });
      return;
    }

    houder.innerHTML = "";
    for (const regio of regios) {
      const label = document.createElement("label");
      label.className = "regio-optie";
      const vak = document.createElement("input");
      vak.type = "checkbox";
      vak.value = regio;
      vak.checked = gekozenRegios.has(regio);
      vak.addEventListener("change", () => {
        if (vak.checked) gekozenRegios.add(regio); else gekozenRegios.delete(regio);
        bewaarRegios();
        haalMeldingen();
      });
      label.appendChild(vak);
      label.appendChild(document.createTextNode(regio));
      houder.appendChild(label);
    }
  } catch (e) { /* backend even niet bereikbaar */ }
}

/* ---------- Eén melding opbouwen ---------- */
function maakMelding(m, isNieuw, sleutel) {
  const rij = document.createElement("article");
  rij.className = "melding dienst-" + hoofdKlasse(m) + (isNieuw ? " nieuw" : "");

  const inhoud = document.createElement("div");
  inhoud.className = "rij-inhoud";

  const titel = document.createElement("h2");
  titel.className = "titel";
  titel.textContent = m.bericht || "";
  inhoud.appendChild(titel);

  const meta = document.createElement("div");
  meta.className = "meta";

  const d = new Date(m.ontvangen);
  const tijd = document.createElement("span");
  tijd.className = "tijd";
  if (!isNaN(d)) {
    const uu = String(d.getHours()).padStart(2, "0");
    const mm = String(d.getMinutes()).padStart(2, "0");
    const ss = String(d.getSeconds()).padStart(2, "0");
    tijd.innerHTML = "<b>" + uu + ":" + mm + "</b>:" + ss;
  } else {
    tijd.textContent = m.ontvangen || "";
  }
  meta.appendChild(tijd);

  const min = minutenGeleden(m.ontvangen);
  if (min !== null) {
    const geleden = document.createElement("span");
    geleden.className = "geleden" + (min > 60 ? " oud" : "");
    geleden.dataset.tijd = m.ontvangen;
    geleden.textContent = "+" + min;
    geleden.title = min + " minuten geleden";
    meta.appendChild(geleden);
  }

  if (!isNaN(d)) {
    const datum = document.createElement("span");
    datum.className = "datum";
    datum.textContent = d.toLocaleDateString("nl-NL", { day: "2-digit", month: "2-digit", year: "numeric" });
    meta.appendChild(datum);
  }

  const prio = prioKlasse(m.bericht || "");
  if (prio) {
    const badge = document.createElement("span");
    badge.className = "badge " + prio;
    badge.textContent = prio === "prio1" ? "Prio 1" : "Prio 2";
    meta.appendChild(badge);
  }
  for (const regio of (m.regios || "").split(",").map((r) => r.trim()).filter(Boolean)) {
    const badge = document.createElement("span");
    badge.className = "badge regio";
    badge.textContent = regio;
    meta.appendChild(badge);
  }
  // Capcodes met vertaling. Het blok staat standaard ingeklapt; een tik op de
  // melding klapt het uit en weer in. De keuze blijft bewaard bij het verversen.
  if (m.codes && m.codes.length) {
    const open = openSleutels.has(sleutel);

    const wissel = document.createElement("span");
    wissel.className = "badge capwissel" + (open ? " open" : "");
    wissel.innerHTML = '<span class="pijl">▸</span> ' + m.codes.length +
      (m.codes.length === 1 ? " capcode" : " capcodes");
    meta.appendChild(wissel);
    inhoud.appendChild(meta);

    const capblok = document.createElement("div");
    capblok.className = "capblok";
    capblok.hidden = !open;

    const codes = document.createElement("div");
    codes.className = "codes";
    for (const c of m.codes) {
      const regel = document.createElement("div");
      regel.className = "code";
      const nr = document.createElement("span");
      nr.className = "nr";
      nr.textContent = c.capcode;
      regel.appendChild(nr);
      const delen = [c.omschrijving, c.discipline, c.regio || c.plaats].filter(Boolean);
      regel.appendChild(document.createTextNode(delen.length ? delen.join(" / ") : "onbekende capcode"));
      codes.appendChild(regel);
    }
    capblok.appendChild(codes);

    // Eenheid als extra regel: alleen capcodes van een eenheid met een eigen
    // standplaats. Monitorcodes van de meldkamer en regels zonder plaats staan
    // al volledig in de lijst hierboven en worden overgeslagen.
    const eenheden = [];
    for (const c of m.codes) {
      if (!c.omschrijving || !c.plaats) continue;
      if (/monitorcode|meldkamer/i.test(c.omschrijving)) continue;
      const tekst = c.omschrijving + " - " + c.plaats;
      if (!eenheden.includes(tekst)) eenheden.push(tekst);
    }
    if (eenheden.length) {
      const eenheid = document.createElement("div");
      eenheid.className = "eenheid";
      eenheid.textContent = eenheden.join(" · ");
      capblok.appendChild(eenheid);
    }

    inhoud.appendChild(capblok);

    // Tik op de melding: capcodes tonen of verbergen. Een klik die tekst
    // selecteert of op een koppeling valt, telt niet als tik.
    rij.classList.add("klapbaar");
    inhoud.addEventListener("click", (e) => {
      if (e.target.closest("a")) return;
      const selectie = window.getSelection();
      if (selectie && !selectie.isCollapsed) return;
      const nuOpen = capblok.hidden;
      capblok.hidden = !nuOpen;
      wissel.classList.toggle("open", nuOpen);
      if (nuOpen) openSleutels.add(sleutel); else openSleutels.delete(sleutel);
    });
  } else {
    inhoud.appendChild(meta);
  }

  rij.appendChild(inhoud);

  const pin = document.createElement("a");
  pin.className = "pin";
  const locatie = kaartLocatie(m);
  if (locatie) {
    pin.href = "https://www.google.com/maps/search/?api=1&query=" +
      encodeURIComponent(locatie + ", Nederland");
    pin.target = "_blank";
    pin.rel = "noopener";
    pin.title = "Toon op de kaart: " + locatie;
    pin.setAttribute("aria-label", "Toon " + locatie + " op de kaart");
  } else {
    pin.classList.add("geen");
    pin.title = "Geen locatie in de melding herkend";
    pin.setAttribute("aria-label", "Geen locatie in de melding herkend");
  }
  pin.innerHTML = PIN_SVG;
  rij.appendChild(pin);

  return rij;
}

/* ---------- Blokjes met minuten geleden bijwerken ---------- */
function werkGeledenBij() {
  document.querySelectorAll(".geleden").forEach((el) => {
    const min = minutenGeleden(el.dataset.tijd);
    if (min === null) return;
    el.textContent = "+" + min;
    el.title = min + " minuten geleden";
    el.classList.toggle("oud", min > 60);
  });
}

/* ---------- Seintje bij een nieuwe melding ---------- */
function piep() {
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    const osc = ctx.createOscillator();
    const vol = ctx.createGain();
    osc.type = "sine";
    osc.frequency.value = 880;
    vol.gain.setValueAtTime(0.0001, ctx.currentTime);
    vol.gain.exponentialRampToValueAtTime(0.2, ctx.currentTime + 0.02);
    vol.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + 0.35);
    osc.connect(vol).connect(ctx.destination);
    osc.start();
    osc.stop(ctx.currentTime + 0.36);
    setTimeout(() => ctx.close(), 600);
  } catch (e) { /* geluid niet mogelijk in deze browser */ }
}

/* ---------- Meldingen ophalen en tonen ---------- */
async function haalMeldingen() {
  const params = new URLSearchParams();
  if (gekozenRegios.size) params.set("regios", [...gekozenRegios].join(","));
  const uren = $("periode").value;
  const zoek = $("zoek").value.trim();
  if (uren) params.set("uren", uren);
  if (zoek) params.set("zoek", zoek);

  try {
    let meldingen = await (await fetch("/api/meldingen?" + params.toString())).json();

    // Persoonlijk plaatsnamenfilter, na het ophalen toegepast in de browser.
    let verborgen = 0;
    const patronen = $("plaatsAan").checked ? plaatsPatronen() : [];
    if (patronen.length) {
      const alles = meldingen.length;
      meldingen = meldingen.filter((m) => pastBijPlaatsen(m, patronen));
      verborgen = alles - meldingen.length;
    }

    const lijst = $("lijst");
    const nieuweSleutels = new Set();
    let aantalNieuw = 0;

    lijst.innerHTML = "";
    for (const m of meldingen) {
      const sleutel = (m.ontvangen || "") + "|" + (m.bericht || "");
      nieuweSleutels.add(sleutel);
      const isNieuw = !eersteRonde && !bekendeSleutels.has(sleutel);
      if (isNieuw) aantalNieuw++;
      lijst.appendChild(maakMelding(m, isNieuw, sleutel));
    }

    bekendeSleutels = nieuweSleutels;
    // Uitgeklapte meldingen die uit de lijst zijn verdwenen, vergeten.
    for (const s of [...openSleutels]) if (!nieuweSleutels.has(s)) openSleutels.delete(s);
    if (aantalNieuw && geluidAan) piep();
    eersteRonde = false;

    $("leeg").hidden = meldingen.length !== 0;
    let stand = meldingen.length
      ? meldingen.length + " meldingen getoond, nieuwste bovenaan."
      : "";
    if (verborgen) stand += " Plaatsfilter verbergt " + verborgen + (verborgen === 1 ? " melding." : " meldingen.");
    $("stand").textContent = stand;
    $("live").textContent = "live";
    $("live").classList.remove("stil");
  } catch (e) {
    $("stand").textContent = "Kan de meldingen even niet ophalen.";
    $("live").textContent = "geen verbinding";
    $("live").classList.add("stil");
  }
}

/* ---------- Knoppen in de balk ---------- */
function toonPaneel(open, focusOp) {
  const paneel = $("paneel");
  const nu = open === undefined ? paneel.hidden : open;
  paneel.hidden = !nu;
  $("knopFilter").setAttribute("aria-expanded", String(nu));
  if (nu && focusOp) focusOp.focus();
}

$("knopFilter").addEventListener("click", () => toonPaneel());
$("knopZoek").addEventListener("click", () => toonPaneel(true, $("zoek")));

$("regioAlles").addEventListener("click", () => {
  gekozenRegios.clear();
  bewaarRegios();
  $("regioOpties").querySelectorAll("input").forEach((v) => { v.checked = false; });
  haalMeldingen();
});

$("knopSchermvullend").addEventListener("click", () => {
  if (document.fullscreenElement) document.exitFullscreen();
  else document.documentElement.requestFullscreen().catch(() => {});
});

try { geluidAan = localStorage.getItem(GELUID_SLEUTEL) === "aan"; } catch (e) { /* geen opslag */ }
function toonGeluid() {
  $("knopGeluid").classList.toggle("aan", geluidAan);
  $("knopGeluid").setAttribute("aria-pressed", String(geluidAan));
}
toonGeluid();
$("knopGeluid").addEventListener("click", () => {
  geluidAan = !geluidAan;
  try { localStorage.setItem(GELUID_SLEUTEL, geluidAan ? "aan" : "uit"); } catch (e) { /* geen opslag */ }
  toonGeluid();
  if (geluidAan) piep();
});

["periode", "zoek"].forEach((id) => $(id).addEventListener("input", haalMeldingen));

/* Plaatsnamenfilter: instellingen terugzetten en wijzigingen verwerken */
const plaatsInstellingen = leesPlaatsInstellingen();
$("plaatsen").value = plaatsInstellingen.tekst;
$("plaatsAan").checked = plaatsInstellingen.aan;

$("plaatsAan").addEventListener("change", () => { bewaarPlaatsInstellingen(); haalMeldingen(); });
$("plaatsen").addEventListener("input", () => { bewaarPlaatsInstellingen(); haalMeldingen(); });

/* ---------- Opbouwen en verversen ---------- */
zetKlok();
setInterval(zetKlok, 1000);
setInterval(werkGeledenBij, 15000);

vulRegios();
haalMeldingen();

setInterval(() => {
  if ($("auto").checked) { haalMeldingen(); vulRegios(); }
}, 20000);
