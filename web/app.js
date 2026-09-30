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

const $ = (id) => document.getElementById(id);
const form = $("search-form");
const input = $("q");
const statusEl = $("status");
const noticeEl = $("notice");
const resultsEl = $("results");

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

function quranCard(r) {
  const ctx = [r.context?.prev, r.context?.next].filter(Boolean);
  return `
    <article class="card">
      <header class="card-head"><span class="ref">Surah ${esc(r.surah_name)} · ${esc(r.ref)}</span></header>
      ${r.text_ar ? `<p class="arabic" lang="ar" dir="rtl">${esc(r.text_ar)}</p>` : ""}
      ${r.text_ms ? `<p class="text-main">${esc(r.text_ms)}</p>` : ""}
      ${r.text_en ? `<details><summary>Terjemahan Inggeris</summary><p class="text-en">${esc(r.text_en)}</p></details>` : ""}
      ${ctx.length ? `<details><summary>Ayat sebelum dan selepas</summary>${ctx
        .map((c) => `<p class="ctx"><span class="ref">${esc(c.ref)}</span> ${esc(c.text_ms)}</p>`)
        .join("")}</details>` : ""}
    </article>`;
}

function hadithCard(r) {
  const number = String(r.ref || "").split(" ").pop();
  const grade = r.grade_source === "collection"
    ? `${esc(r.grade)} (koleksi ${esc(r.collection)})`
    : esc(r.grade);
  return `
    <article class="card">
      <header class="card-head">
        <span class="ref">${esc(r.collection)} · ${esc(number)}</span>
        ${r.grade ? `<span class="badge">${grade}</span>` : ""}
      </header>
      ${r.book_title ? `<p class="book">${esc(r.book_title)}</p>` : ""}
      <p class="text-main">${esc(r.text_en)}</p>
      ${r.text_ar ? `<details><summary>Teks Arab</summary><p class="arabic" lang="ar" dir="rtl">${esc(r.text_ar)}</p></details>` : ""}
    </article>`;
}

function section(title, sec, cardFn, note) {
  const warn = sec.confident
    ? ""
    : `<p class="warn">Hasil di bahagian ini mungkin kurang berkaitan dengan soalan anda.</p>`;
  const body = sec.results.length
    ? sec.results.map(cardFn).join("")
    : `<p class="muted">Tiada hasil.</p>`;
  return `
    <section class="col">
      <h2>${title}</h2>
      ${note ? `<p class="muted small">${note}</p>` : ""}
      ${warn}
      ${body}
    </section>`;
}

function render(data) {
  if (data.notice && NOTICES[data.notice]) {
    noticeEl.innerHTML = NOTICES[data.notice];
    noticeEl.hidden = false;
  }
  resultsEl.innerHTML =
    section("Al-Quran", data.sections.quran, quranCard) +
    section("Hadis", data.sections.hadith, hadithCard,
      "Terjemahan Bahasa Melayu untuk hadis belum tersedia; teks Inggeris yang sahih dipaparkan.");
}

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

async function search(q) {
  statusEl.textContent = "Mencari...";
  noticeEl.hidden = true;
  resultsEl.innerHTML = "";
  const slow = setTimeout(() => {
    statusEl.textContent =
      "Pelayan sedang dimulakan semula. Carian pertama boleh mengambil masa sehingga 1–2 minit...";
  }, 5000);

  try {
    const res = await fetch(`${API_BASE}/search?` + new URLSearchParams({ q, k: 5 }));
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    render(data);
    statusEl.textContent = "";
    logSearch(data);
  } catch (e) {
    console.error(e);
    statusEl.textContent = "Maaf, carian gagal. Sila cuba lagi sebentar lagi.";
  } finally {
    clearTimeout(slow);
  }
}

function run(q) {
  q = q.trim();
  if (q.length < 2) return;
  input.value = q;
  const url = new URL(window.location);
  url.searchParams.set("q", q);
  history.replaceState(null, "", url);
  search(q);
}

form.addEventListener("submit", (e) => {
  e.preventDefault();
  run(input.value);
});

document.querySelectorAll(".examples button").forEach((btn) =>
  btn.addEventListener("click", () => run(btn.dataset.q)));

// Buka terus dengan ?q=... (boleh dikongsi), atau "kejutkan" pelayan lebih awal
const initial = new URLSearchParams(window.location.search).get("q");
if (initial) run(initial);
else fetch(`${API_BASE}/health`).catch(() => {});