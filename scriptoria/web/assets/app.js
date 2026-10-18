"use strict";
// Scriptoria — study workbench front end. Vanilla JS, no build step (keeps it offline).

const $ = (s, r = document) => r.querySelector(s);
const el = (t, props = {}, kids = []) => {
  const n = document.createElement(t);
  for (const [k, v] of Object.entries(props)) {
    if (k === "dataset") Object.assign(n.dataset, v);           // dataset is getter-only
    else if (k === "style" && typeof v === "object") Object.assign(n.style, v);
    else n[k] = v;
  }
  for (const c of [].concat(kids)) if (c !== "" && c != null) n.append(c);
  return n;
};
const api = async (p) => {
  const r = await fetch(p);
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || r.statusText);
  return r.json();
};
const store = {
  get: (k, d) => { try { return JSON.parse(localStorage.getItem("scr." + k)) ?? d; } catch { return d; } },
  set: (k, v) => { try { localStorage.setItem("scr." + k, JSON.stringify(v)); } catch {} },
};

const HL = { amber: "#D6A955", rose: "#BE505A", sky: "#3C6EBE", sage: "#5A965A" };
const state = {
  books: [], bookName: {}, translations: [],
  book: store.get("book", "John"), chapter: store.get("chapter", 3),
  versions: store.get("versions", ["KJV"]),
  sel: null, tab: "xref", notes: {},
};

function osisParts(osis) { const p = osis.split("."); return [p[0], +p[1], +p[2]]; }

// ---------------------------------------------------------------- bootstrap
async function init() {
  state.books = await api("/api/books");
  state.books.forEach((b) => (state.bookName[b.osis] = b.name));
  state.translations = await api("/api/translations");
  const have = new Set(state.translations.map((t) => t.code));
  state.versions = state.versions.filter((c) => have.has(c));
  if (!state.versions.length) state.versions = [state.translations.find((t) => t.code === "KJV") ? "KJV" : state.translations[0].code];

  renderVersions();
  renderBookPicker();
  wire();
  applyTheme(store.get("theme", "auto"));
  await loadChapter();
}

function renderVersions() {
  const box = $("#versions");
  box.replaceChildren(...state.translations.map((t) => {
    const on = state.versions.includes(t.code);
    const c = el("button", { className: "chip", type: "button", textContent: t.code, title: t.name });
    c.setAttribute("aria-pressed", on);
    c.onclick = () => toggleVersion(t.code, c);
    return c;
  }));
}
function toggleVersion(code, chip) {
  const i = state.versions.indexOf(code);
  if (i >= 0) { if (state.versions.length === 1) return; state.versions.splice(i, 1); }
  else state.versions.push(code);
  chip.setAttribute("aria-pressed", state.versions.includes(code));
  store.set("versions", state.versions);
  loadChapter(false);
}

function renderBookPicker() {
  const bsel = $("#book");
  bsel.replaceChildren(...state.books.map((b) => el("option", { value: b.osis, textContent: b.name, selected: b.osis === state.book })));
  fillChapters();
}
function fillChapters() {
  const b = state.books.find((x) => x.osis === state.book) || state.books[0];
  state.book = b.osis;
  const csel = $("#chapter");
  csel.replaceChildren(...Array.from({ length: b.chapters }, (_, i) =>
    el("option", { value: i + 1, textContent: "Chapter " + (i + 1), selected: i + 1 === state.chapter })));
}

function wire() {
  $("#book").onchange = (e) => { state.book = e.target.value; state.chapter = 1; fillChapters(); loadChapter(); };
  $("#chapter").onchange = (e) => { state.chapter = +e.target.value; loadChapter(); };
  $("#themeBtn").onclick = cycleTheme;
  $("#searchForm").onsubmit = (e) => { e.preventDefault(); const q = $("#searchInput").value.trim(); if (q) runSearch(q); };
  $("#study").addEventListener("click", onStudyClick);
  document.querySelectorAll(".tab").forEach((t) => (t.onclick = () => setTab(t.dataset.tab)));
}

// ---------------------------------------------------------------- reader
async function loadChapter(resetSel = true) {
  const { book, chapter } = state;
  store.set("book", book); store.set("chapter", chapter);
  const data = await api(`/api/chapter?book=${encodeURIComponent(book)}&chapter=${chapter}&translations=${state.versions.join(",")}`);
  state.notes = await api(`/api/notes/chapter?book=${encodeURIComponent(book)}&chapter=${chapter}`).catch(() => ({}));
  const r = $("#reader");
  r.replaceChildren();
  r.append(el("div", { className: "chapter-head" }, [
    el("div", { className: "chapter-num", textContent: chapter }),
    el("div", { className: "chapter-book" }, [
      document.createTextNode(state.bookName[book] || book),
      el("small", { textContent: state.versions.join(" · ") }),
    ]),
  ]));
  r.append(state.versions.length > 1 ? grid(data) : prose(data));
  r.scrollTop = 0;
  if (resetSel) { state.sel = null; closeStudy(); }
  else if (state.sel) markSelected();
  // keep selectors in sync (e.g. after navigation)
  $("#book").value = book; fillChapters(); $("#chapter").value = chapter;
}

function hlClass(osis) { const n = state.notes[osis]; return n && n.color ? " hl-" + n.color : ""; }

function prose(data) {
  const code = state.versions[0];
  const p = el("div", { className: "prose" });
  for (const v of data.verses) {
    const span = el("span", { className: "v" + (hlClass(v.osis)), dataset: { osis: v.osis } });
    span.append(el("span", { className: "vn", textContent: v.verse }));
    const t = el("span", { className: "vt", textContent: (v.texts[code] || "—") + " " });
    span.append(t);
    if (v.has_xrefs) span.append(el("sup", { className: "mark-x", textContent: "✦" }));
    span.onclick = () => selectVerse(v.osis);
    p.append(span, document.createTextNode(" "));
  }
  return p;
}

function grid(data) {
  const wrap = el("div", { className: "grid" });
  wrap.style.setProperty("--cols", state.versions.length);
  const head = el("div", { className: "colhead" }, [el("span", {})]);
  state.versions.forEach((c) => head.append(el("span", { textContent: c })));
  wrap.append(head);
  for (const v of data.verses) {
    const row = el("div", { className: "grow" + hlClass(v.osis), dataset: { osis: v.osis } });
    row.style.setProperty("--cols", state.versions.length);
    const gn = el("div", { className: "gn" });
    gn.append(document.createTextNode(v.verse));
    if (v.has_xrefs) gn.append(el("sup", { className: "mark-x", textContent: "✦" }));
    row.append(gn);
    state.versions.forEach((c) => row.append(el("div", { className: "gc" + (v.texts[c] ? "" : " empty"), textContent: v.texts[c] || "—" })));
    row.onclick = () => selectVerse(v.osis);
    wrap.append(row);
  }
  return wrap;
}

function markSelected() {
  document.querySelectorAll(".v.sel,.grow.sel").forEach((n) => n.classList.remove("sel"));
  const n = document.querySelector(`[data-osis="${state.sel}"]`);
  if (n) n.classList.add("sel");
}

// ---------------------------------------------------------------- study panel
function closeStudy() { $("#studyBody").hidden = true; $("#studyEmpty").hidden = false; }
function selectVerse(osis) {
  state.sel = osis; markSelected();
  $("#studyEmpty").hidden = true; $("#studyBody").hidden = false;
  $("#studyRef").textContent = refLabel(osis);
  renderTab();
}
function refLabel(osis) { const [b, c, v] = osisParts(osis); return `${state.bookName[b] || b} ${c}:${v}`; }
function setTab(t) {
  state.tab = t;
  document.querySelectorAll(".tab").forEach((x) => x.setAttribute("aria-selected", x.dataset.tab === t));
  renderTab();
}
async function renderTab() {
  document.querySelectorAll(".tab").forEach((x) => x.setAttribute("aria-selected", x.dataset.tab === state.tab));
  const panel = $("#tabpanel");
  panel.replaceChildren(el("div", { className: "study-empty", textContent: "Loading…" }));
  try {
    if (state.tab === "xref") panel.replaceChildren(await xrefPanel());
    else if (state.tab === "inter") panel.replaceChildren(await interPanel());
    else panel.replaceChildren(await notesPanel());
  } catch (e) {
    panel.replaceChildren(el("div", { className: "study-empty", textContent: "Couldn’t load: " + e.message }));
  }
}

async function xrefPanel() {
  const d = await api(`/api/verse/${state.sel}/crossrefs?translation=${state.versions[0]}&limit=40`);
  if (!d.crossrefs.length) return el("div", { className: "study-empty", textContent: "No cross-references for this verse." });
  const box = el("div", {});
  for (const x of d.crossrefs) {
    const b = el("button", { className: "xref", type: "button" }, [
      el("span", { className: "xref-ref", textContent: x.ref }),
      el("div", { className: "xref-text", textContent: x.text || "" }),
    ]);
    b.onclick = () => goTo(x.osis);
    box.append(b);
  }
  return box;
}

async function interPanel() {
  const d = await api(`/api/verse/${state.sel}/interlinear`);
  const box = el("div", {});
  if (!d.aligned) { box.append(el("div", { className: "note-banner", textContent: d.note })); return box; }
  for (const w of d.words) {
    const row = el("div", { className: "word " + w.language });
    row.append(el("div", { className: "orig", textContent: w.text }));
    if (w.strongs) {
      const s = el("button", { className: "sbtn", type: "button", textContent: w.strongs, dataset: { strongs: w.strongs } });
      row.append(s);
    } else row.append(el("span", {}));
    row.append(el("div", { className: "gloss" }, [
      document.createTextNode(w.gloss || ""),
      w.translit ? el("span", { className: "translit", textContent: "  " + w.translit }) : "",
    ]));
    if (w.morph) row.append(el("div", { className: "morph", textContent: w.morph }));
    box.append(row);
  }
  return box;
}

async function showStrongs(id) {
  const panel = $("#tabpanel");
  const d = await api(`/api/strongs/${id}`);
  const wrap = el("div", { className: "strong" });
  wrap.append(el("button", { className: "backlink", type: "button", textContent: "‹ Back to words", onclick: renderTab }));
  wrap.append(el("div", {}, [
    el("span", { className: "strong-lemma", textContent: d.lemma || id }),
    el("span", { className: "strong-translit", textContent: d.translit || "" }),
  ]));
  wrap.append(el("div", { className: "strong-meta", textContent: `${d.id} · ${d.language} · ${d.occurrences} occurrences${d.pronounce ? " · " + d.pronounce : ""}` }));
  const def = el("div", { className: "strong-def", textContent: d.definition || "" });
  if (d.kjv_def) { def.append(el("b", { textContent: "KJV usage" })); def.append(document.createTextNode(d.kjv_def)); }
  wrap.append(def);
  panel.replaceChildren(wrap);
}

async function notesPanel() {
  const current = state.notes[state.sel] || { color: "", body: "" };
  const box = el("div", {});
  const sw = el("div", { className: "swatches" });
  const colors = ["", ...Object.keys(HL)];
  colors.forEach((c) => {
    const b = el("button", { className: "swatch", type: "button", title: c || "no highlight" });
    b.style.background = c ? HL[c] : "transparent";
    if (!c) b.textContent = "∅";
    b.setAttribute("aria-pressed", (current.color || "") === c);
    b.onclick = () => { current.color = c; sw.querySelectorAll(".swatch").forEach((x) => x.setAttribute("aria-pressed", "false")); b.setAttribute("aria-pressed", "true"); };
    sw.append(b);
  });
  const ta = el("textarea", { className: "notearea", placeholder: "Write a note for this verse…", value: current.body || "" });
  const save = el("button", { className: "savebtn", type: "button", textContent: "Save note" });
  save.onclick = async () => {
    await fetch("/api/notes", { method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ osis: state.sel, color: current.color || "", body: ta.value }) });
    if (!current.color && !ta.value) delete state.notes[state.sel];
    else state.notes[state.sel] = { osis: state.sel, color: current.color || "", body: ta.value };
    save.textContent = "Saved";
    setTimeout(() => (save.textContent = "Save note"), 1200);
    // re-tint the verse in the reader
    const n = document.querySelector(`[data-osis="${state.sel}"]`);
    if (n) { n.className = n.className.replace(/\s*hl-\w+/g, ""); if (current.color) n.classList.add("hl-" + current.color); }
  };
  box.append(sw, ta, save);
  return box;
}

function onStudyClick(e) {
  const s = e.target.closest(".sbtn");
  if (s) showStrongs(s.dataset.strongs);
}

// ---------------------------------------------------------------- navigation + search
async function goTo(osis) {
  const [b, c] = osisParts(osis);
  state.book = b; state.chapter = c;
  await loadChapter();
  selectVerse(osis);
  const n = document.querySelector(`[data-osis="${osis}"]`);
  if (n) n.scrollIntoView({ block: "center", behavior: "smooth" });
}

async function runSearch(q) {
  const d = await api(`/api/search?q=${encodeURIComponent(q)}&translation=${state.versions[0]}&limit=150`);
  const r = $("#reader"); r.replaceChildren();
  const head = el("div", { className: "results-head" }, [
    el("h2", { textContent: `“${q}”` }),
    el("span", { style: "font-size:.85rem;color:var(--ink-faint)", textContent: `${d.count} result${d.count === 1 ? "" : "s"} · ${d.translation}` }),
  ]);
  r.append(head);
  if (!d.count) { r.append(el("div", { className: "study-empty", textContent: "Nothing found. Try different words." })); return; }
  for (const res of d.results) {
    const b = el("button", { className: "result", type: "button" });
    b.append(el("div", { className: "result-ref", textContent: res.ref }));
    const snip = el("div", { className: "result-snip" });
    snip.innerHTML = res.snippet;           // snippet markup is from our own API (safe)
    b.append(snip);
    b.onclick = () => goTo(res.osis);
    r.append(b);
  }
}

// ---------------------------------------------------------------- theme
function applyTheme(mode) {
  if (mode === "auto") document.documentElement.removeAttribute("data-theme");
  else document.documentElement.setAttribute("data-theme", mode);
  store.set("theme", mode);
}
function cycleTheme() {
  const order = ["auto", "light", "dark"];
  const cur = store.get("theme", "auto");
  applyTheme(order[(order.indexOf(cur) + 1) % order.length]);
}

init().catch((e) => { document.body.append(el("div", { style: "padding:2rem;font-family:sans-serif", textContent: "Failed to start: " + e.message })); });
