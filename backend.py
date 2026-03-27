"""
=============================================================================
  CURRICULUM MAPPING AUTOMATION SYSTEM - BACKEND
  File: backend.py
  Description: FastAPI backend with MongoDB + NumPy semantic search
=============================================================================
  Run with:
    uvicorn backend:app --reload --host 127.0.0.1 --port 8000
============================================================================="""

import os
import io
import json
import logging
import traceback
from datetime import datetime
from typing import List, Optional, Dict, Any
from contextlib import asynccontextmanager

import numpy as np
import pandas as pd
import pdfplumber
from google import genai
from google.genai import types
from docx import Document
from pymongo import MongoClient
from dotenv import load_dotenv

from fastapi import FastAPI, UploadFile, File, HTTPException, Query, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────────────────────────────────────
load_dotenv()

MONGO_URI        = os.getenv("ATLAS_MONGO_URI") or os.getenv("MONGO_URI", "mongodb://localhost:27017/")
DB_NAME          = os.getenv("ATLAS_DB_NAME") or os.getenv("DB_NAME", "LRN_LESSONS")
COLLECTION_NAME  = os.getenv("ATLAS_COLLECTION_NAME") or os.getenv("COLLECTION_NAME", "Models")
MODEL_NAME       = os.getenv("EMBEDDING_MODEL", "models/gemini-embedding-001")
GOOGLE_API_KEY   = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
ALLOWED_ORIGINS  = os.getenv("ALLOWED_ORIGINS", "*").split(",")

HIGH_CONF   = 0.80
MEDIUM_CONF = 0.50

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

CACHE_DIR = os.path.join(os.getcwd(), ".cache")
EMBED_CACHE = os.path.join(CACHE_DIR, "embeddings.npy")
META_CACHE  = os.path.join(CACHE_DIR, "metadata.pkl")

# ─────────────────────────────────────────────────────────────────────────────
# GLOBAL STATE
# ─────────────────────────────────────────────────────────────────────────────
class AppState:
    mongo_client:   Optional[MongoClient]    = None
    collection:     Any                      = None
    atlas_db:       Any                      = None
    np_index:       Optional[np.ndarray]     = None
    index_df:       Optional[pd.DataFrame]   = None
    index_ready:    bool                     = False
    mongo_ok:       bool                     = False
    genai_client:   Optional[genai.Client]   = None

state = AppState()

# ─────────────────────────────────────────────────────────────────────────────
# STARTUP / SHUTDOWN
# ─────────────────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("=== Starting Backend ===")
    _connect_mongo()
    _load_model()
    if not _load_cache():
        _build_index()
    yield
    if state.mongo_client: state.mongo_client.close()

def _connect_mongo():
    try:
        state.mongo_client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        state.mongo_client.admin.command("ping")
        state.atlas_db = state.mongo_client[DB_NAME]
        state.collection = state.atlas_db[COLLECTION_NAME]
        state.mongo_ok = True
        log.info(f"✅ MongoDB connected: {DB_NAME}")
    except Exception as e:
        state.mongo_ok = False
        log.warning(f"⚠️ MongoDB Error: {e}")

def _load_model():
    if GOOGLE_API_KEY:
        state.genai_client = genai.Client(api_key=GOOGLE_API_KEY)
        log.info("✅ GenAI ready.")

def _build_index():
    if not state.mongo_ok or not state.genai_client: return
    try:
        log.info("Building index from MongoDB Atlas...")
        all_docs = []
        for col in ["Models", "Activities"]:
            if col in state.atlas_db.list_collection_names():
                docs = list(state.atlas_db[col].find({"meta_data.audio": {"$exists": True}}, {"_id": 0}))
                for d in docs:
                    d["_source_collection"] = col
                    url = d.get("url", "")
                    parts = url.split("/")
                    if len(parts) >= 4:
                        d["meta_board"]   = parts[0]
                        d["meta_class"]   = parts[1]
                        d["meta_subject"] = parts[2]
                        d["meta_lesson"]  = parts[3]
                        d["meta_topic"]   = parts[5].split(".")[1] if len(parts) >= 6 and "." in parts[5] else (parts[5] if len(parts) >= 6 else "")
                    else:
                        d["meta_board"]   = ""
                        d["meta_class"]   = ""
                        d["meta_subject"] = ""
                        d["meta_lesson"]  = ""
                        d["meta_topic"]   = ""
                all_docs.extend(docs)
        
        if not all_docs: return
        df = pd.DataFrame(all_docs)
        
        def _get_text(row):
            parts = [str(row.get(f, "")) for f in ["meta_board", "meta_class", "meta_subject", "meta_lesson", "meta_topic"]]
            audio = row.get("meta_data", {}).get("audio", [])
            if audio: parts.append(str(audio[0].get("audio_script", "")))
            return " | ".join([p for p in parts if p.strip()])

        df["_embed_text"] = df.apply(_get_text, axis=1)
        df = df[df["_embed_text"].str.strip() != ""].reset_index(drop=True)
        
        texts = df["_embed_text"].tolist()
        
        batch_size = 100
        all_embeddings = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            res = state.genai_client.models.embed_content(
                model=MODEL_NAME, contents=batch,
                config=types.EmbedContentConfig(task_type="RETRIEVAL_DOCUMENT")
            )
            all_embeddings.extend([e.values for e in res.embeddings])
            log.info(f"Embedded batch {i//batch_size + 1}/{(len(texts)+batch_size-1)//batch_size}")
            
        embeddings = np.array(all_embeddings).astype("float32")
        norms = np.linalg.norm(embeddings, axis=1, keepdims=True); norms[norms==0]=1e-10
        state.np_index = embeddings / norms
        state.index_df = df
        state.index_ready = True
        _save_cache()
        log.info(f"✅ Index built: {len(df)} items")
    except Exception as e:
        log.error(f"❌ Build failed: {e}")

def _save_cache():
    if not os.path.exists(CACHE_DIR): os.makedirs(CACHE_DIR)
    if state.np_index is not None: np.save(EMBED_CACHE, state.np_index)
    if state.index_df is not None: state.index_df.to_pickle(META_CACHE)

def _load_cache():
    if not os.path.exists(EMBED_CACHE) or not os.path.exists(META_CACHE): return False
    try:
        state.np_index = np.load(EMBED_CACHE)
        state.index_df = pd.read_pickle(META_CACHE)
        state.index_ready = True
        return True
    except: return False

# ─────────────────────────────────────────────────────────────────────────────
# API HELPERS
# ─────────────────────────────────────────────────────────────────────────────
def _semantic_search(query: str, top_k: int):
    res = state.genai_client.models.embed_content(
        model=MODEL_NAME, contents=query,
        config=types.EmbedContentConfig(task_type="RETRIEVAL_QUERY")
    )
    q = np.array(res.embeddings[0].values, dtype="float32")
    n = np.linalg.norm(q); q = q/n if n>0 else q
    scores = state.np_index @ q
    idxs = np.argsort(scores)[::-1][:top_k]
    matches = []
    for rank, i in enumerate(idxs):
        row = state.index_df.iloc[i]
        sim = float(scores[i])
        audio = row.get("meta_data", {}).get("audio", [])
        script = audio[0].get("audio_script", "") if audio else ""
        matches.append({
            "rank": rank + 1,
            "matched_board": row.get("meta_board", ""),
            "matched_grade": row.get("meta_class", ""),
            "matched_subject": row.get("meta_subject", ""),
            "matched_lesson": row.get("meta_lesson", ""),
            "matched_topic": row.get("meta_topic", ""),
            "audio_script_snippet": script[:250],
            "similarity_score": round(sim, 4),
            "confidence_label": "High" if sim >= 0.8 else "Medium" if sim >= 0.5 else "Low"
        })
    return matches

# ─────────────────────────────────────────────────────────────────────────────
# ROUTES
# ─────────────────────────────────────────────────────────────────────────────
app = FastAPI(lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.get("/health")
def health():
    return {
        "mongo": state.mongo_ok, "faiss_ready": state.index_ready,
        "index_size": len(state.np_index) if state.index_ready else 0,
        "model_loaded": state.genai_client is not None
    }

@app.get("/library/stats")
def stats():
    if not state.index_ready or state.index_df is None: return {"connected": False}
    boards = state.index_df["meta_board"].dropna().unique().tolist()
    grades = state.index_df["meta_class"].dropna().unique().tolist()
    subs = state.index_df["meta_subject"].dropna().unique().tolist()
    return {
        "connected": True, 
        "total": len(state.index_df), 
        "boards": sorted([str(b) for b in boards if b]),
        "grades": sorted([str(g) for g in grades if g]), 
        "subjects": sorted([str(s) for s in subs if s])
    }

@app.get("/library/boards")
def boards():
    if not state.index_ready or state.index_df is None: return []
    boards = state.index_df["meta_board"].dropna().unique().tolist()
    return sorted([str(b) for b in boards if b])

@app.get("/library/grades")
def grades(board: str = None):
    if not state.index_ready or state.index_df is None: return []
    df = state.index_df
    if board: df = df[df["meta_board"] == board]
    grades = df["meta_class"].dropna().unique().tolist()
    return sorted([str(g) for g in grades if g])

@app.get("/library/subjects")
def subjects(grade: str = None, board: str = None):
    if not state.index_ready or state.index_df is None: return []
    df = state.index_df
    if board: df = df[df["meta_board"] == board]
    if grade: df = df[df["meta_class"] == grade]
    subs = df["meta_subject"].dropna().unique().tolist()
    return sorted([str(s) for s in subs if s])

@app.post("/rebuild-index")
async def rebuild_index(background_tasks: BackgroundTasks):
    background_tasks.add_task(_build_index)
    return {"status": "Rebuild triggered in background."}

@app.post("/upload-curriculum")
async def upload(file: UploadFile = File(...)):
    b = await file.read()
    topics = []
    fname = file.filename.lower()
    
    try:
        if fname.endswith((".xlsx", ".xls")):
            df = pd.read_excel(io.BytesIO(b))
            topics = [{"topic_name": str(row[0])} for _, row in df.iterrows() if pd.notna(row[0]) and str(row[0]).strip()]
        elif fname.endswith(".csv"):
            df = pd.read_csv(io.BytesIO(b))
            topics = [{"topic_name": str(row[0])} for _, row in df.iterrows() if pd.notna(row[0]) and str(row[0]).strip()]
        elif fname.endswith(".pdf"):
            with pdfplumber.open(io.BytesIO(b)) as pdf:
                for page in pdf.pages:
                    text = page.extract_text()
                    if text:
                        lines = [line.strip() for line in text.split("\n") if line.strip()]
                        for line in lines:
                            if len(line) > 3:
                                topics.append({"topic_name": line})
            
            # OCR Fallback for Screenshot/Image PDFs
            if len(topics) == 0 and state.genai_client:
                log.info("No text detected in PDF, falling back to Visual OCR via PyMuPDF + Gemini...")
                import fitz
                try:
                    pdf_doc = fitz.open(stream=b, filetype="pdf")
                    # Process first 3 pages (usually enough for syllabus summary)
                    images_parts = []
                    for page_num in range(min(len(pdf_doc), 3)):
                        page = pdf_doc.load_page(page_num)
                        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2)) # Higher resolution (2x)
                        img_bytes = pix.tobytes("png")
                        images_parts.append(types.Part.from_bytes(data=img_bytes, mime_type="image/png"))
                    
                    if images_parts:
                        response = state.genai_client.models.generate_content(
                            model="gemini-2.5-flash",
                            contents=images_parts + [
                                "Extract all the distinct curriculum topic names or lesson titles from these document images. "
                                "Output ONLY a raw JSON array of strings, with no markdown formatting or extra text. "
                                "Example: [\"Photosynthesis\", \"Newton's Laws\"]"
                            ]
                        )
                        gen_text = response.text.replace("```json", "").replace("```", "").strip()
                        extracted_list = json.loads(gen_text)
                        for t in extracted_list:
                            if isinstance(t, str) and len(t) > 3:
                                topics.append({"topic_name": t})
                    pdf_doc.close()
                except Exception as e:
                    log.error(f"Visual OCR fallback failed: {e}")

        elif fname.endswith(".docx") or fname.endswith(".doc"):
            doc = Document(io.BytesIO(b))
            for para in doc.paragraphs:
                txt = para.text.strip()
                if len(txt) > 3:
                    topics.append({"topic_name": txt})
        else:
            raise HTTPException(status_code=400, detail="Unsupported file type.")
            
        return {"filename": file.filename, "total_extracted": len(topics), "topics": topics}
    except Exception as e:
        log.error(f"Error parsing uploaded file: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to parse file: {str(e)}")

@app.post("/run-mapping")
def mapping(data: dict):
    results = []
    for t in data["topics"]:
        matches = _semantic_search(t["topic_name"], data.get("top_k", 3))
        results.append({"school_topic": t["topic_name"], "best_match": matches[0] if matches else None, "top_matches": matches})
    return {"results": results, "model_used": MODEL_NAME}

@app.post("/export")
def export(results: List[Dict], fmt: str = "xlsx"):
    rows = []
    for item in results:
        m = item.get("best_match") or {}
        if not isinstance(m, dict): m = {}
        rows.append({
            "School Topic": item.get("school_topic", ""),
            "Description": item.get("description", ""),
            "Matched Board": m.get("matched_board", ""),
            "Matched Grade": m.get("matched_grade", ""),
            "Matched Subject": m.get("matched_subject", ""),
            "Matched Lesson": m.get("matched_lesson", ""),
            "Matched Topic": m.get("matched_topic", ""),
            "Similarity": m.get("similarity_score", ""),
            "Confidence": m.get("confidence_label", ""),
            "Audio Script": m.get("audio_script_snippet", ""),
        })
    df = pd.DataFrame(rows)
    out = io.BytesIO()
    
    if fmt.lower() == "csv":
        csv_str = df.to_csv(index=False)
        return StreamingResponse(io.BytesIO(csv_str.encode()), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=mapping.csv"})
    
    with pd.ExcelWriter(out, engine="openpyxl") as w:
        df.to_excel(w, index=False, sheet_name="Mapping")
    out.seek(0)
    return StreamingResponse(out, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": "attachment; filename=mapping.xlsx"})

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
