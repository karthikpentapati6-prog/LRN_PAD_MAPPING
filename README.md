# 📚 Curriculum Mapping Automation System

> **LearningPad** — Automatically map school curriculum topics to the CBSE content library using AI-powered semantic search on audio scripts.

---

## 🏗️ Architecture

```
frontend.py  (Streamlit UI — 5-step wizard)
      │
      │  HTTP / REST
      ▼
backend.py   (FastAPI)
      │
      ├── Board / Class / Subject Filters ──► Parsed from MongoDB Atlas URL field
      ├── MongoDB Atlas                    ──► Collections: Models, Activities
      ├── NumPy Vector Search              ──► Cosine similarity (no FAISS needed)
      └── Google Gemini (Cloud)            ──► gemini-embedding-001 (embeddings)
                                               gemini-2.5-flash    (Vision OCR)

transcribe_audios.py  (Standalone CLI tool)
      │
      ├── MongoDB Atlas  ──► Reads Models / Activities / Topics / Lessons
      ├── Cloudflare R2  ──► Downloads audio files (S3-compatible)
      └── Faster-Whisper ──► CPU transcription → writes audio_script back to Atlas
```

---

## 📁 Project Structure

```
LRNPAD_MAPPING/
├── backend.py           ← FastAPI backend (single file)
├── frontend.py          ← Streamlit frontend (single file)
├── transcribe_audios.py ← CLI tool: audio transcription pipeline (Whisper + R2 + Atlas)
├── requirements.txt     ← All Python dependencies
├── .env                 ← MongoDB Atlas URI, Gemini API key, R2 credentials
├── .cache/              ← Auto-generated NumPy embedding cache
│   ├── embeddings.npy
│   └── metadata.pkl
├── .gitignore
└── README.md
```

---

## ⚙️ Setup & Installation

### 1. Create & activate virtual environment

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

### 2. Install dependencies

```powershell
pip install -r requirements.txt
```

### 3. Configure environment

Edit `.env`:

```env
# ─── Local MongoDB (fallback) ───────────────────────────────────────────────
MONGO_URI=mongodb://localhost:27017/
DB_NAME=LRN_LESSONS
COLLECTION_NAME=LESSONS

# ─── Embedding Model ────────────────────────────────────────────────────────
EMBEDDING_MODEL=models/gemini-embedding-001
GEMINI_API_KEY=your_gemini_api_key_here

# ─── CORS ───────────────────────────────────────────────────────────────────
ALLOWED_ORIGINS=*

# ─── MongoDB Atlas (Primary source) ─────────────────────────────────────────
ATLAS_MONGO_URI=mongodb+srv://<user>:<pass>@<cluster>.mongodb.net/?retryWrites=true&w=majority
ATLAS_DB_NAME=lp_dev_database
ATLAS_COLLECTION_NAME=Models

# ─── Cloudflare R2 (for transcription tool) ─────────────────────────────────
R2_ACCESS_KEY=your_r2_access_key
R2_SECRET_KEY=your_r2_secret_key
R2_ENDPOINT_URL=https://<account_id>.r2.cloudflarestorage.com
R2_BUCKET_NAME=lp-dev-content-cf
```

> 💡 `ATLAS_MONGO_URI` takes priority over `MONGO_URI` at runtime. The backend checks for Atlas vars first.

---

## 🗄️ MongoDB Atlas Schema

The backend reads from two collections: **Models** and **Activities**.

### Required Document Structure

```json
{
  "url": "CBSE/Class6/Science/FoodWhereDoesItComeFrom/FoodWhereDoesItComeFrom.SomeTopic",
  "model_name": "Vitamins and Their Sources",
  "meta_data": {
    "audio": [
      {
        "audio_id": 1,
        "audio_script": "In this lesson we explore vitamins...",
        "path": "CBSE/Class6/Science/..."
      }
    ]
  }
}
```

### How Metadata is Parsed (from `url` field)

The backend **auto-parses** the `url` field at index-build time — no manual field mapping needed:

| `url` segment | Parsed into | Example |
|---|---|---|
| `parts[0]` | `meta_board` | `CBSE` |
| `parts[1]` | `meta_class` | `Class6` |
| `parts[2]` | `meta_subject` | `Science` |
| `parts[3]` | `meta_lesson` | `FoodWhereDoesItComeFrom` |
| `parts[5]` (after `.`) | `meta_topic` | `Vitamins and Their Sources` |

> These parsed fields drive all dropdowns (Board → Class → Subject) and export filters.

---

## 🚀 Running the Application

Open **two terminals** side-by-side.

### Terminal 1 — Start the Backend

```powershell
cd c:\FLIXITY_WORKS\LRNPAD_MAPPING
.\venv\Scripts\Activate.ps1
uvicorn backend:app --reload --host 0.0.0.0 --port 8000
```

Backend will be live at: **http://localhost:8000**  
Interactive API docs: **http://localhost:8000/docs**

### Terminal 2 — Start the Frontend

```powershell
cd c:\FLIXITY_WORKS\LRNPAD_MAPPING
.\venv\Scripts\Activate.ps1
streamlit run frontend.py
```

Streamlit UI will open at: **http://localhost:8501**

---

## 🔄 5-Step Workflow

### Step 1 — 📤 Upload Curriculum

- **Select Board** from the dropdown — loaded live from MongoDB Atlas
- **Select Class (Grade)** — automatically filtered by the chosen Board
- **Select Subject** — automatically filtered by Board + Class
- File uploader is **disabled** until all three filters are selected
- Upload school curriculum file (PDF / Excel / CSV / Word)
- **Scanned / Screenshot PDFs**: Automatically detected; pages rendered via **PyMuPDF** and sent to **Gemini 2.5 Flash Vision OCR** for topic extraction

### Step 2 — 🔍 Review Topics

- View all extracted topics in a table
- Banner shows the chosen Board, Class & Subject
- Adjust the **top-K slider** (1–10 matches per topic)

### Step 3 — 🤖 AI Mapping

- Google Gemini encodes each topic into a **768-dimension** embedding (cloud-based)
- NumPy cosine similarity search runs against the pre-built embedding index
- Ranking and confidence scoring applied

### Step 4 — 📊 Results

- Summary metrics: High / Medium / Low confidence counts + average similarity
- Tabbed view filtered by confidence level (shows Board, Grade, Subject, Lesson, Topic)
- Expandable audio script snippets
- Drilldown section shows all top-K alternatives per topic

### Step 5 — ⬇️ Export

- Board, Class & Subject filters **pre-filled** from Step 1 (editable here too)
- Only rows matching the selected Board, Class & Subject are exported
- Filtered preview table shown before any download
- Filenames include Board, Class, and Subject: `mapping_CBSE_Class6_Science.xlsx`
- Three download formats: **Excel**, **CSV** (via API), **Quick CSV** (local)

---

## 🎙️ Transcription Pipeline (`transcribe_audios.py`)

A standalone CLI tool that fetches audio from Cloudflare R2, transcribes it using Faster-Whisper (CPU), and writes the transcript back to MongoDB Atlas.

### Usage

```powershell
# Transcribe a specific topic
python transcribe_audios.py --topic_id <id>

# Transcribe all topics under a lesson
python transcribe_audios.py --lesson_id <id>

# Transcribe all topics under a subject
python transcribe_audios.py --subject_id <id>

# Transcribe a specific activity
python transcribe_audios.py --activity_id <id>

# Full sweep (no args)
python transcribe_audios.py
```

### What it does

1. Resolves target document IDs (Topics / Activities) from the given scope
2. Fetches audio files from **Cloudflare R2** (S3-compatible)
3. Transcribes using **Faster-Whisper** (CPU, `large-v3` model)
4. Writes `meta_data.audio.0.audio_script` back to **MongoDB Atlas**
5. Saves a local JSON backup to `transcriptions.json`

> Parallelism is controlled by `MAX_WORKERS = 4` (configurable in the script).

---

## 🌐 API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET`  | `/health` | System health (MongoDB, index, model status) |
| `GET`  | `/library/stats` | Library stats: boards, grades, subjects, total items |
| `GET`  | `/library/boards` | All boards in the index |
| `GET`  | `/library/grades?board=X` | Classes filtered by board |
| `GET`  | `/library/subjects?grade=X&board=Y` | Subjects filtered by board + class |
| `POST` | `/upload-curriculum` | Parse file, extract topics (with Vision OCR fallback) |
| `POST` | `/run-mapping` | Semantic search for each uploaded topic |
| `POST` | `/export?fmt=xlsx` | Download results as Excel |
| `POST` | `/export?fmt=csv` | Download results as CSV |
| `POST` | `/rebuild-index` | Rebuild NumPy embedding index from MongoDB Atlas |

---

## 📊 Confidence Score Logic

| Score Range | Label | Action |
|-------------|-------|--------|
| ≥ 0.80 | 🟢 **High** | Direct mapping — safe to use |
| 0.50 – 0.79 | 🟡 **Medium** | Partial match — review recommended |
| < 0.50 | 🔴 **Low** | Weak match — manual mapping required |

---

## 🧠 AI Models

| Purpose | Model | Details |
|---------|-------|---------|
| **Embeddings** | `models/gemini-embedding-001` | 768-dim vectors, cloud-based, `google-genai` SDK |
| **Vision OCR** | `gemini-2.5-flash` | Converts scanned PDF pages (PNG) to topic lists |
| **Transcription** | Faster-Whisper (`large-v3`) | CPU-based, local, writes back to Atlas |

**Embedding text used per document:**
```
meta_board | meta_class | meta_subject | meta_lesson | meta_topic | audio_script
```

**Change embedding model:** Update `EMBEDDING_MODEL` in `.env`, then click **Rebuild AI Index** in sidebar.

---

## 📦 Technology Stack

| Layer | Technology |
|-------|------------|
| Frontend | Streamlit ≥ 1.33 |
| Backend | FastAPI + Uvicorn |
| AI Embeddings | Google GenAI SDK (`google-genai`) — `gemini-embedding-001` |
| Vision OCR | Google Gemini 2.5 Flash (via `google-genai`) |
| Vector Search | NumPy (`ndarray` cosine similarity — no FAISS required) |
| Database | MongoDB Atlas (primary) + local MongoDB (fallback) |
| Audio Storage | Cloudflare R2 (S3-compatible) |
| File Parsing | pdfplumber, PyMuPDF (fitz), python-docx, openpyxl, pandas |
| Transcription | Faster-Whisper (CPU) |
| Config | python-dotenv |

---

## 🔧 Troubleshooting

| Problem | Fix |
|---------|-----|
| `Backend unreachable` | Run `uvicorn backend:app --reload --port 8000` |
| `Index not ready` | Atlas has no data with `meta_data.audio` — check collection and click **Rebuild AI Index** |
| `Board dropdown empty` | Index not built yet — click **Rebuild AI Index** in sidebar and wait for logs |
| `No topics extracted from PDF` | Use a text-layer PDF; scanned PDFs auto-fallback to Gemini 2.5 Flash Vision OCR |
| `Low confidence scores` | Improve `audio_script` content in Atlas via `transcribe_audios.py` |
| `Subject not filtering by Class` | Ensure Board and Class are both selected first |
| `R2 download failed` | Check `R2_ACCESS_KEY`, `R2_SECRET_KEY`, `R2_ENDPOINT_URL` in `.env` |
| `Whisper model slow` | Increase `MAX_WORKERS` or switch to `small`/`medium` model in `transcribe_audios.py` |

---

## 🔄 Embedding Cache

The backend caches the NumPy index to disk to avoid rebuilding on every restart:

| File | Contents |
|------|----------|
| `.cache/embeddings.npy` | L2-normalised embedding vectors (`float32`) |
| `.cache/metadata.pkl` | Pandas DataFrame with document metadata |

> Delete `.cache/` and click **Rebuild AI Index** to force a full refresh from Atlas.

---

*Built for LearningPad · © 2026*
