# Nota Projek: ayat. (Carian Al-Quran & Hadis)

Nota kerja yang merekodkan keputusan, eksperimen, dapatan dan batasan projek. Ditulis semula
berdasarkan log kerja 29 Sep – 1 Okt 2026.

---

## 1. Ringkasan

Carian semantik untuk ayat Al-Quran dan hadis sahih (Sahih al-Bukhari & Sahih Muslim)
menggunakan soalan harian dalam Bahasa Melayu atau Inggeris.

- **Carian:** hybrid BM25 + dense (multilingual-e5-base), digabung dengan Reciprocal Rank Fusion (RRF).
- **Quran dan hadis dicari secara berasingan** dan dipaparkan dalam dua bahagian.
- **Laman web:** https://ayat-f43d2.web.app (Firebase Hosting)
- **API:** FastAPI di Google Cloud Run (asia-southeast1)

### Prinsip reka bentuk utama
1. **Terjemahan mesin hanya untuk carian, tidak pernah dipaparkan.** Pengguna sentiasa melihat teks
   Arab dan terjemahan manusia yang sahih.
2. **Setiap perubahan diukur** terhadap test set yang sama, dengan peraturan keputusan ditetapkan
   sebelum melihat hasil (sebarang pengecualian direkodkan).
3. **Bukan alat fatwa.** Soalan berbentuk hukum dikesan dan pengguna dirujuk ke sumber rasmi.

---

## 2. Seni bina

```
Pengguna → Firebase Hosting (web/) → Cloud Run (FastAPI) → repo dataset PERIBADI Hugging Face (index)
                  ↓
            Firestore (search_logs, tanpa nama)
```

| Komponen | Butiran |
|---|---|
| Data mentah | Quran: alquran.cloud (Tanzil; BM Basmeih, EN Sahih International). Hadis: fawazahmed0/hadith-api |
| Pipeline | `download.py` → `clean.py` → `units.py` → `build_index.py` (Colab GPU) |
| Unit carian | Quran: 1 unit per ayat per bahasa. Hadis: chunk 150 perkataan (bertindih 30) |
| Dense | `intfloat/multilingual-e5-base`, varian `ctx` (ayat pendek diberi konteks) |
| Terjemahan hadis (index sahaja) | NLLB-200 1.3B, beam 4, `no_repeat_ngram_size=3`, ditapis |
| Stemming | Sastrawi, Quran sahaja (v7) |
| Deploy API | Docker di Cloud Run: 4 GiB, 2 vCPU, min 0 / max 2 instans |
| Rahsia | Token HF (read) dalam Secret Manager; tiada token dalam kod |

---

## 3. Data (Minggu 1)

**Corpus akhir:** 21,176 dokumen (Quran 6,236; Bukhari 7,580; Muslim 7,360).
9 baris Bukhari dan 203 baris Muslim tanpa teks dibuang.

### Dapatan pembersihan data
- **Kitab 0 membawa maksud berbeza dalam dua dataset.** Bukhari: 306 hadis tidak dipetakan
  (300 diisi dari jiran dalam kitab yang sama, 6 di sempadan kitab dibiarkan "Tidak diklasifikasikan").
  Muslim: kitab 0 ialah **Introduction** yang sah (tidak diubah).
- **Bug yang disembunyikan oleh metrik ringkasan:** jadual nilai kosong tunjuk 0%, tetapi
  *semua 7,580* hadis Bukhari tersalah label "Tidak diklasifikasikan" (kunci `"56.0"` vs `"56"`
  selepas pandas menukar Int64+NA kepada float). Hanya spot-check manual yang mendedahkannya.
- **Basmalah** tercantum pada ayat 1 bagi 112 surah. Padanan `startswith` biasa gagal kerana teks
  yang kelihatan sama berbeza pada peringkat Unicode; diselesaikan dengan membandingkan rangka
  huruf (tanpa harakat, alif diseragamkan).
- **Rujukan silang hadis** ("As above", "See previous hadith", nota rantaian perawi Muslim):
  734 entri (corak + bawah 40 perkataan) dikecualikan daripada carian. Peraturan panjang
  menyelamatkan ~150 hadis yang ada kandungan sebenar.
- **Ayat muqatta'ah** (الم, يس, حم, ...): 20 ayat dikecualikan daripada dense sahaja; ia muncul
  untuk soalan yang langsung tidak berkaitan.

---

## 4. Evaluation

### Test set (akhir: 248 soalan)
| Jenis | Bilangan | Nota |
|---|---|---|
| Sintetik Quran | 128 | Satu jawapan betul per soalan (known-item) |
| Sintetik hadis | 45 | Soalan BM untuk teks hadis EN (menguji merentas bahasa) |
| Manual | 35 | Jawapan disemak dengan `show_refs.py` |
| Negatif | 28 | Jelas luar bidang |
| Negatif sukar | 12 | Berbau agama tetapi tidak boleh dijawab teks (contoh: "waktu solat Kuching hari ini") |

27 calon sintetik dibuang (ayat generik berulang seperti 55:32, serpihan, hadis tanpa isi).
Metrik: recall@5, recall@10, MRR@10. Soalan dinilai dalam bahagian di mana jawapannya berada.

### Batasan test set (penting)
- Soalan sintetik ditulis berdasarkan terjemahan Basmeih → **berat sebelah memihak BM25**.
- Soalan known-item cuma ada satu jawapan betul → recall sebenar mungkin lebih tinggi.
- Soalan manual kecil (~18–20 per bahagian): setiap soalan ≈ 5 mata peratus.
- Tiada pengesahan oleh seseorang yang berilmu dalam bidang agama.
- 100 soalan manual tambahan telah dijana (`manual_queries_batch2.csv`) tetapi **belum** disemak
  atau digunakan.

---

## 5. Sejarah versi

Metrik hybrid kecuali dinyatakan. "SEMUA" = semua soalan positif dalam bahagian tersebut.

| Versi | Perubahan | Quran R@10 | Quran MRR | Hadis R@10 | Hadis MRR |
|---|---|---|---|---|---|
| v1 | BM25 sahaja | 0.766 (sint.) | 0.570 | 0.133 | 0.061 |
| v2 | Hybrid RRF (k=60, 1:1) | 0.852 (sint.) | 0.621 | 0.244 | 0.074 |
| – | MT hadis v1, index bercampur | 0.820 (sint.) | 0.608 | 0.467 | 0.227 |
| v3 | Carian berasingan Quran/hadis | 0.812 (sint.) | 0.590 | 0.556 | 0.282 |
| v3b | BM25 Quran k1=1.2, b=0.3 | 0.859 (sint.) | 0.643 | 0.556 | 0.282 |
| v4 | Konteks untuk ayat pendek (dense) | 0.859 (sint.) | 0.654 | – | – |
| v4 (247 soalan) | + manual & negatif tambahan | 0.832 | 0.634 | 0.611 | 0.363 |
| v4f | Tapis terjemahan meragukan | 0.832 | 0.634 | 0.578 | 0.366 |
| v5 | MT hadis v2 (NLLB 1.3B) + tapis | 0.832 | 0.634 | 0.628 | 0.378 |
| v6 | Kecuali xref/muqatta'ah, stopword (Quran `intent`, hadis `full`) | 0.832 | 0.628 | 0.667 | 0.374 |
| **v7** | **Stemming BM untuk Quran** | **0.881** | **0.633** | **0.672** | **0.371** |

(v6 dan v7 diukur pada test set 247/248 soalan; nombor sintetik awal pada test set lebih kecil.)

Soalan manual Quran (recall@10): 0.478 (v1 BM25) → 0.566 (v3b) → 0.644 (v4) → **0.766 (v7)**.
Soalan manual hadis (recall@10): 0.778 (v4) → 0.844 (v5) → **0.875 (v7)**.

### v7c (1 Okt 2026)
- **Kata dasar ejaan Malaysia** ditambah ke kamus Sastrawi (kahwin, taubat, derhaka, ugama, rosak, ...).
  Sastrawi dibina untuk Bahasa Indonesia ("kawin"), jadi "berkahwin" tidak di-stem sebelum ini.
  Metrik tidak berubah (test set tiada soalan berkaitan), tetapi carian "kahwin" untuk Quran
  berubah dari tiada padanan BM25 kepada 5/5 ayat perkahwinan.
- **Pepijat RRF:** dokumen dengan skor BM25 0 masih mendapat skor RRF bila BM25 jumpa < 100 padanan,
  menyebabkan hasil rawak (contoh: Bukhari 18–21 untuk "kahwin"). Dibetulkan: hanya skor > 0 dikira.
  Metrik tidak berubah kerana semua soalan test set cukup panjang untuk mendapat ≥ 100 padanan.
- **Stemming hadis diuji semula** dengan kamus baharu: recall@10 −0.030 → ditolak semula.

**Pengajaran:** tiga perubahan berturut-turut tidak menggerakkan metrik langsung, walaupun dua daripadanya
membetulkan masalah sebenar yang jelas kelihatan. Test set tiada soalan satu perkataan atau perkataan
berimbuhan khusus Malaysia. Kegagalan yang dijumpai dalam penggunaan sebenar mesti ditambah sebagai
kes ujian.

**Isu diketahui:** hadis dengan terjemahan Inggeris "See hadith" atau kosong (contoh: Bukhari 4910,
Muslim 3452) boleh muncul secara rawak dalam hasil kerana kandungannya (teks Arab) tidak diindex.
Dibiarkan buat masa ini; kerja masa depan: index teks Arab untuk hadis tanpa terjemahan.

---

## 6. Dapatan utama

### 6.1 Masalah hadis ialah masalah bahasa, sepenuhnya
Hadis dengan soalan EN: BM25 recall@10 1.000 (5 soalan). Dengan soalan BM: 0.025.
Sistem boleh mencari hadis; yang gagal ialah jambatan BM ↔ EN.

### 6.2 Terjemahan mesin membantu BM25, bukan dense
Selepas terjemahan: BM25 hadis 0.133 → 0.467, dense tidak berubah (0.222). Model e5 multilingual
sudah merentas bahasa secara semantik. Maka unit terjemahan hanya dimasukkan ke BM25.

### 6.3 Carian bercampur menyebabkan persaingan
Unit hadis BM mula menolak ayat Quran keluar dari 10 teratas, dan IDF perkataan BM berubah.
Penyelesaian: dua bahagian berasingan, masing-masing dengan index sendiri.

### 6.4 Regresi sistematik, bukan rawak
v2 → v3 Quran: **0 soalan lebih baik, 5 lebih teruk**. Punca: statistik BM25 (IDF, panjang purata)
berubah bila index Quran berdiri sendiri. Diselesaikan dengan menala `b`.

### 6.5 Komponen dalam hybrid tak perlu terbaik bersendirian
BM25 bersendirian terbaik dengan `b` tinggi (0.75–0.9), tetapi dalam hybrid, `b` rendah (0.0–0.3)
jauh lebih baik: BM25 dengan `b` rendah mengimbangi kecenderungan dense memilih ayat pendek.
Keputusan `b` membentuk dataran (0.0–0.3 hampir sama), petanda parameter yang stabil.

### 6.6 Konteks bersasar untuk ayat pendek
Konteks (±1 ayat) hanya untuk ayat < 12 perkataan (2,387 unit). Dense manual Quran 0.136 → 0.318,
dan soalan sintetik **tidak** jatuh (kebimbangan asal: ayat jiran bersaing).

### 6.7 Metrik bagus tidak menjamin sistem selamat
Terjemahan NLLB 600M: **14.94%** unit menambah nama nabi yang tiada dalam teks asal
(contoh: Heraclius → "Nabi Sulaiman"; "Nabi Sulaiman, Nabi Sulaiman, ..." berulang; gaya
"Dan (ingatlah)" dari terjemahan Quran menyerap masuk). Soalan dalam test set jarang menyebut
nama nabi, jadi kerosakan ini hampir tidak kelihatan dalam recall.

| Masalah | MT v1 (600M, greedy) | MT v2 (1.3B, beam 4, no-repeat 3) |
|---|---|---|
| Nama nabi palsu | 2,741 | 1,628 |
| Gelung berulang | 29 | 0 |
| Panjang luar biasa | 220 | 372 |
| Unit lulus penapis | 15,372 | 16,349 |

Terjemahan dibuat ayat demi ayat (64,089 sentence → 55,931 unik → 28 shard), checkpoint dalam
Google Drive. Penapis hanya menangkap kesilapan jelas; kesilapan halus (contoh: kata nafi tercicir)
tidak dikesan, sebab itu terjemahan mesin tidak pernah dipaparkan.

### 6.8 Kecenderungan test set terbawa ke parameter sistem
Threshold keyakinan BM25 yang dipilih dari soalan sintetik (Quran 12, hadis 15) menandakan
soalan sebenar yang sempurna (contoh: "hukum riba dalam islam", hasil 2:275 di tempat pertama)
sebagai "kurang berkaitan". Soalan sintetik berkongsi perkataan dengan terjemahan Basmeih, jadi
skornya lebih tinggi daripada soalan pengguna sebenar. Dikalibrasi semula dengan soalan manual:
**Quran 10, hadis 11**.

### 6.9 Stemming membantu satu korpus, menjejaskan yang lain
| | Quran | Hadis |
|---|---|---|
| R@10 | 0.828 → **0.881** | 0.672 → 0.642 ✗ |
| MRR | 0.627 → 0.633 | 0.371 → 0.403 |
| Manual R@10 | 0.624 → **0.766** | 0.875 → 0.823 |

Hipotesis (belum dibuktikan): teks BM hadis ialah terjemahan mesin yang kurang konsisten, dan
stemming mencantumkan makna berbeza (contoh: "withhold water" dan "menahan marah" → `tahan`).

---

## 7. Log keputusan

| Keputusan | Peraturan | Hasil | Jenis |
|---|---|---|---|
| Pemberat hybrid | Pilih pada sintetik, sahkan pada manual | Kekal 1:1; tala semula selepas isu bahasa | Sebelum |
| BM25 Quran | Tukar dari b=0.3 hanya jika jelas lebih baik pada tune *dan* check | Kekal k1=1.2, b=0.3 | Sebelum |
| Penapis MT (v4f) | Terima jika hadis R@10 jatuh < 0.03 | Jatuh 0.033 → terjemah semula (v5) | Sebelum |
| Stopword Quran | Had 0.01 berbanding v5 | `full` ditolak (MRR −0.024); `none` & `intent` seri | Sebelum |
| Pemecah seri stopword | *Tiada peraturan awal* | `intent` dipilih kerana membetulkan soalan riba (33:6, 60:10 hilang) | **Selepas** |
| Threshold | Nilai tertinggi yang kekalkan ≥95% positif manual | Quran 10, hadis 11 | Sebelum |
| Stemming hadis | R@10 & MRR tak jatuh > 0.01 | R@10 −0.030 → **ditolak** | Sebelum |
| Stemming Quran | Sama + MRR manual "tak jatuh" | MRR manual −0.007 (< 1 soalan) → **diterima dengan toleransi 0.01** | **Selepas** (peraturan asal tiada toleransi) |

---

## 8. Ujian kualitatif melalui API (v6 → v7)

| Soalan | Dapatan |
|---|---|
| hukum riba dalam islam | Notis fatwa ✓. Selepas stopword `intent`: 5/5 ayat riba (2:275, 2:278, 2:276, 3:130, 4:161), 5/5 hadis riba |
| sabar ketika ditimpa musibah | 2:45, 16:126, Bukhari 1302 relevan. **2:155–2:157 tiada** (pengguna tulis "musibah", Basmeih tulis "kesusahan") |
| resepi nasi lemak | Quran `confident: false` ✓. Hadis `confident: true` (padan "lemak" / susu berlemak) ✗: kos threshold hadis yang longgar |
| menahan marah | Tanpa stemming: 3:134 tak padan ("kemarahannya" ≠ "marah"). Dengan stemming: 3:134 naik ke tempat ke-2 BM25. Bukhari 6114 masih tiada ("mengawal" vs "menahan") |

---

## 9. Deployment

- **Hugging Face Spaces ditolak:** Docker/Gradio Spaces kini memerlukan langganan PRO (ralat 402).
  Hanya Static Spaces percuma.
- **Cloud Run:** kuota percuma kekal untuk pengkomputeran; akaun billing wajib. Kos yang dijangka
  hanya storan imej Docker (~2–3 GB, melebihi 0.5 GB percuma). Kredit percubaan: RM1,208, tamat
  ~11 Dis 2026. **Semak bil sebelum tarikh ini.**
- **Bug Docker:** `WORKDIR` mencipta folder sebagai root → API tak boleh menulis index yang dimuat
  turun. Diselesaikan dengan `RUN mkdir -p $HOME/app` sebagai pengguna biasa.
- **Permulaan sejuk:** carian pertama ~1 minit (muat turun index + muatkan model). Laman web papar
  mesej dan "mengejutkan" pelayan semasa dibuka.
- **Firestore:** `search_logs` hanya boleh ditambah (create) dengan bentuk tetap; tiada baca/ubah
  dari pelayar.
- **CORS:** dihadkan kepada domain Firebase (semak semula selepas sebarang perubahan).
- **Git:** `data/index/` pernah ter-commit (`.gitignore` asal tidak meliputinya). Dikeluarkan, tetapi
  masih dalam sejarah Git → bersihkan dengan `git filter-repo` sebelum dipromosikan.

---

## 10. Batasan diketahui

- Jurang **sinonim** (musibah/kesusahan, menahan/mengawal) masih wujud; stemming hanya menyelesaikan imbuhan.
- Dense lemah untuk soalan manual Quran pendek (recall@10 ~0.30).
- Threshold Quran v7 hanya menolak 64% soalan negatif (93% dalam v6); hadis 46%.
- Pengesan niat berasaskan peraturan yang ditulis selepas melihat soalan negatif sukar → liputan mungkin terlebih anggar.
- Hadis dipaparkan dalam EN sahaja; gred ialah lalai koleksi, bukan per hadis.
- Hanya Bukhari dan Muslim; nombor hadis Muslim dalam dataset tidak sepadan dengan penomboran lazim.
- Terma lesen terjemahan Basmeih dan sumber hadis belum disemak secara rasmi.
- Tiada unit test atau CI/CD; deploy manual dari Cloud Shell.

---

## 11. Kerja masa depan

| Keutamaan | Kerja |
|---|---|
| Segera | README (demo, screenshot, seni bina, jadual versi) |
| Segera | Bersihkan sejarah Git; tetapkan versi pakej |
| Sederhana | Dashboard analytics dari log Firestore (soalan popular, kadar amaran, notis fatwa) |
| Sederhana | Butang 👍/👎 untuk kumpul label relevan daripada pengguna sebenar |
| Sederhana | Pengembangan sinonim soalan dan/atau reranker (cross-encoder) di atas 30 hasil teratas |
| Sederhana | Uji model embedding lebih kuat (contoh: bge-m3) |
| Sederhana | ONNX Runtime → imej lebih kecil, permulaan lebih pantas, kos hampir sifar |
| Sederhana | Unit test + GitHub Actions untuk deploy automatik |
| Sederhana | Semak & gunakan 100 soalan manual tambahan; kalibrasi semula threshold |
| Jangka panjang | Pengesahan soalan manual oleh seseorang berlatar belakang pengajian Islam |
| Jangka panjang | Koleksi hadis lain dengan gred per hadis; terjemahan BM hadis berlesen; pautan tafsir |

---

## 12. Pengajaran (untuk write-up / interview)

1. Spot-check manual menangkap bug yang metrik ringkasan sembunyikan (7,580 label salah, 0% kosong).
2. Masalah yang punca tunggalnya jelas (bahasa) lebih mudah diselesaikan daripada yang kabur.
3. Regresi "0 lebih baik, 5 lebih teruk" ialah sistematik; cari punca, jangan anggap hingar.
4. Dalam sistem gabungan, komponen patut melengkapi, bukan menjadi terbaik bersendirian.
5. Metrik yang baik tidak menjamin keselamatan: audit kualiti berasingan wajib dalam domain sensitif.
6. Cara test set dibina boleh terbawa terus ke parameter sistem; uji dengan soalan gaya pengguna.
7. Tetapkan peraturan keputusan sebelum melihat data, dan rekodkan dengan jujur bila menyimpang.
8. Teknik yang sama boleh membantu satu korpus dan menjejaskan korpus lain (stemming).
