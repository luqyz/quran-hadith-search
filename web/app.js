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
const langToggle = $("#lang-toggle");
const surahPlayBtn = $("#surah-play");
const viewSearch = $("#view-search");
const viewLibrary = $("#view-library");
const viewArbain = $("#view-arbain");
const surahGrid = $("#surah-grid");
const surahFilter = $("#surah-filter");
const resumeEl = $("#resume");
const arbainGrid = $("#arbain-grid");

let activeTab = "quran";
let lastQuery = "";
let surahList = null;
let nawawiList = null;
let readerSurah = null;
let readerAyahCount = 0;

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

const storage = {
  get(key, fallback = null) {
    try {
      const v = localStorage.getItem(key);
      return v === null ? fallback : JSON.parse(v);
    } catch {
      return fallback;
    }
  },
  set(key, value) {
    try { localStorage.setItem(key, JSON.stringify(value)); } catch {}
  },
};

/* ---------- Senarai surah (dikongsi oleh perpustakaan & audio) ---------- */

let surahListPromise = null;
let ayahOffsets = null;

function ensureSurahList() {
  if (surahList) return Promise.resolve(surahList);
  if (!surahListPromise) {
    surahListPromise = fetch(`${API_BASE}/surahs`)
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
      })
      .then((list) => {
        surahList = list;
        ayahOffsets = [0];
        for (const s of list) ayahOffsets.push(ayahOffsets[ayahOffsets.length - 1] + s.ayah_count);
        return list;
      })
      .catch((e) => {
        surahListPromise = null;
        throw e;
      });
  }
  return surahListPromise;
}

/* ---------- Kad hasil carian ---------- */
const ICON_UP = `<svg class="ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M7 10v12"/><path d="M15 5.88 14 10h5.83a2 2 0 0 1 1.92 2.56l-2.33 8A2 2 0 0 1 17.5 22H4a2 2 0 0 1-2-2v-8a2 2 0 0 1 2-2h2.76a2 2 0 0 0 1.79-1.11L12 2a3.13 3.13 0 0 1 3 3.88Z"/></svg>`;
const ICON_DOWN = `<svg class="ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M17 14V2"/><path d="M9 18.12 10 14H4.17a2 2 0 0 1-1.92-2.56l2.33-8A2 2 0 0 1 6.5 2H20a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2h-2.76a2 2 0 0 0-1.79 1.11L12 22a3.13 3.13 0 0 1-3-3.88Z"/></svg>`;

function voteButtons(section, id, i) {
  return `
    <span class="vote" data-vote-for="${esc(id)}" data-section="${section}" data-rank="${i + 1}">
      <button type="button" class="tool" data-vote="1" aria-label="Hasil ini berguna" title="Berguna">${ICON_UP}</button>
      <button type="button" class="tool" data-vote="-1" aria-label="Hasil ini tidak berguna" title="Tidak berguna">${ICON_DOWN}</button>
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
  updatePlayButtons();
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

async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
    toast("Disalin ke papan klip");
  } catch {
    toast("Tidak dapat menyalin");
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
  url.hash = "";
  history.replaceState(null, "", url);
  route();
  window.scrollTo({ top: 0 });
  search(q);
}

/* ---------- Audio ---------- */

// Nombor ayat global (1–6236) diperlukan oleh CDN audio
const AUDIO_BASE = "https://cdn.islamic.network/quran/audio/128/ar.alafasy";

let playingKey = null;   // "surah:ayat" yang sedang dimainkan
let surahQueue = null;   // { s, total } bila memainkan seluruh surah

function audioUrl(s, a) {
  return `${AUDIO_BASE}/${ayahOffsets[s - 1] + a}.mp3`;
}

function updatePlayButtons() {
  const playing = Boolean(playingKey) && !player.paused;
  document.querySelectorAll("[data-play]").forEach((b) => {
    const on = playing && b.dataset.play === playingKey;
    b.textContent = on ? "❚❚ Henti" : "▶ Dengar";
    b.classList.toggle("is-playing", on);
  });

  readerBody.querySelectorAll(".is-playing-ayah").forEach((el) => el.classList.remove("is-playing-ayah"));
  const surahOn = playing && surahQueue && surahQueue.s === readerSurah;
  if (surahOn) {
    const el = document.getElementById(`r-${playingKey.split(":")[1]}`);
    if (el) {
      el.classList.add("is-playing-ayah");
      el.scrollIntoView({ block: "center", behavior: "smooth" });
    }
  }
  surahPlayBtn.textContent = surahOn ? "❚❚ Henti surah" : "▶ Main surah";
  surahPlayBtn.classList.toggle("is-playing", Boolean(surahOn));
}

async function playAyah(s, a) {
  try {
    await ensureSurahList();
  } catch {
    toast("Audio belum sedia. Cuba lagi sebentar lagi.");
    return;
  }
  playingKey = `${s}:${a}`;
  player.src = audioUrl(s, a);
  player.play().catch(() => {
    toast("Audio tidak dapat dimainkan");
    surahQueue = null;
    updatePlayButtons();
  });
}

function togglePlay(btn) {
  const key = btn.dataset.play;
  if (playingKey === key && !player.paused) {
    player.pause();
    return;
  }
  surahQueue = null;
  const [s, a] = key.split(":").map(Number);
  playAyah(s, a);
}

function toggleSurah() {
  if (surahQueue && !player.paused) {
    surahQueue = null;
    player.pause();
    return;
  }
  if (!readerSurah) return;
  surahQueue = { s: readerSurah, total: readerAyahCount };
  playAyah(readerSurah, 1);
}

function stopAudio() {
  surahQueue = null;
  player.pause();
}

player.addEventListener("play", updatePlayButtons);
player.addEventListener("pause", updatePlayButtons);
player.addEventListener("ended", () => {
  if (surahQueue && playingKey) {
    const [s, a] = playingKey.split(":").map(Number);
    if (s === surahQueue.s && a < surahQueue.total) {
      playAyah(s, a + 1);
      return;
    }
  }
  surahQueue = null;
  updatePlayButtons();
});

/* ---------- Pembaca (surah & hadis) ---------- */

let readerLang = storage.get("readerLang", "ms");

function applyReaderLang() {
  readerBody.dataset.lang = readerLang;
  langToggle.querySelectorAll("[data-lang]").forEach((b) =>
    b.setAttribute("aria-pressed", String(b.dataset.lang === readerLang)));
}

function showReader(mode) {
  reader.dataset.mode = mode;
  reader.hidden = false;
  document.body.classList.add("no-scroll");
}

async function openReader(s, a = 1, highlight = true) {
  s = Number(s);
  a = Number(a);
  if (surahQueue && surahQueue.s !== s) stopAudio();

  showReader("quran");
  applyReaderLang();
  readerTitle.textContent = "Memuatkan surah...";
  readerMeta.textContent = "";
  readerBody.innerHTML = `<div class="card skeleton"><span></span><span></span><span class="short"></span></div>`;

  try {
    const res = await fetch(`${API_BASE}/surah/${s}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    const m = data.surah || {};
    readerSurah = s;
    readerAyahCount = data.ayahs.length;
    readerTitle.innerHTML = `${s}. ${esc(m.english_name)} <span class="ar-name" lang="ar">${esc(m.name_ar)}</span>`;
    readerMeta.textContent = [m.translation, revelationLabel(m.revelation), m.ayah_count && `${m.ayah_count} ayat`]
      .filter(Boolean).join(" · ");

    const bismillah = s !== 1 && s !== 9
      ? `<p class="arabic bismillah" lang="ar" dir="rtl">بِسْمِ اللَّهِ الرَّحْمَٰنِ الرَّحِيمِ</p>` : "";
    const ayahs = data.ayahs.map((x) => `
      <div class="r-ayah${highlight && x.ayah === a ? " is-target" : ""}" id="r-${x.ayah}">
        <div class="r-head">
          <span class="mini-ref">${esc(x.ref)}</span>
          <button type="button" class="tool" data-play="${s}:${x.ayah}">▶ Dengar</button>
        </div>
        ${x.text_ar ? `<p class="arabic" lang="ar" dir="rtl">${esc(x.text_ar)}</p>` : ""}
        ${x.text_ms ? `<p class="main t-ms">${esc(x.text_ms)}</p>` : ""}
        ${x.text_en ? `<p class="sub t-en">${esc(x.text_en)}</p>` : ""}
      </div>`).join("");
    const nav = `
      <nav class="r-nav">
        ${s > 1 ? `<button type="button" class="tool" data-open-surah="${s - 1}">← Surah sebelum</button>` : "<span></span>"}
        ${s < 114 ? `<button type="button" class="tool" data-open-surah="${s + 1}">Surah seterusnya →</button>` : ""}
      </nav>`;
    readerBody.innerHTML = bismillah + ayahs + nav;
    updatePlayButtons();

    storage.set("lastRead", { s, name: m.english_name || `Surah ${s}` });
    renderResume();

    const target = highlight ? document.getElementById(`r-${a}`) : null;
    if (target) target.scrollIntoView({ block: "center" });
    else readerBody.scrollTop = 0;
  } catch (e) {
    console.error(e);
    readerSurah = null;
    readerTitle.textContent = "Gagal memuatkan surah";
    readerBody.innerHTML = `<p class="muted">Sila cuba lagi sebentar lagi.</p>`;
  }
}

function openNawawi(n) {
  n = Number(n);
  const h = nawawiList?.find((x) => x.number === n);
  if (!h) return;
  if (surahQueue) stopAudio();
  readerSurah = null;

  showReader("nawawi");
  readerTitle.textContent = `Hadis ${n}: ${h.title_ms}`;
  readerMeta.textContent = `Hadis 40 Imam an-Nawawi · Riwayat: ${h.sources}`;
  const copy = `${h.text_en}\n(Hadis 40 Imam an-Nawawi, no. ${n})`;
  readerBody.innerHTML = `
    <div class="r-ayah">
      <div class="r-head">
        <span class="mini-ref">Hadis ${n}</span>
        <button type="button" class="tool" data-copy="${esc(copy)}">Salin</button>
      </div>
      ${h.text_ar ? `<p class="arabic" lang="ar" dir="rtl">${esc(h.text_ar)}</p>` : ""}
      <p class="main">${esc(h.text_en)}</p>
      <p class="note">Terjemahan Bahasa Melayu belum tersedia; terjemahan Inggeris dipaparkan. Tajuk ialah ringkasan.</p>
    </div>
    <nav class="r-nav">
      ${n > 1 ? `<button type="button" class="tool" data-open-nawawi="${n - 1}">← Hadis sebelum</button>` : "<span></span>"}
      ${n < nawawiList.length ? `<button type="button" class="tool" data-open-nawawi="${n + 1}">Hadis seterusnya →</button>` : ""}
    </nav>`;
  readerBody.scrollTop = 0;
  updatePlayButtons();
}

function closeReader() {
  if (surahQueue) stopAudio();
  reader.hidden = true;
  document.body.classList.remove("no-scroll");
}

/* ---------- Perpustakaan surah ---------- */

const normalize = (s) =>
  String(s ?? "").toLowerCase().replace(/[^a-z0-9]/g, "").replace(/(.)\1+/g, "$1").replace(/h$/, "");

function renderSurahs(filter = "") {
  if (!surahList) return;
  const f = normalize(filter);
  const items = surahList.filter((s) =>
    !f || String(s.number) === filter.trim() ||
    normalize(s.english_name).includes(f) || normalize(s.translation).includes(f));
  surahGrid.innerHTML = items.length ? items.map((s, i) => `
    <button type="button" class="surah-card glass" data-open-surah="${s.number}" style="--i:${Math.min(i, 20)}">
      <span class="surah-no"><span>${s.number}</span></span>
      <span class="surah-names">
        <strong>${esc(s.english_name)}</strong>
        <span class="muted">${esc(s.translation)}</span>
      </span>
      <span class="surah-side">
        <span class="surah-ar" lang="ar">${esc(s.name_ar)}</span>
        <span class="muted">${revelationLabel(s.revelation)} · ${s.ayah_count} ayat</span>
      </span>
    </button>`).join("") : `<p class="muted">Tiada surah sepadan.</p>`;
}

function renderResume() {
  const last = storage.get("lastRead");
  if (!last) {
    resumeEl.hidden = true;
    return;
  }
  resumeEl.hidden = false;
  resumeEl.innerHTML =
    `<button type="button" class="resume-btn glass" data-open-surah="${last.s}">` +
    `Sambung bacaan: <strong>${esc(last.name)}</strong> →</button>`;
}

async function loadLibrary() {
  renderResume();
  if (surahList) {
    renderSurahs(surahFilter.value);
    return;
  }
  surahGrid.innerHTML = `<div class="card glass skeleton"><span></span><span class="short"></span></div>`.repeat(6);
  try {
    await ensureSurahList();
    renderSurahs(surahFilter.value);
  } catch (e) {
    console.error(e);
    surahGrid.innerHTML = `<p class="muted">Gagal memuatkan senarai surah. Pelayan mungkin sedang dimulakan; cuba lagi sebentar lagi.</p>`;
  }
}

/* ---------- Hadis 40 ---------- */

function renderArbain() {
  arbainGrid.innerHTML = nawawiList.map((h, i) => `
    <button type="button" class="surah-card glass" data-open-nawawi="${h.number}" style="--i:${Math.min(i, 20)}">
      <span class="surah-no"><span>${h.number}</span></span>
      <span class="surah-names">
        <strong>${esc(h.title_ms)}</strong>
        <span class="muted">Riwayat: ${esc(h.sources)}</span>
      </span>
    </button>`).join("");
}

async function loadArbain() {
  if (nawawiList) {
    renderArbain();
    return;
  }
  arbainGrid.innerHTML = `<div class="card glass skeleton"><span></span><span class="short"></span></div>`.repeat(6);
  try {
    const res = await fetch(`${API_BASE}/nawawi`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    nawawiList = await res.json();
    renderArbain();
  } catch (e) {
    console.error(e);
    arbainGrid.innerHTML = `<p class="muted">Gagal memuatkan Hadis 40. Pelayan mungkin sedang dimulakan; cuba lagi sebentar lagi.</p>`;
  }
}

/* ---------- Navigasi ---------- */

function currentView() {
  if (location.hash === "#quran") return "library";
  if (location.hash === "#arbain") return "arbain";
  return "search";
}

function route() {
  const view = currentView();
  viewSearch.hidden = view !== "search";
  viewLibrary.hidden = view !== "library";
  viewArbain.hidden = view !== "arbain";
  if (view === "library") loadLibrary();
  if (view === "arbain") loadArbain();
  if (view !== "search") window.scrollTo({ top: 0 });
}

window.addEventListener("hashchange", route);

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

resultsEl.addEventListener("click", (e) => {
  const t = e.target;

  const copyBtn = t.closest("[data-copy]");
  if (copyBtn) return copyText(copyBtn.dataset.copy);

  const playBtn = t.closest("[data-play]");
  if (playBtn) return togglePlay(playBtn);

  const readBtn = t.closest("[data-read]");
  if (readBtn) {
    const [s, a] = readBtn.dataset.read.split(":");
    return openReader(s, a, true);
  }

  const simBtn = t.closest("[data-similar]");
  if (simBtn) return toggleSimilar(simBtn);

  const voteBtn = t.closest("[data-vote]");
  if (voteBtn) return vote(voteBtn);
});

viewLibrary.addEventListener("click", (e) => {
  const btn = e.target.closest("[data-open-surah]");
  if (btn) openReader(btn.dataset.openSurah, 1, false);
});

viewArbain.addEventListener("click", (e) => {
  const btn = e.target.closest("[data-open-nawawi]");
  if (btn) openNawawi(btn.dataset.openNawawi);
});

surahFilter.addEventListener("input", () => renderSurahs(surahFilter.value));

surahPlayBtn.addEventListener("click", toggleSurah);

reader.addEventListener("click", (e) => {
  const t = e.target;
  if (t.closest("[data-close]")) return closeReader();

  const langBtn = t.closest("#lang-toggle [data-lang]");
  if (langBtn) {
    readerLang = langBtn.dataset.lang;
    storage.set("readerLang", readerLang);
    return applyReaderLang();
  }

  const surahNav = t.closest("[data-open-surah]");
  if (surahNav) return openReader(surahNav.dataset.openSurah, 1, false);

  const hadithNav = t.closest("[data-open-nawawi]");
  if (hadithNav) return openNawawi(hadithNav.dataset.openNawawi);

  const copyBtn = t.closest("[data-copy]");
  if (copyBtn) return copyText(copyBtn.dataset.copy);

  const playBtn = t.closest("[data-play]");
  if (playBtn) togglePlay(playBtn);
});

document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && !reader.hidden) {
    closeReader();
    return;
  }
  if (e.key === "/" && reader.hidden && !["INPUT", "TEXTAREA"].includes(document.activeElement.tagName)) {
    const view = currentView();
    if (view === "arbain") return;
    e.preventDefault();
    (view === "library" ? surahFilter : input).focus();
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

route();
ensureSurahList().catch(() => {});   // juga "mengejutkan" pelayan dan menyediakan audio
const initial = new URLSearchParams(window.location.search).get("q");
if (initial && currentView() === "search") run(initial);