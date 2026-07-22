// Werking van de MijnP2000-pagina: filters uitlezen, meldingen ophalen van de
// backend en tonen. Ververst automatisch zolang dat aanstaat.

const $ = (id) => document.getElementById(id);

/* Klok bovenin */
function zetKlok() {
  const nu = new Date();
  $("klok").textContent = nu.toLocaleDateString("nl-NL", { weekday: "long", day: "numeric", month: "long" })
    + " · " + nu.toLocaleTimeString("nl-NL", { hour: "2-digit", minute: "2-digit" });
}

/* Regio's vullen in het keuzemenu */
async function vulRegios() {
  try {
    const regios = await (await fetch("/api/regios")).json();
    const keuze = $("regio");
    const huidig = keuze.value;
    keuze.innerHTML = '<option value="">Alle regio\'s</option>';
    for (const regio of regios) {
      const optie = document.createElement("option");
      optie.value = regio;
      optie.textContent = regio;
      keuze.appendChild(optie);
    }
    keuze.value = huidig;
  } catch (e) { /* stil: backend even niet bereikbaar */ }
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

/* Eén melding opbouwen */
function maakMelding(m) {
  const kaart = document.createElement("div");
  kaart.className = "melding";

  const kop = document.createElement("div");
  kop.className = "melding-kop";

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
  if (m.regios) {
    for (const regio of m.regios.split(",").map((r) => r.trim()).filter(Boolean)) {
      const kenmerk = document.createElement("span");
      kenmerk.className = "kenmerk regio";
      kenmerk.textContent = regio;
      kop.appendChild(kenmerk);
    }
  }
  if (m.disciplines) {
    for (const disc of m.disciplines.split(",").map((d) => d.trim()).filter(Boolean)) {
      const kenmerk = document.createElement("span");
      kenmerk.className = "kenmerk";
      kenmerk.textContent = disc;
      kop.appendChild(kenmerk);
    }
  }

  const tekst = document.createElement("div");
  tekst.className = "melding-tekst";
  tekst.textContent = m.bericht || "";

  const onder = document.createElement("div");
  onder.className = "melding-onder";
  onder.textContent = "capcodes: " + (m.capcodes || "—");

  kaart.appendChild(kop);
  kaart.appendChild(tekst);
  kaart.appendChild(onder);
  return kaart;
}

/* Meldingen ophalen en tonen */
async function haalMeldingen() {
  const params = new URLSearchParams();
  const regio = $("regio").value;
  const uren = $("periode").value;
  const zoek = $("zoek").value.trim();
  if (regio) params.set("regio", regio);
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

["regio", "periode", "zoek"].forEach((id) =>
  $(id).addEventListener("input", haalMeldingen));

setInterval(() => {
  if ($("auto").checked) { haalMeldingen(); vulRegios(); }
}, 20000);
