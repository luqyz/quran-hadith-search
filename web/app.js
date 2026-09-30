import { initializeApp } from "https://www.gstatic.com/firebasejs/10.12.2/firebase-app.js";
import {
  getFirestore, collection, addDoc, serverTimestamp,
} from "https://www.gstatic.com/firebasejs/10.12.2/firebase-firestore.js";

const { API_BASE, FIREBASE } = window.APP_CONFIG;

let db = null;
try {
  if (FIREBASE && FIREBASE.projectId) db = getFirestore(initializeApp(FIREBASE));
} catch (e) {
  console.warn("Firebase tidak aktif:", e);
}

const $ = (sel) => document.querySelector(sel);
const form = $("#search-form");
const input = $("#q");
const statusEl = $("#status");
const noticeEl = $("#notice");
const resultsEl = $("#results");
const tabsEl = $("#tabs");
const toastEl = $("#toast");

let activeTab = "quran";

const NOTICES = {
  fatwa:
    'Soalan anda kelihatan berkaitan <strong>hukum</strong>. Sistem ini hanya memaparkan teks Al-Quran dan hadis, bukan fatwa. ' +
    'Untuk keputusan hukum, rujuk <a href="https://www.e-fatwa.gov.my" target="_blank" rel="noopener">portal e-Fatwa</a> atau pejabat mufti negeri anda.',
  current_info:
    "Soalan anda kelihatan meminta maklumat semasa (contohnya tarikh, harga atau waktu). " +
    "Sistem ini mencari teks Al-Quran dan hadis sahaja, jadi hasil di bawah mungkin tidak menjawab soalan tersebut.",
};

const esc = (s) =>
  String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

/* ---------- Kad ---------- */

function quranCard(r, i) {
  const ctx = [r.context?.prev, r.context?.next].filter(Boolean);
  const label = `Surah ${r.surah_name} · ${r.ref}`;
  const copyText = `${r.text_ms || r.text_en || ""}\n(Al-Quran, ${label})`;
  return `
    <article class="card glass" style="--i:${i}">
      <div class="card-top">
        <span class="pill">${esc(label)}</span>
        <button type="button" class="ghost-btn" data-copy="${esc(copyText)}">Salin</button>
      </div>
      ${r.text_ar ? `<p class="arabic" lang="ar" dir="rtl">${esc(r.text_ar)}</p>` : ""}
      ${r.text_ms ? `<p class="main">${esc(r.text_ms)}</p>` : ""}
      ${r.text_en ? `<details><summary>Terjemahan Inggeris</summary><p class="sub">${esc(r.text_en)}</p></details>` : ""}
      ${ctx.length ? `<details><summary>Ayat sebelum &amp; selepas</summary>${ctx
        .map((c) => `<p class="sub"><span class="mini-ref">${esc(c.ref)}</span>${esc(c.text_ms)}</p>`)
        .join("")}</details>` : ""}
    </article>`;
}

function hadithCard(r, i) {
  const number = String(r.ref || "").split(" ").pop();
  const label = `${r.collection} · ${number}`;
  const grade = r.grade_source === "collection" ? `${r.grade} (koleksi)` : r.grade;
  const copyText = `${r.text_en || ""}\n(${label})`;
  return `
    <article class="card glass" style="--i:${i}">
      <div class="card-top">
        <span class="pill">${esc(label)}</span>
        <div class="card-actions">
          ${r.grade ? `<span class="badge">${esc(grade)}</span>` : ""}
          <button type="button" class="ghost-btn" data-copy="${esc(copyText)}">Salin</button>
        </div>
      </div>
      ${r.book_title ? `<p class="book">${esc(r.book_title)}</p>` : ""}
      <p class="main">${esc(r.text_en)}</p>
      ${r.text_ar ? `<details><summary>Teks Arab</summary><p class="arabic" lang="ar" dir="rtl">${esc(r.text_ar)}</p></details>` : ""}
    </article>`;
}

/* ---------- Bahagian ---------- */

function sectionHtml(key, title, unit, sec, cardFn, note) {
  const n = sec.results.length;
  return `
    <section class="col${key === activeTab ? " is-active" : ""}" data-col="${key}" role="tabpanel">
      <header class="col-head"><h2>${title}</h2><span class="muted">${n} ${unit}</span></header>
      ${note ? `<p class="note">${note}</p>` : ""}
      ${sec.confident ? "" : `<p class="warn glass">Hasil di bahagian ini mungkin kurang berkaitan dengan soalan anda.</p>`}
      ${n ? sec.results.map(cardFn).join("") : `<p class="muted">Tiada hasil.</p>`}
    </section>`;
}

function skeleton() {
  const card = `<div class="card glass skeleton"><span></span><span></span><span></span><span class="short"></span></div>`;
  const col = (key, title) => `
    <section class="col${key === activeTab ? " is-active" : ""}" data-col="${key}">
      <header class="col-head"><h2>${title}</h2></header>
      ${card.repeat(3)}
    </section>`;
  return col("quran", "Al-Quran") + col("hadith", "Hadis");
}

function render(data) {
  const { quran, hadith } = data.sections;
  if (data.notice && NOTICES[data.notice]) {
    noticeEl.innerHTML = NOTICES[data.notice];
    noticeEl.hidden = false;
  }
  $("#count-quran").textContent = quran.results.length;
  $("#count-hadith").textContent = hadith.results.length;
  resultsEl.innerHTML =
    sectionHtml("quran", "Al-Quran", "ayat", quran, quranCard) +
    sectionHtml("hadith", "Hadis", "hadis", hadith, hadithCard,
      "Terjemahan Bahasa Melayu untuk hadis belum tersedia; teks Inggeris yang sahih dipaparkan.");
}

function setTab(key) {
  activeTab = key;
  tabsEl.querySelectorAll("[data-tab]").forEach((b) =>
    b.setAttribute("aria-selected", String(b.dataset.tab === key)));
  resultsEl.querySelectorAll(".col").forEach((c) =>
    c.classList.toggle("is-active", c.dataset.col === key));
}

/* ---------- Log ---------- */

async function logSearch(data) {
  if (!db) return;
  try {
    await addDoc(collection(db, "search_logs"), {
      q: data.query.slice(0, 200),
      notice: data.notice ?? null,
      quran_confident: data.sections.quran.confident,
      hadith_confident: data.sections.hadith.confident,
      ts: serverTimestamp(),
    });
  } catch (e) {
    console.warn("Log carian gagal:", e);
  }
}

/* ---------- Carian ---------- */

async function search(q) {
  document.body.classList.add("has-results");
  statusEl.textContent = "";
  noticeEl.hidden = true;
  tabsEl.hidden = false;
  $("#count-quran").textContent = "";
  $("#count-hadith").textContent = "";
  resultsEl.innerHTML = skeleton();

  const slow = setTimeout(() => {
    statusEl.textContent = "Pelayan sedang dimulakan semula. Carian pertama boleh mengambil masa sehingga 1–2 minit...";
  }, 5000);

  try {
    const res = await fetch(`${API_BASE}/search?` + new URLSearchParams({ q, k: 5 }));
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    statusEl.textContent = "";
    render(data);
    logSearch(data);
  } catch (e) {
    console.error(e);
    resultsEl.innerHTML = "";
    tabsEl.hidden = true;
    statusEl.textContent = "Maaf, carian gagal. Sila cuba lagi sebentar lagi.";
  } finally {
    clearTimeout(slow);
  }
}

function run(q) {
  q = q.trim();
  if (q.length < 2) return;
  input.value = q;
  input.blur();
  const url = new URL(window.location);
  url.searchParams.set("q", q);
  history.replaceState(null, "", url);
  window.scrollTo({ top: 0 });
  search(q);
}

/* ---------- Notifikasi ---------- */

let toastTimer;
function toast(msg) {
  toastEl.textContent = msg;
  toastEl.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toastEl.classList.remove("show"), 1800);
}

/* ---------- Acara ---------- */

form.addEventListener("submit", (e) => {
  e.preventDefault();
  run(input.value);
});

document.querySelectorAll(".chip").forEach((btn) =>
  btn.addEventListener("click", () => run(btn.dataset.q)));

tabsEl.addEventListener("click", (e) => {
  const btn = e.target.closest("[data-tab]");
  if (btn) setTab(btn.dataset.tab);
});

resultsEl.addEventListener("click", async (e) => {
  const btn = e.target.closest("[data-copy]");
  if (!btn) return;
  try {
    await navigator.clipboard.writeText(btn.dataset.copy);
    toast("Disalin ke papan klip");
  } catch {
    toast("Tidak dapat menyalin");
  }
});

document.addEventListener("keydown", (e) => {
  if (e.key === "/" && document.activeElement !== input) {
    e.preventDefault();
    input.focus();
  }
});

// Buka terus dengan ?q=... (boleh dikongsi), atau "kejutkan" pelayan lebih awal
const initial = new URLSearchParams(window.location.search).get("q");
if (initial) run(initial);
else fetch(`${API_BASE}/health`).catch(() => {});

/* ---------- Tema ---------- */

const themeBtn = $("#theme-toggle");
const systemDark = window.matchMedia("(prefers-color-scheme: dark)");

function currentTheme() {
  return document.documentElement.getAttribute("data-theme") || (systemDark.matches ? "dark" : "light");
}

function updateThemeLabel() {
  themeBtn.setAttribute("aria-label",
    currentTheme() === "dark" ? "Tukar ke mod cerah" : "Tukar ke mod gelap");
}

themeBtn.addEventListener("click", () => {
  const next = currentTheme() === "dark" ? "light" : "dark";
  document.documentElement.setAttribute("data-theme", next);
  try { localStorage.setItem("theme", next); } catch {}
  updateThemeLabel();
});

systemDark.addEventListener("change", updateThemeLabel);
updateThemeLabel();