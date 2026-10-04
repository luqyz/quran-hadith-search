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
const surahRestartBtn = $("#surah-restart");
const viewSearch = $("#view-search");
const viewLibrary = $("#view-library");
const viewArbain = $("#view-arbain");
const viewMathurat = $("#view-mathurat");
const surahGrid = $("#surah-grid");
const surahFilter = $("#surah-filter");
const resumeEl = $("#resume");
const arbainGrid = $("#arbain-grid");
const libToggle = $("#lib-toggle");

let activeTab = "quran";
let lastQuery = "";
let surahList = null;
let juzList = null;
let nawawiList = null;
let libMode = "surah";

// Unit bacaan semasa: { kind: "surah" | "juz", n, name, keys: ["s:a", ...] }
let readerUnit = null;
let readerPos = null;     // kunci "s:a" ayat semasa (dari skrol atau audio)

const DEFAULT_K = 5;
const MORE_K = 10;

// Data bacaan dihidangkan sebagai fail statik oleh Firebase Hosting (dijana oleh scripts/export_static.py)
const DATA_BASE = "data";

const NOTICES = {
  fatwa:
    'Soalan anda kelihatan berkaitan <strong>hukum</strong>. Sistem ini hanya memaparkan teks Al-Quran dan hadis, bukan fatwa. ' +
    'Untuk keputusan hukum, rujuk <a href="https://efatwa.muftiwp.gov.my/" target="_blank" rel="noopener">portal e-Fatwa</a> atau pejabat mufti negeri anda.',
  current_info:
    "Soalan anda kelihatan meminta maklumat semasa (contohnya tarikh, harga atau waktu). " +
    "Sistem ini mencari teks Al-Quran dan hadis sahaja, jadi hasil di bawah mungkin tidak menjawab soalan tersebut.",
};

const BISMILLAH = `<p class="arabic bismillah" lang="ar" dir="rtl">بِسْمِ اللَّهِ الرَّحْمَٰنِ الرَّحِيمِ</p>`;

const esc = (s) =>
  String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

const shorten = (s, n) => {
  s = String(s ?? "");
  return s.length > n ? s.slice(0, n).trimEnd() + "…" : s;
};

const revelationLabel = (r) => (r === "Meccan" ? "Makkiyah" : r === "Medinan" ? "Madaniyah" : "");

const parseKey = (k) => String(k).split(":").map(Number);
const unitId = (u) => (u ? `${u.kind}:${u.n}` : null);

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

libMode = storage.get("libMode", "surah") === "juz" ? "juz" : "surah";

/* ---------- Senarai surah (dikongsi oleh perpustakaan, juz & audio) ---------- */

let surahListPromise = null;
let ayahOffsets = null;

function ensureSurahList() {
  if (surahList) return Promise.resolve(surahList);
  if (!surahListPromise) {
    surahListPromise = fetch(`${DATA_BASE}/surahs.json`)
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

const surahMeta = (s) => (surahList && surahList[s - 1]) || { english_name: `Surah ${s}`, name_ar: "" };

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

async function search(q, k = DEFAULT_K) {
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
    const res = await fetch(`${API_BASE}/search?` + new URLSearchParams({ q, k }));
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    statusEl.textContent = "";
    render(data);
    if (k < MORE_K) {
      resultsEl.insertAdjacentHTML("beforeend",
        `<div class="more-wrap"><button type="button" class="more-btn glass" data-more>Papar lebih banyak hasil</button></div>`);
    }
    if (k === DEFAULT_K) logSearch(data);   // log sekali sahaja untuk setiap carian
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

/* ---------- Kedudukan bacaan (disimpan dalam pelayar) ---------- */

let saveTimer;
let posObserver = null;

function getLastRead() {
  const last = storage.get("lastRead");
  if (!last) return null;
  if (last.kind) return last;
  // Format lama: { s, name, a }
  return { kind: "surah", n: last.s, name: last.name, key: `${last.s}:${last.a || 1}` };
}

function posLabel(key) {
  if (!key || !readerUnit) return "";
  const [s, a] = parseKey(key);
  return readerUnit.kind === "surah" ? `ayat ${a}` : `${s}:${a}`;
}

const atStart = () => !readerUnit || !readerPos || readerPos === readerUnit.keys[0];

function saveReadPos() {
  if (!readerUnit) return;
  const unit = readerUnit;
  clearTimeout(saveTimer);
  saveTimer = setTimeout(() => {
    storage.set("lastRead", {
      kind: unit.kind, n: unit.n, name: unit.name,
      key: readerPos, page: unit.pages?.[readerPos] ?? null,
    });
    renderResume();
  }, 400);
}

function setReadPos(key) {
  if (!readerUnit || !key || key === readerPos) return;
  readerPos = key;
  saveReadPos();
  updateSurahButton();
}

// Ikut ayat yang berada di tengah skrin semasa pengguna membaca
function watchReadPos() {
  if (posObserver) posObserver.disconnect();
  posObserver = new IntersectionObserver((entries) => {
    if (!readerUnit) return;
    if (readerBody.scrollTop < 40) return setReadPos(readerUnit.keys[0]);
    const hit = entries.find((en) => en.isIntersecting);
    if (hit) setReadPos(hit.target.dataset.key);
  }, { root: readerBody, rootMargin: "-45% 0px -45% 0px" });
  readerBody.querySelectorAll(".r-ayah[data-key]").forEach((el) => posObserver.observe(el));
}

function stopWatchReadPos() {
  if (posObserver) posObserver.disconnect();
  posObserver = null;
}

/* ---------- Audio ---------- */

// Nombor ayat global (1–6236) diperlukan oleh CDN audio
const AUDIO_BASE = "https://cdn.islamic.network/quran/audio/128/ar.alafasy";

let playingKey = null;   // "surah:ayat" yang sedang (atau terakhir) dimainkan
let queue = null;        // { unit: "surah:2" | "juz:1" | "mathurat:id", keys: [...] }; kekal semasa dijeda

function audioUrl(s, a) {
  return `${AUDIO_BASE}/${ayahOffsets[s - 1] + a}.mp3`;
}

function inProgress() {
  return Boolean(queue && playingKey && readerUnit) &&
    queue.unit === unitId(readerUnit) && queue.keys.includes(playingKey);
}

function updateSurahButton() {
  if (!readerUnit) return;
  const playing = Boolean(playingKey) && !player.paused;
  const active = inProgress();
  const what = readerUnit.kind === "juz" ? "juz" : "surah";

  if (active) {
    surahPlayBtn.textContent = playing ? "❚❚ Jeda" : `▶ Sambung (${posLabel(playingKey)})`;
  } else {
    surahPlayBtn.textContent = atStart() ? `▶ Main ${what}` : `▶ Main dari ${posLabel(readerPos)}`;
  }
  surahPlayBtn.classList.toggle("is-playing", active && playing);
  surahRestartBtn.hidden = !(active || !atStart());
}

function updatePlayButtons() {
  const playing = Boolean(playingKey) && !player.paused;
  document.querySelectorAll("[data-play]").forEach((b) => {
    const on = playing && b.dataset.play === playingKey;
    b.textContent = on ? "❚❚ Henti" : "▶ Dengar";
    b.classList.toggle("is-playing", on);
  });

  readerBody.querySelectorAll(".is-playing-ayah").forEach((el) => el.classList.remove("is-playing-ayah"));
  if (inProgress()) {
    const el = readerBody.querySelector(`[data-key="${playingKey}"]`);
    if (el) {
      el.classList.add("is-playing-ayah");
      if (playing) el.scrollIntoView({ block: "center", behavior: "smooth" });
    }
  }

  // Al-Ma'thurat: satu butang untuk seluruh petikan, dan tonjolkan ayat yang sedang dibaca
  const mUnit = queue && playingKey && queue.unit.startsWith("mathurat:") ? queue.unit.slice(9) : null;
  document.querySelectorAll("[data-m-play]").forEach((b) => {
    const mine = mUnit === b.dataset.mPlay && queue.keys.includes(playingKey);
    b.textContent = mine ? (playing ? "❚❚ Jeda" : "▶ Sambung") : "▶ Dengar";
    b.classList.toggle("is-playing", mine && playing);
  });
  document.querySelectorAll(".m-span.is-reading").forEach((el) => el.classList.remove("is-reading"));
  if (mUnit) {
    const el = document.querySelector(`[data-item="${CSS.escape(mUnit)}"] .m-span[data-mkey="${playingKey}"]`);
    if (el) el.classList.add("is-reading");
  }

  updateSurahButton();
}

async function playAyah(s, a) {
  try {
    await ensureSurahList();
  } catch {
    toast("Audio belum sedia. Cuba lagi sebentar lagi.");
    return;
  }
  playingKey = `${s}:${a}`;
  if (queue && readerUnit && queue.unit === unitId(readerUnit)) setReadPos(playingKey);
  player.src = audioUrl(s, a);
  player.play().catch(() => {
    toast("Audio tidak dapat dimainkan");
    queue = null;
    updatePlayButtons();
  });
}

function togglePlay(btn) {
  const key = btn.dataset.play;
  if (playingKey === key && !player.paused) {
    player.pause();
    return;
  }
  queue = null;
  const [s, a] = parseKey(key);
  playAyah(s, a);
}

function startQueue(fromKey) {
  if (!readerUnit) return;
  const key = readerUnit.keys.includes(fromKey) ? fromKey : readerUnit.keys[0];
  queue = { unit: unitId(readerUnit), keys: readerUnit.keys };
  const [s, a] = parseKey(key);
  playAyah(s, a);
}

function toggleQueue() {
  if (!readerUnit) return;
  if (inProgress()) {
    if (!player.paused) player.pause();                                     // jeda
    else player.play().catch(() => toast("Audio tidak dapat dimainkan"));    // sambung
    return;
  }
  startQueue(readerPos);   // main dari ayat terakhir dibaca (awal jika baru)
}

function restartQueue() {
  if (readerUnit) startQueue(readerUnit.keys[0]);
}

function stopAudio() {
  queue = null;
  player.pause();
}

player.addEventListener("play", updatePlayButtons);
player.addEventListener("pause", updatePlayButtons);
player.addEventListener("ended", () => {
  if (queue && playingKey) {
    const i = queue.keys.indexOf(playingKey);
    if (i >= 0 && i < queue.keys.length - 1) {
      const [s, a] = parseKey(queue.keys[i + 1]);
      playAyah(s, a);
      return;
    }
    // Surah/juz habis didengar: kedudukan kembali ke awal
    if (readerUnit && queue.unit === unitId(readerUnit)) {
      queue = null;
      readerPos = null;
      setReadPos(readerUnit.keys[0]);
    }
  }
  queue = null;
  updatePlayButtons();
});

/* ---------- Pembaca (surah, juz & hadis) ---------- */

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

function pageRange(ayahs) {
  const pages = ayahs.map((x) => x.page).filter(Boolean);
  if (!pages.length) return "";
  const lo = Math.min(...pages);
  const hi = Math.max(...pages);
  return lo === hi ? `Halaman ${lo}` : `Halaman ${lo}–${hi}`;
}

function ayahHtml(ayahs, kind, targetKey) {
  let prevS = null;
  let prevPage = null;
  return ayahs.map((x) => {
    const key = `${x.s}:${x.a}`;
    let head = "";
    if (x.page && x.page !== prevPage) {
      head += `<div class="r-page"><span>Halaman ${x.page}</span></div>`;
    }
    if (kind === "juz" && x.s !== prevS) {
      const m = surahMeta(x.s);
      head += `<div class="r-surah-head">${x.s}. ${esc(m.english_name)} <span class="ar-name" lang="ar">${esc(m.name_ar)}</span></div>`;
    }
    if (x.a === 1 && x.s !== 1 && x.s !== 9) head += BISMILLAH;
    prevS = x.s;
    prevPage = x.page;
    return head + `
      <div class="r-ayah${key === targetKey ? " is-target" : ""}" data-key="${key}">
        <div class="r-head">
          <span class="mini-ref">${esc(x.ref)}</span>
          <button type="button" class="tool" data-play="${key}">▶ Dengar</button>
        </div>
        ${x.text_ar ? `<p class="arabic" lang="ar" dir="rtl">${esc(x.text_ar)}</p>` : ""}
        ${x.text_ms ? `<p class="main t-ms">${esc(x.text_ms)}</p>` : ""}
        ${x.text_en ? `<p class="sub t-en">${esc(x.text_en)}</p>` : ""}
      </div>`;
  }).join("");
}

function navHtml(kind, n) {
  const max = kind === "juz" ? 30 : 114;
  const label = kind === "juz" ? "Juz" : "Surah";
  return `
    <nav class="r-nav">
      ${n > 1 ? `<button type="button" class="tool" data-open-${kind}="${n - 1}">← ${label} sebelum</button>` : "<span></span>"}
      ${n < max ? `<button type="button" class="tool" data-open-${kind}="${n + 1}">${label} seterusnya →</button>` : ""}
    </nav>`;
}

async function openUnit(kind, n, targetKey = null, highlight = false) {
  n = Number(n);
  if (queue && queue.unit !== `${kind}:${n}`) stopAudio();
  stopWatchReadPos();

  showReader("quran");
  applyReaderLang();
  readerTitle.textContent = kind === "juz" ? "Memuatkan juz..." : "Memuatkan surah...";
  readerMeta.textContent = "";
  readerBody.innerHTML = `<div class="card skeleton"><span></span><span></span><span class="short"></span></div>`;

  try {
    await ensureSurahList();
    const res = await fetch(kind === "juz" ? `${DATA_BASE}/juz/${n}.json` : `${DATA_BASE}/surah/${n}.json`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    const ayahs = kind === "juz" ? data.ayahs : data.ayahs.map((x) => ({ ...x, s: n, a: x.ayah }));
    const keys = ayahs.map((x) => `${x.s}:${x.a}`);
    const pages = Object.fromEntries(ayahs.map((x) => [`${x.s}:${x.a}`, x.page || null]));
    const range = pageRange(ayahs);

    if (kind === "surah") {
      const m = data.surah || surahMeta(n);
      readerUnit = { kind, n, name: m.english_name || `Surah ${n}`, keys, pages };
      readerTitle.innerHTML = `${n}. ${esc(m.english_name)} <span class="ar-name" lang="ar">${esc(m.name_ar)}</span>`;
      readerMeta.textContent = [m.translation, revelationLabel(m.revelation),
        m.ayah_count && `${m.ayah_count} ayat`, range].filter(Boolean).join(" · ");
    } else {
      const first = ayahs[0];
      const last = ayahs[ayahs.length - 1];
      readerUnit = { kind, n, name: `Juz ${n}`, keys, pages };
      readerTitle.textContent = `Juz ${n}`;
      readerMeta.textContent = [
        `${surahMeta(first.s).english_name} ${first.s}:${first.a} – ${surahMeta(last.s).english_name} ${last.s}:${last.a}`,
        `${keys.length} ayat`, range,
      ].filter(Boolean).join(" · ");
    }

    // Kedudukan awal: ayat sasaran dari carian, ayat yang dijeda, atau kedudukan tersimpan
    const saved = getLastRead();
    const pausedKey = inProgress() ? playingKey : null;
    const savedKey = saved && saved.kind === kind && Number(saved.n) === n ? saved.key : null;
    const start = (highlight && targetKey) || pausedKey || savedKey;
    readerPos = keys.includes(start) ? start : keys[0];

    readerBody.innerHTML = ayahHtml(ayahs, kind, highlight ? targetKey : null) + navHtml(kind, n);
    updatePlayButtons();
    saveReadPos();

    const target = readerPos !== keys[0] ? readerBody.querySelector(`[data-key="${readerPos}"]`) : null;
    if (target) target.scrollIntoView({ block: "center" });
    else readerBody.scrollTop = 0;

    // Mula mengikut skrol selepas skrol awal selesai
    requestAnimationFrame(() => requestAnimationFrame(watchReadPos));
  } catch (e) {
    console.error(e);
    readerUnit = null;
    readerTitle.textContent = kind === "juz" ? "Gagal memuatkan juz" : "Gagal memuatkan surah";
    readerBody.innerHTML = `<p class="muted">Sila semak sambungan internet dan cuba lagi.</p>`;
  }
}

function openNawawi(n) {
  n = Number(n);
  const h = nawawiList?.find((x) => x.number === n);
  if (!h) return;
  if (queue) stopAudio();
  stopWatchReadPos();
  readerUnit = null;

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
  if (queue) player.pause();   // jeda sahaja, supaya boleh disambung bila dibuka semula
  stopWatchReadPos();
  reader.hidden = true;
  document.body.classList.remove("no-scroll");
}

/* ---------- Perpustakaan (surah & juz) ---------- */

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

function renderJuz(filter = "") {
  if (!juzList) return;
  const f = normalize(filter);
  const items = juzList.filter((j) =>
    !f || String(j.number) === filter.trim() ||
    j.surahs.some((s) => normalize(surahMeta(s).english_name).includes(f)));
  surahGrid.innerHTML = items.length ? items.map((j, i) => `
    <button type="button" class="surah-card glass" data-open-juz="${j.number}" style="--i:${Math.min(i, 20)}">
      <span class="surah-no"><span>${j.number}</span></span>
      <span class="surah-names">
        <strong>Juz ${j.number}</strong>
        <span class="muted">${esc(j.start.name)} ${j.start.s}:${j.start.a} – ${esc(j.end.name)} ${j.end.s}:${j.end.a}</span>
      </span>
      <span class="surah-side">
        <span class="muted">${j.ayah_count} ayat</span>
      </span>
    </button>`).join("") : `<p class="muted">Tiada juz sepadan.</p>`;
}

function renderLibrary() {
  if (libMode === "juz") renderJuz(surahFilter.value);
  else renderSurahs(surahFilter.value);
}

function applyLibMode() {
  libToggle.querySelectorAll("[data-lib]").forEach((b) =>
    b.setAttribute("aria-pressed", String(b.dataset.lib === libMode)));
  surahFilter.placeholder = libMode === "juz"
    ? "Cari juz: nombor atau nama surah"
    : "Cari surah: nama atau nombor";
}

function renderResume() {
  const last = getLastRead();
  if (!last) {
    resumeEl.hidden = true;
    return;
  }
  let pos = "";
  if (last.key) {
    const [s, a] = parseKey(last.key);
    if (last.kind === "juz") pos = `, ${s}:${a}`;
    else if (a > 1) pos = `, ayat ${a}`;
  }
  const page = last.page ? ` · Halaman ${last.page}` : "";
  resumeEl.hidden = false;
  resumeEl.innerHTML =
    `<button type="button" class="resume-btn glass" data-resume>` +
    `Sambung bacaan: <strong>${esc(last.name)}${pos}</strong>${page} →</button>`;
}

async function loadLibrary() {
  renderResume();
  applyLibMode();
  const needSurahs = !surahList;
  const needJuz = libMode === "juz" && !juzList;
  if (!needSurahs && !needJuz) {
    renderLibrary();
    return;
  }
  surahGrid.innerHTML = `<div class="card glass skeleton"><span></span><span class="short"></span></div>`.repeat(6);
  try {
    await ensureSurahList();
    if (libMode === "juz" && !juzList) {
      const res = await fetch(`${DATA_BASE}/juz.json`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      juzList = await res.json();
    }
    renderLibrary();
  } catch (e) {
    console.error(e);
    surahGrid.innerHTML = `<p class="muted">Gagal memuatkan senarai. Sila semak sambungan internet dan muat semula halaman.</p>`;
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
    const res = await fetch(`${DATA_BASE}/nawawi.json`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    nawawiList = await res.json();
    renderArbain();
  } catch (e) {
    console.error(e);
    arbainGrid.innerHTML = `<p class="muted">Gagal memuatkan Hadis 40. Sila semak sambungan internet dan muat semula halaman.</p>`;
  }
}

/* ---------- Al-Ma'thurat ---------- */

const mathuratList = $("#mathurat-list");
const mathuratToggle = $("#mathurat-toggle");
const mathuratProgress = $("#mathurat-progress");
let mathurat = null;
let mathuratTime = new Date().getHours() < 13 ? "pagi" : "petang";

function todayStr() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

// Kiraan disimpan berasingan untuk setiap hari dan sesi (pagi/petang)
const countsKey = () => `mathurat:${todayStr()}:${mathuratTime}`;
const getCounts = () => storage.get(countsKey(), {});
const setCounts = (c) => storage.set(countsKey(), c);

const mathuratItems = () =>
  (mathurat?.items || []).filter((it) => !it.when || it.when === mathuratTime);

const itemText = (it, field) =>
  (mathuratTime === "petang" && it[`${field}_petang`]) || it[field] || "";

function countLabel(n, repeat) {
  if (n >= repeat) return "✓ Selesai";
  return repeat === 1 ? "Tanda selesai" : `Ketuk · ${n}/${repeat}`;
}

const toArabicDigits = (n) => String(n).replace(/\d/g, (d) => "٠١٢٣٤٥٦٧٨٩"[d]);

function mathuratCard(it, i, counts) {
  const n = Math.min(counts[it.id] || 0, it.repeat);
  const done = n >= it.repeat;
  let body;
  if (it.type === "quran") {
    const ar = it.ayahs.map((x) => {
      const a = x.key.split(":")[1];
      return `<span class="m-span" data-mkey="${x.key}">${esc(x.text_ar)} <span class="m-num">﴿${toArabicDigits(a)}﴾</span></span>`;
    }).join(" ");
    const ms = it.ayahs.filter((x) => x.text_ms)
      .map((x) => `(${x.key.split(":")[1]}) ${esc(x.text_ms)}`).join(" ");
    body = `
      <p class="arabic m-passage" lang="ar" dir="rtl">${ar}</p>
      ${ms ? `<details><summary>Terjemahan</summary><p class="sub">${ms}</p></details>` : ""}
      <div class="tools"><button type="button" class="tool" data-m-play="${esc(it.id)}">▶ Dengar</button></div>`;
  } else {
    const ar = itemText(it, "text_ar");
    const ms = itemText(it, "text_ms");
    body = (ar ? `<p class="arabic" lang="ar" dir="rtl">${esc(ar)}</p>` : "") +
      (ms ? `<details><summary>Maksud</summary><p class="sub">${esc(ms)}</p></details>` : "");
  }
  return `
    <article class="card glass m-card${done ? " is-done" : ""}" style="--i:${Math.min(i, 20)}" data-item="${esc(it.id)}">
      <div class="card-top">
        <span class="pill">${i + 1}. ${esc(it.title)}</span>
        ${it.repeat > 1 ? `<span class="badge">${it.repeat}×</span>` : ""}
      </div>
      ${body}
      ${it.note ? `<p class="note">${esc(it.note)}</p>` : ""}
      <button type="button" class="m-count" data-count="${esc(it.id)}"${done ? " disabled" : ""}>${countLabel(n, it.repeat)}</button>
    </article>`;
}

function updateMathuratProgress() {
  const items = mathuratItems();
  const counts = getCounts();
  const done = items.filter((it) => (counts[it.id] || 0) >= it.repeat).length;
  const pct = items.length ? (done / items.length) * 100 : 0;
  mathuratProgress.innerHTML = `
    <div class="m-bar"><span style="width:${pct}%"></span></div>
    <span class="muted">${done}/${items.length} selesai</span>
    <button type="button" class="tool" data-m-reset>↺ Set semula</button>`;
}

function renderMathurat() {
  if (!mathurat) return;
  mathuratToggle.querySelectorAll("[data-time]").forEach((b) =>
    b.setAttribute("aria-pressed", String(b.dataset.time === mathuratTime)));
  const items = mathuratItems();
  const counts = getCounts();
  mathuratList.innerHTML = items.length
    ? items.map((it, i) => mathuratCard(it, i, counts)).join("")
    : `<p class="muted">Tiada item untuk sesi ini.</p>`;
  updateMathuratProgress();
  updatePlayButtons();
}

function tapCount(id) {
  const it = mathuratItems().find((x) => x.id === id);
  if (!it) return;
  const counts = getCounts();
  const n = Math.min((counts[id] || 0) + 1, it.repeat);
  counts[id] = n;
  setCounts(counts);
  navigator.vibrate?.(10);

  const card = mathuratList.querySelector(`[data-item="${CSS.escape(id)}"]`);
  const btn = card.querySelector("[data-count]");
  btn.textContent = countLabel(n, it.repeat);
  if (n >= it.repeat) {
    card.classList.add("is-done");
    btn.disabled = true;
    const next = card.nextElementSibling;
    if (next) next.scrollIntoView({ block: "center", behavior: "smooth" });
  }
  updateMathuratProgress();
}

function toggleMathuratPlay(id) {
  const it = mathuratItems().find((x) => x.id === id);
  if (!it || it.type !== "quran") return;
  const unit = `mathurat:${id}`;
  if (queue && queue.unit === unit && queue.keys.includes(playingKey)) {
    if (!player.paused) player.pause();                                     // jeda
    else player.play().catch(() => toast("Audio tidak dapat dimainkan"));    // sambung
    return;
  }
  const keys = it.ayahs.map((x) => x.key);
  queue = { unit, keys };            // dimainkan berturut-turut oleh pengendali "ended"
  const [s, a] = parseKey(keys[0]);
  playAyah(s, a);
}

async function loadMathurat() {
  if (mathurat) return renderMathurat();
  mathuratList.innerHTML = `<div class="card glass skeleton"><span></span><span></span><span class="short"></span></div>`.repeat(3);
  try {
    await ensureSurahList();   // untuk audio
    const res = await fetch(`${DATA_BASE}/mathurat.json`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    mathurat = await res.json();
    if (mathurat.source) {
      $("#mathurat-source").textContent =
        `Zikir dan doa pagi dan petang himpunan Imam Hasan al-Banna. Rujukan teks: ${mathurat.source}.`;
    }
    renderMathurat();
  } catch (e) {
    console.error(e);
    mathuratList.innerHTML = `<p class="muted">Gagal memuatkan Al-Ma'thurat. Sila semak sambungan internet dan muat semula halaman.</p>`;
  }
}

viewMathurat.addEventListener("click", (e) => {
  const t = e.target;

  const timeBtn = t.closest("[data-time]");
  if (timeBtn) {
    mathuratTime = timeBtn.dataset.time;
    return renderMathurat();
  }

  if (t.closest("[data-m-reset]")) {
    setCounts({});
    return renderMathurat();
  }

  const countBtn = t.closest("[data-count]");
  if (countBtn) return tapCount(countBtn.dataset.count);

  const mPlay = t.closest("[data-m-play]");
  if (mPlay) return toggleMathuratPlay(mPlay.dataset.mPlay);

  const playBtn = t.closest("[data-play]");
  if (playBtn) togglePlay(playBtn);
});

/* ---------- Navigasi ---------- */

function currentView() {
  if (location.hash === "#quran") return "library";
  if (location.hash === "#arbain") return "arbain";
  if (location.hash === "#mathurat") return "mathurat";
  return "search";
}

function route() {
  const view = currentView();
  viewSearch.hidden = view !== "search";
  viewLibrary.hidden = view !== "library";
  viewArbain.hidden = view !== "arbain";
  viewMathurat.hidden = view !== "mathurat";
  if (view === "library") loadLibrary();
  if (view === "arbain") loadArbain();
  if (view === "mathurat") loadMathurat();
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

  if (t.closest("[data-more]")) return search(lastQuery, MORE_K);

  const copyBtn = t.closest("[data-copy]");
  if (copyBtn) return copyText(copyBtn.dataset.copy);

  const playBtn = t.closest("[data-play]");
  if (playBtn) return togglePlay(playBtn);

  const readBtn = t.closest("[data-read]");
  if (readBtn) {
    const [s, a] = parseKey(readBtn.dataset.read);
    return openUnit("surah", s, `${s}:${a}`, true);
  }

  const simBtn = t.closest("[data-similar]");
  if (simBtn) return toggleSimilar(simBtn);

  const voteBtn = t.closest("[data-vote]");
  if (voteBtn) return vote(voteBtn);
});

viewLibrary.addEventListener("click", (e) => {
  const t = e.target;

  const libBtn = t.closest("[data-lib]");
  if (libBtn) {
    if (libBtn.dataset.lib === libMode) return;
    libMode = libBtn.dataset.lib;
    storage.set("libMode", libMode);
    surahFilter.value = "";
    return loadLibrary();
  }

  if (t.closest("[data-resume]")) {
    const last = getLastRead();
    if (last) openUnit(last.kind, last.n);
    return;
  }

  const surahBtn = t.closest("[data-open-surah]");
  if (surahBtn) return openUnit("surah", surahBtn.dataset.openSurah);

  const juzBtn = t.closest("[data-open-juz]");
  if (juzBtn) return openUnit("juz", juzBtn.dataset.openJuz);
});

viewArbain.addEventListener("click", (e) => {
  const btn = e.target.closest("[data-open-nawawi]");
  if (btn) openNawawi(btn.dataset.openNawawi);
});

surahFilter.addEventListener("input", renderLibrary);

surahPlayBtn.addEventListener("click", toggleQueue);
surahRestartBtn.addEventListener("click", restartQueue);

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
  if (surahNav) return openUnit("surah", surahNav.dataset.openSurah);

  const juzNav = t.closest("[data-open-juz]");
  if (juzNav) return openUnit("juz", juzNav.dataset.openJuz);

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
    if (view === "arbain" || view === "mathurat") return;
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
ensureSurahList().catch(() => {});            // sediakan audio & perpustakaan (fail statik)
fetch(`${API_BASE}/health`).catch(() => {});  // "kejutkan" pelayan carian lebih awal
const initial = new URLSearchParams(window.location.search).get("q");
if (initial && currentView() === "search") run(initial);