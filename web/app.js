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
const player = $("#player");
const reader = $("#reader");
const readerTitle = $("#reader-title");
const readerMeta = $("#reader-meta");
const readerBody = $("#reader-body");

let activeTab = "quran";
let lastQuery = "";

const NOTICES = {
  fatwa:
    'Soalan anda kelihatan berkaitan <strong>hukum</strong>. Sistem ini hanya memaparkan teks Al-Quran dan hadis, bukan fatwa. ' +
    'Untuk keputusan hukum, rujuk <a href="https://efatwa.muftiwp.gov.my/" target="_blank" rel="noopener">portal e-Fatwa</a> atau pejabat mufti negeri anda.',
  current_info:
    "Soalan anda kelihatan meminta maklumat semasa (contohnya tarikh, harga atau waktu). " +
    "Sistem ini mencari teks Al-Quran dan hadis sahaja, jadi hasil di bawah mungkin tidak menjawab soalan tersebut.",
};

const esc = (s) =>
  String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

const shorten = (s, n) => {
  s = String(s ?? "");
  return s.length > n ? s.slice(0, n).trimEnd() + "…" : s;
};

const revelationLabel = (r) => (r === "Meccan" ? "Makkiyah" : r === "Medinan" ? "Madaniyah" : "");

/* ---------- Kad ---------- */

function voteButtons(section, id, i) {
  return `
    <span class="vote" data-vote-for="${esc(id)}" data-section="${section}" data-rank="${i + 1}">
      <button type="button" class="tool" data-vote="1" aria-label="Hasil ini berguna">👍</button>
      <button type="button" class="tool" data-vote="-1" aria-label="Hasil ini tidak berguna">👎</button>
    </span>`;
}

function quranCard(r, i) {
  const ctx = [r.context?.prev, r.context?.next].filter(Boolean);
  const label = `Surah ${r.surah_name} · ${r.ref}`;
  const rev = revelationLabel(r.revelation);
  const copyText = `${r.text_ms || r.text_en || ""}\n(Al-Quran, ${label})`;
  return `
    <article class="card glass" style="--i:${i}">
      <div class="card-top">
        <span class="pill">${esc(label)}</span>
        <div class="card-actions">
          ${rev ? `<span class="badge">${rev}</span>` : ""}
          <button type="button" class="ghost-btn" data-copy="${esc(copyText)}">Salin</button>
        </div>
      </div>
      ${r.text_ar ? `<p class="arabic" lang="ar" dir="rtl">${esc(r.text_ar)}</p>` : ""}
      ${r.text_ms ? `<p class="main">${esc(r.text_ms)}</p>` : ""}
      ${r.text_en ? `<details><summary>Terjemahan Inggeris</summary><p class="sub">${esc(r.text_en)}</p></details>` : ""}
      ${ctx.length ? `<details><summary>Ayat sebelum &amp; selepas</summary>${ctx
        .map((c) => `<p class="sub"><span class="mini-ref">${esc(c.ref)}</span>${esc(c.text_ms)}</p>`)
        .join("")}</details>` : ""}
      <div class="tools">
        <button type="button" class="tool" data-play="${r.surah}:${r.ayah}">▶ Dengar</button>
        <button type="button" class="tool" data-read="${r.surah}:${r.ayah}">Baca surah</button>
        <button type="button" class="tool" data-similar="${esc(r.id)}">Ayat serupa</button>
        <a class="tool" href="https://quran.com/${r.surah}/${r.ayah}" target="_blank" rel="noopener">Tafsir ↗</a>
        ${voteButtons("quran", r.id, i)}
      </div>
      <div class="similar" hidden></div>
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
      <div class="tools">${voteButtons("hadith", r.id, i)}</div>
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

/* ---------- Log & maklum balas ---------- */

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

async function vote(btn) {
  const wrap = btn.closest("[data-vote-for]");
  if (!wrap || wrap.classList.contains("voted")) return;
  wrap.classList.add("voted");
  wrap.querySelectorAll("button").forEach((b) => { b.disabled = true; });
  btn.classList.add("chosen");
  if (!db) {
    toast("Terima kasih!");
    return;
  }
  try {
    await addDoc(collection(db, "feedback"), {
      q: lastQuery.slice(0, 200),
      doc_id: wrap.dataset.voteFor,
      section: wrap.dataset.section,
      rank: Number(wrap.dataset.rank),
      vote: Number(btn.dataset.vote),
      ts: serverTimestamp(),
    });
    toast("Terima kasih atas maklum balas!");
  } catch (e) {
    console.warn("Maklum balas gagal:", e);
    toast("Maklum balas gagal dihantar");
  }
}

/* ---------- Carian ---------- */

async function search(q) {
  lastQuery = q;
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

/* ---------- Audio ---------- */

let playingKey = null;
let playingBtn = null;

function audioUrl(s, a) {
  const p = (n) => String(n).padStart(3, "0");
  return `https://everyayah.com/data/Alafasy_128kbps/${p(s)}${p(a)}.mp3`;
}

function setPlayBtn(btn, playing) {
  if (!btn) return;
  btn.textContent = playing ? "❚❚ Henti" : "▶ Dengar";
  btn.classList.toggle("is-playing", playing);
}

function togglePlay(btn) {
  const key = btn.dataset.play;
  if (playingKey === key && !player.paused) {
    player.pause();
    return;
  }
  setPlayBtn(playingBtn, false);
  playingKey = key;
  playingBtn = btn;
  const [s, a] = key.split(":");
  player.src = audioUrl(s, a);
  player.play().catch(() => toast("Audio tidak dapat dimainkan"));
}

player.addEventListener("play", () => setPlayBtn(playingBtn, true));
player.addEventListener("pause", () => setPlayBtn(playingBtn, false));
player.addEventListener("ended", () => setPlayBtn(playingBtn, false));

/* ---------- Pembaca surah ---------- */

async function openReader(s, a) {
  reader.hidden = false;
  document.body.classList.add("no-scroll");
  readerTitle.textContent = "Memuatkan surah...";
  readerMeta.textContent = "";
  readerBody.innerHTML = `<div class="card skeleton"><span></span><span></span><span class="short"></span></div>`;

  try {
    const res = await fetch(`${API_BASE}/surah/${s}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    const m = data.surah || {};
    readerTitle.innerHTML = `${esc(m.english_name)} <span class="ar-name" lang="ar">${esc(m.name_ar)}</span>`;
    readerMeta.textContent = [m.translation, revelationLabel(m.revelation), m.ayah_count && `${m.ayah_count} ayat`]
      .filter(Boolean).join(" · ");

    const bismillah = Number(s) !== 1 && Number(s) !== 9
      ? `<p class="arabic bismillah" lang="ar" dir="rtl">بِسْمِ اللَّهِ الرَّحْمَٰنِ الرَّحِيمِ</p>` : "";
    readerBody.innerHTML = bismillah + data.ayahs.map((x) => `
      <div class="r-ayah${String(x.ayah) === String(a) ? " is-target" : ""}" id="r-${x.ayah}">
        <div class="r-head">
          <span class="mini-ref">${esc(x.ref)}</span>
          <button type="button" class="tool" data-play="${s}:${x.ayah}">▶ Dengar</button>
        </div>
        ${x.text_ar ? `<p class="arabic" lang="ar" dir="rtl">${esc(x.text_ar)}</p>` : ""}
        ${x.text_ms ? `<p class="main">${esc(x.text_ms)}</p>` : ""}
      </div>`).join("");

    const target = document.getElementById(`r-${a}`);
    if (target) target.scrollIntoView({ block: "center" });
  } catch (e) {
    console.error(e);
    readerTitle.textContent = "Gagal memuatkan surah";
    readerBody.innerHTML = `<p class="muted">Sila cuba lagi sebentar lagi.</p>`;
  }
}

function closeReader() {
  reader.hidden = true;
  document.body.classList.remove("no-scroll");
}

/* ---------- Ayat serupa ---------- */

async function toggleSimilar(btn) {
  const box = btn.closest(".card").querySelector(".similar");
  if (!box.hidden) {
    box.hidden = true;
    return;
  }
  box.hidden = false;
  box.innerHTML = `<p class="muted small">Mencari ayat dengan maksud yang dekat...</p>`;
  try {
    const res = await fetch(`${API_BASE}/similar/${encodeURIComponent(btn.dataset.similar)}?` +
      new URLSearchParams({ section: "quran", k: 5 }));
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    box.innerHTML = `<p class="similar-title">Ayat dengan maksud yang dekat</p>` + data.results.map((r) => `
      <button type="button" class="similar-item" data-read="${r.surah}:${r.ayah}">
        <span class="mini-ref">${esc(r.surah_name)} ${esc(r.ref)}</span>
        <span>${esc(shorten(r.text_ms, 150))}</span>
      </button>`).join("");
  } catch (e) {
    console.error(e);
    box.innerHTML = `<p class="muted small">Gagal memuatkan ayat serupa.</p>`;
  }
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
  const t = e.target;

  const copyBtn = t.closest("[data-copy]");
  if (copyBtn) {
    try {
      await navigator.clipboard.writeText(copyBtn.dataset.copy);
      toast("Disalin ke papan klip");
    } catch {
      toast("Tidak dapat menyalin");
    }
    return;
  }

  const playBtn = t.closest("[data-play]");
  if (playBtn) return togglePlay(playBtn);

  const readBtn = t.closest("[data-read]");
  if (readBtn) {
    const [s, a] = readBtn.dataset.read.split(":");
    return openReader(s, a);
  }

  const simBtn = t.closest("[data-similar]");
  if (simBtn) return toggleSimilar(simBtn);

  const voteBtn = t.closest("[data-vote]");
  if (voteBtn) return vote(voteBtn);
});

reader.addEventListener("click", (e) => {
  if (e.target.closest("[data-close]")) return closeReader();
  const playBtn = e.target.closest("[data-play]");
  if (playBtn) togglePlay(playBtn);
});

document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && !reader.hidden) {
    closeReader();
    return;
  }
  if (e.key === "/" && document.activeElement !== input && reader.hidden) {
    e.preventDefault();
    input.focus();
  }
});

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

/* ---------- Mula ---------- */

const initial = new URLSearchParams(window.location.search).get("q");
if (initial) run(initial);
else fetch(`${API_BASE}/health`).catch(() => {});