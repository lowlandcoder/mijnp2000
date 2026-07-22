// Werking van de MijnP2000-pagina: filters uitlezen, meldingen ophalen en
// tonen, met steunkleuren per discipline, een kaartpin per melding en de
// vertaling per capcode. Ververst automatisch zolang dat aanstaat.

const $ = (id) => document.getElementById(id);

/* Klok bovenin */
function zetKlok() {
  const nu = new Date();
  $("klok").textContent = nu.toLocaleDateString("nl-NL", { weekday: "long", day: "numeric", month: "long" })
    + " · " + nu.toLocaleTimeString("nl-NL", { hour: "2-digit", minute: "2-digit" });
}

/* Regio's als aankruisvakjes; meerdere tegelijk mogelijk */
let gekozenRegios = new Set();

async function vulRegios() {
  try {
    const regios = await (await fetch("/api/regios")).json();
    const houder = $("regioOpties");
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
        werkRegioSamenvatting();
        haalMeldingen();
      });
      label.appendChild(vak);
      label.appendChild(document.createTextNode(regio));
      houder.appendChild(label);
    }
    werkRegioSamenvatting();
  } catch (e) { /* backend even niet bereikbaar */ }
}

function werkRegioSamenvatting() {
  const n = gekozenRegios.size;
  const tekst = n === 0 ? "Alle regio's" : (n === 1 ? [...gekozenRegios][0] : n + " regio's");
  $("regioSamenvatting").textContent = tekst;
}

/* Discipline naar kleurklasse; lifeliner wint (groen) */
function disciplineKlasse(tekst) {
  const t = (tekst || "").toLowerCase();
  if (/lifeliner|traumaheli|\bmmt\b|mobiel medisch/.test(t)) return "lifeliner";
  if (t.includes("brandweer")) return "brandweer";
  if (t.includes("ambulance")) return "ambulance";
  if (t.includes("politie")) return "politie";
  return "overig";
}

/* Hoofdkleur van de melding: eerst lifeliner in de tekst, anders de eerste
   bekende discipline */
function hoofdKlasse(m) {
  const alles = (m.bericht || "") + " " + (m.disciplines || "");
  if (/lifeliner|traumaheli|\bmmt\b/i.test(alles)) return "lifeliner";
  for (const disc of (m.disciplines || "").split(",").map((d) => d.trim()).filter(Boolean)) {
    const k = disciplineKlasse(disc);
    if (k !== "overig") return k;
  }
  return "overig";
}

/* Prioriteit uit de melding halen voor een kleurtje (A1/P1 = hoog) */
function prioKlasse(bericht) {
  if (/\b(A1|P\s?1|PRIO\s?1|GRIP)\b/i.test(bericht)) return "prio1";
  if (/\b(A2|P\s?2|PRIO\s?2)\b/i.test(bericht)) return "prio2";
  return "";
}

/* Tijd netjes tonen */
function toonTijd(iso) {
  const d = new Date(iso);
  if (isNaN(d)) return iso || "";
  return d.toLocaleString("nl-NL", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

/* Zoekopdracht voor Google Maps opbouwen uit de melding en de plaats */
function kaartZoekterm(m) {
  let t = (m.bericht || "")
    .replace(/\(dia:[^)]*\)/gi, " ")
    .replace(/\brit:?\s*\d+/gi, " ")
    .replace(/\b\d{4,}\b/g, " ")
    .replace(/^\s*(A1|A2|B\d?|P\s?\d)\b/i, " ")
    .replace(/\s+/g, " ")
    .trim();
  if (m.plaats && !new RegExp(m.plaats, "i").test(t)) t += " " + m.plaats;
  return (t + " Nederland").trim();
}

const PIN_SVG = '<svg viewBox="0 0 24 24"><path d="M12 21s7-6.2 7-11a7 7 0 1 0-14 0c0 4.8 7 11 7 11z"></path><circle cx="12" cy="10" r="2.4"></circle></svg>';

/* Eén melding opbouwen */
function maakMelding(m) {
  const kaart = document.createElement("div");
  kaart.className = "melding hoofd-" + hoofdKlasse(m);

  const kop = document.createElement("div");
  kop.className = "melding-kop";

  // Kaartpin naar Google Maps
  const pin = document.createElement("a");
  pin.className = "pin";
  pin.href = "https://www.google.com/maps/search/?api=1&query=" + encodeURIComponent(kaartZoekterm(m));
  pin.target = "_blank";
  pin.rel = "noopener";
  pin.title = "Toon locatie op de kaart";
  pin.innerHTML = PIN_SVG;
  kop.appendChild(pin);

  const tijd = document.createElement("span");
  tijd.className = "melding-tijd";
  tijd.textContent = toonTijd(m.ontvangen);
  kop.appendChild(tijd);

  const prio = prioKlasse(m.bericht || "");
  if (prio) {
    const kenmerk = document.createElement("span");
    kenmerk.className = "kenmerk " + prio;
    kenmerk.textContent = prio === "prio1" ? "Prio 1" : "Prio 2";
    kop.appendChild(kenmerk);
  }
  for (const regio of (m.regios || "").split(",").map((r) => r.trim()).filter(Boolean)) {
    const kenmerk = document.createElement("span");
    kenmerk.className = "kenmerk regio";
    kenmerk.textContent = regio;
    kop.appendChild(kenmerk);
  }
  for (const disc of (m.disciplines || "").split(",").map((d) => d.trim()).filter(Boolean)) {
    const kenmerk = document.createElement("span");
    kenmerk.className = "kenmerk disc-" + disciplineKlasse(disc);
    kenmerk.textContent = disc;
    kop.appendChild(kenmerk);
  }

  const tekst = document.createElement("div");
  tekst.className = "melding-tekst";
  tekst.textContent = m.bericht || "";

  kaart.appendChild(kop);
  kaart.appendChild(tekst);

  // Vertaling per capcode
  if (m.codes && m.codes.length) {
    const codes = document.createElement("div");
    codes.className = "codes";
    for (const c of m.codes) {
      const regel = document.createElement("div");
      regel.className = "code-regel";
      const nr = document.createElement("span");
      nr.className = "code-nr";
      nr.textContent = c.capcode;
      regel.appendChild(nr);
      const delen = [c.omschrijving || c.discipline, c.plaats, c.regio].filter(Boolean);
      regel.appendChild(document.createTextNode(delen.length ? delen.join(" · ") : "onbekende capcode"));
      codes.appendChild(regel);
    }
    kaart.appendChild(codes);
  }
  return kaart;
}

/* Meldingen ophalen en tonen */
async function haalMeldingen() {
  const params = new URLSearchParams();
  if (gekozenRegios.size) params.set("regios", [...gekozenRegios].join(","));
  const uren = $("periode").value;
  const zoek = $("zoek").value.trim();
  if (uren) params.set("uren", uren);
  if (zoek) params.set("zoek", zoek);

  try {
    const meldingen = await (await fetch("/api/meldingen?" + params.toString())).json();
    const lijst = $("lijst");
    lijst.innerHTML = "";
    meldingen.forEach((m) => lijst.appendChild(maakMelding(m)));
    $("leeg").hidden = meldingen.length !== 0;
    $("stand").textContent = meldingen.length
      ? `${meldingen.length} meldingen getoond, nieuwste bovenaan.`
      : "";
  } catch (e) {
    $("stand").textContent = "Kan de meldingen even niet ophalen.";
  }
}

/* Opbouwen en verversen */
zetKlok();
setInterval(zetKlok, 60000);
vulRegios();
haalMeldingen();

["periode", "zoek"].forEach((id) => $(id).addEventListener("input", haalMeldingen));

setInterval(() => {
  if ($("auto").checked) { haalMeldingen(); vulRegios(); }
}, 20000);
