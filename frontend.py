"""
=============================================================================
  CURRICULUM MAPPING AUTOMATION SYSTEM — STREAMLIT FRONTEND
  File : frontend.py
  Run  : streamlit run frontend.py
=============================================================================
"""

import streamlit as st
import pandas as pd
import requests
import time
import io
# ─────────────────────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────────────────────
import os
API_BASE = os.getenv("API_URL", "http://127.0.0.1:8000")
TOP_K    = 3          # number of matches returned per topic

# ─────────────────────────────────────────────────────────────────────────────
# PAGE SETUP
# ─────────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Curriculum Mapping · LearningPad",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Sidebar Health ────────────────────────────────────────────────────────────
def check_backend_connection():
    """Verify backend is reachable before starting."""
    try:
        r = requests.get(f"{API_BASE}/health", timeout=2)
        return r.status_code == 200
    except:
        return False

# ─────────────────────────────────────────────────────────────────────────────
# CUSTOM CSS
# ─────────────────────────────────────────────────────────────────────────────
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');
    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
    .stApp { background: #0a0e1a; color: #e8eaf6; }
    section[data-testid="stSidebar"] { background: #0f1629; border-right: 1px solid rgba(255,255,255,0.07); }
    [data-testid="metric-container"] { background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.09); border-radius: 12px; padding: 14px 18px !important; }
    [data-testid="metric-container"] label { color: #9ba4c0 !important; font-size: 11px !important; text-transform: uppercase; letter-spacing: 0.6px; }
    [data-testid="metric-container"] [data-testid="stMetricValue"] { color: #818cf8 !important; font-size: 26px !important; font-weight: 800 !important; }
    h1 { background: linear-gradient(135deg,#e8eaf6 30%,#a78bfa); -webkit-background-clip:text; -webkit-text-fill-color:transparent; font-weight:800 !important; letter-spacing:-1px; }
    .step-banner { background: linear-gradient(135deg, #1e1b4b, #1e1b4b88); border: 1px solid rgba(99,102,241,0.35); border-radius: 14px; padding: 16px 22px; margin-bottom: 20px; display: flex; align-items: center; gap: 14px; }
    .chip { display:inline-block; background:rgba(99,102,241,0.18); color:#818cf8; border:1px solid rgba(99,102,241,0.3); border-radius:999px; padding:2px 10px; font-size:11.5px; font-weight:600; margin:2px; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ─────────────────────────────────────────────────────────────────────────────
# SESSION STATE
# ─────────────────────────────────────────────────────────────────────────────
if "step" not in st.session_state: st.session_state.step = 1
if "upload_data" not in st.session_state: st.session_state.upload_data = None
if "topics" not in st.session_state: st.session_state.topics = None
if "mapping_data" not in st.session_state: st.session_state.mapping_data = None
if "health" not in st.session_state: st.session_state.health = None
if "stats" not in st.session_state: st.session_state.stats = None

# ─────────────────────────────────────────────────────────────────────────────
# API HELPERS
# ─────────────────────────────────────────────────────────────────────────────
def api_get(path: str, params=None) -> dict | list | None:
    try:
        r = requests.get(f"{API_BASE}{path}", params=params, timeout=5)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        return None

def api_post(path: str, **kw) -> dict | list | None:
    try:
        r = requests.post(f"{API_BASE}{path}", timeout=120, **kw)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        st.error(f"❌ API Error: {e}")
        return None

def api_post_raw(path: str, **kw) -> requests.Response | None:
    try:
        r = requests.post(f"{API_BASE}{path}", timeout=120, **kw)
        r.raise_for_status()
        return r
    except Exception as e:
        st.error(f"❌ Export Error: {e}")
        return None

# ─────────────────────────────────────────────────────────────────────────────
# CONFIDENCE HELPERS
# ─────────────────────────────────────────────────────────────────────────────
def conf_emoji(label: str) -> str:
    return {"High": "🟢", "Medium": "🟡", "Low": "🔴"}.get(label, "⚪")

# ─────────────────────────────────────────────────────────────────────────────
# SIDEBAR
# ─────────────────────────────────────────────────────────────────────────────
def render_sidebar():
    with st.sidebar:
        st.markdown("## 📚 LearningPad")
        st.markdown("**Curriculum Mapping Automation**")
        st.divider()

        # ── Health ──
        health = api_get("/health")
        st.session_state.health = health

        st.markdown("### ⚙️ System Status")
        if health:
            mongo_ok = health.get("mongo", False)
            faiss_ok = health.get("faiss_ready", False)
            idx_size = health.get("index_size", 0)
            model_ok = health.get("model_loaded", False)

            col1, col2 = st.columns(2)
            col1.metric("MongoDB", "🟢 ON" if mongo_ok else "🔴 OFF")
            col2.metric("FAISS", "🟢 ON" if faiss_ok else "🔴 OFF")
            col1.metric("AI Model", "🟢 ON" if model_ok else "🔴 OFF")
            col2.metric("Topics DB", f"{idx_size:,}")
        else:
            st.error(f"Backend unreachable on {API_BASE}")
            if st.button("Retry Connection"): st.rerun()
            return

        st.divider()

        # ── Library Stats ──
        st.markdown("### 🗄️ Content Library")
        stats = api_get("/library/stats")
        st.session_state.stats = stats

        if stats and stats.get("connected"):
            st.success(f"Connected · **{stats['total']:,}** items")
            if stats.get("boards"):
                st.markdown("**Boards:**")
                st.markdown(" ".join(f'<span class="chip">{b}</span>' for b in stats["boards"]), unsafe_allow_html=True)
            if stats.get("grades"):
                st.markdown("**Grades:**")
                st.markdown(" ".join(f'<span class="chip">{g}</span>' for g in stats["grades"]), unsafe_allow_html=True)
            if stats.get("subjects"):
                st.markdown("**Subjects:**")
                st.markdown(" ".join(f'<span class="chip">{s}</span>' for s in stats["subjects"]), unsafe_allow_html=True)
        else:
            st.warning("Library aggregation pending or Atlas sync required.")
            if st.button("Refresh Library"): st.rerun()

        # ── Rebuild index ─────────────────────────
        st.divider()
        if st.button("🔄 Rebuild AI Index"):
            with st.spinner("Rebuilding FAISS index from MongoDB…"):
                api_post("/rebuild-index")
                time.sleep(2)
            st.success("Rebuild triggered! Give it a few seconds.")
            st.rerun()

        # ── Navigation ────────────────────────────
        st.divider()
        st.markdown("### 🧭 Navigation")
        STEP_LABELS = {
            1: "📤 Upload Curriculum",
            2: "🔍 Review Topics",
            3: "🤖 AI Mapping",
            4: "📊 Results",
            5: "⬇️ Export",
        }
        for s, label in STEP_LABELS.items():
            disabled = s > st.session_state.step
            if st.button(label, disabled=disabled, key=f"nav_sidebar_{s}", use_container_width=True):
                st.session_state.step = s
                st.rerun()

        st.divider()
        st.caption("© 2026 LearningPad · All data processed locally")


# ─────────────────────────────────────────────────────────────────────────────
# STEP BANNER
# ─────────────────────────────────────────────────────────────────────────────
def step_banner(icon: str, title: str, subtitle: str):
    st.markdown(
        f"""
        <div class="step-banner">
            <div class="step-icon">{icon}</div>
            <div>
                <div class="step-title">{title}</div>
                <div class="step-sub">{subtitle}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ─────────────────────────────────────────────────────────────────────────────
# STEP 1 — UPLOAD
# ─────────────────────────────────────────────────────────────────────────────
def step_upload():
    step_banner("📤", "Step 1 — Upload School Curriculum",
                "Select Class & Subject, then upload the curriculum file to extract topics.")

    health = st.session_state.health
    if not health or not health.get("mongo"):
        st.error("⚠️ Backend or MongoDB is offline. Start the backend first.")
        st.code("uvicorn backend:app --reload --port 8000", language="bash")
        return

    if not health.get("faiss_ready"):
        st.warning(
            "⚠️ The AI index is not ready (no data in MongoDB or model error). "
            "Add content to MongoDB then click **Rebuild AI Index** in the sidebar."
        )

    # ─────────────────────────────────────────────────────────────────────────
    # CLASS & SUBJECT SELECTORS  (live from MongoDB)
    # ─────────────────────────────────────────────────────────────────────────
    st.markdown("### 🎓 Select Class & Subject")
    st.caption("Choose the Class and Subject from the CBSE content library. "
               "This helps the AI focus the mapping and labels your exported file.")

    # Filter Grade based on Board, then Subject based on Grade+Board
    col_b, col_g, col_s = st.columns(3)
    
    with col_b:
        boards_raw = api_get("/library/boards") or []
        boards_list = ["— Select Board —"] + [str(b) for b in boards_raw]
        selected_board = st.selectbox(
            "🏢 School Board",
            options=boards_list,
            index=boards_list.index(st.session_state.get("selected_board", boards_list[0]))
                  if st.session_state.get("selected_board") in boards_list else 0,
            key="upload_board"
        )

    with col_g:
        board_param = selected_board if selected_board != "— Select Board —" else None
        grades_raw = api_get(f"/library/grades?board={board_param}") if board_param else api_get("/library/grades")
        grades_list = ["— Select Class —"] + [str(g) for g in (grades_raw or [])]
        selected_grade = st.selectbox(
            "📚 Class (Grade)",
            options=grades_list,
            index=grades_list.index(st.session_state.get("selected_grade", grades_list[0]))
                  if st.session_state.get("selected_grade") in grades_list else 0,
            key="upload_grade"
        )

    with col_s:
        grade_param = selected_grade if selected_grade != "— Select Class —" else None
        subjects_raw = api_get(f"/library/subjects?grade={grade_param}&board={board_param}") if (grade_param and board_param) \
                       else (api_get(f"/library/subjects?grade={grade_param}") if grade_param \
                       else (api_get(f"/library/subjects?board={board_param}") if board_param else api_get("/library/subjects")))
        subjects_list = ["— Select Subject —"] + [str(s) for s in (subjects_raw or [])]
        selected_subject = st.selectbox(
            "🔬 Subject",
            options=subjects_list,
            index=subjects_list.index(st.session_state.get("selected_subject", subjects_list[0]))
                  if st.session_state.get("selected_subject") in subjects_list else 0,
            key="upload_subject"
        )

    # Persist selections in session state
    st.session_state.selected_board   = selected_board
    st.session_state.selected_grade   = selected_grade
    st.session_state.selected_subject = selected_subject

    # Validation hint
    board_ok   = selected_board   != "— Select Board —"
    grade_ok   = selected_grade   != "— Select Class —"
    subject_ok = selected_subject != "— Select Subject —"

    if board_ok and grade_ok and subject_ok:
        st.success(
            f"✅ Mapping target: **{selected_board}** · **{selected_grade}** · **{selected_subject}**"
        )
    else:
        st.info("📌 Please select a Board, Class and Subject above before uploading.")

    st.divider()

    # ─────────────────────────────────────────────────────────────────────────
    # FILE UPLOAD
    # ─────────────────────────────────────────────────────────────────────────
    st.markdown("### 📂 Upload School Curriculum File")
    st.caption("Accepted formats: Excel, CSV, PDF, Word. "
               "Best results with Excel/CSV files that have a **Topic** or **Lesson** column.")

    uploaded = st.file_uploader(
        "Choose a curriculum file",
        type=["xlsx", "xls", "csv", "pdf", "docx", "doc"],
        help="Accepted formats: Excel, CSV, PDF, Word",
        disabled=(not grade_ok or not subject_ok),   # block upload until class+subject chosen
    )

    if not grade_ok or not subject_ok:
        st.warning("⬆️ Select a Class and Subject first to enable file upload.")
        return

    if uploaded:
        st.success(f"✅ **{uploaded.name}** selected ({uploaded.size / 1024:.1f} KB)")

        if st.button("📥 Extract Topics", use_container_width=True):
            with st.spinner(f"Parsing **{uploaded.name}**…"):
                data = api_post(
                    "/upload-curriculum",
                    files={"file": (uploaded.name, uploaded.getvalue(), uploaded.type)},
                )

            if data:
                st.session_state.upload_data  = data
                st.session_state.topics        = data.get("topics", [])
                st.success(f"🎉 **{data['total_extracted']}** topics extracted!")
                time.sleep(0.8)
                st.session_state.step = 2
                st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# STEP 2 — REVIEW
# ─────────────────────────────────────────────────────────────────────────────
def step_review():
    data   = st.session_state.upload_data
    topics = st.session_state.topics or []

    grade   = st.session_state.get("selected_grade",   "—")
    subject = st.session_state.get("selected_subject", "—")

    step_banner("🔍", "Step 2 — Review Extracted Topics",
                f"Verify the {len(topics)} topics before mapping · {grade} · {subject}")

    col_info, col_btn = st.columns([4, 1])
    with col_info:
        st.markdown(
            f"📄 **File:** `{data['filename']}`  ·  "
            f"**Topics found:** `{data['total_extracted']}`  ·  "
            f"🎓 **{grade}** · **{subject}**"
        )
    with col_btn:
        if st.button("← Re-upload", use_container_width=True):
            st.session_state.step = 1
            st.rerun()

    if not topics:
        st.error("No topics found. Please go back and re-upload.")
        return

    # Display as styled dataframe
    df_preview = pd.DataFrame(topics)
    df_preview.index = df_preview.index + 1
    df_preview.index.name = "#"
    df_preview.columns = ["Topic Name", "Description"] if "description" in df_preview.columns else df_preview.columns

    st.dataframe(df_preview, use_container_width=True, height=420)

    st.divider()

    # Optional: let user pick how many top matches
    top_k = st.slider(
        "Number of top matches to return per topic",
        min_value=1, max_value=10, value=3,
        help="Higher values give more alternatives but take longer."
    )
    st.session_state["top_k"] = top_k

    colA, colB = st.columns([3, 1])
    with colB:
        if st.button("🤖 Run AI Mapping →", use_container_width=True):
            st.session_state.step = 3
            st.rerun()



# ─────────────────────────────────────────────────────────────────────────────
# STEP 3 — MAPPING
# ─────────────────────────────────────────────────────────────────────────────
def step_mapping():
    topics = st.session_state.topics or []
    top_k  = st.session_state.get("top_k", TOP_K)

    step_banner("🤖", "Step 3 — AI Semantic Mapping",
                "Comparing extracted topics against the CBSE content library using Sentence Transformers + FAISS.")

    if not topics:
        st.error("No topics found. Go back to Step 1.")
        if st.button("← Back to Upload"):
            st.session_state.step = 1; st.rerun()
        return

    progress_bar  = st.progress(0,  text="Initialising…")
    status_holder = st.empty()

    stages = [
        (10, "🔧 Loading Sentence Transformer model…"),
        (30, "📝 Encoding school topics into embeddings…"),
        (55, "🔍 Searching FAISS vector index…"),
        (80, "📐 Calculating cosine similarity scores…"),
        (95, "🏷️ Ranking matches by confidence…"),
    ]
    for pct, msg in stages:
        progress_bar.progress(pct, text=msg)
        status_holder.info(msg)
        time.sleep(0.3)

    payload = {"topics": topics, "top_k": top_k}
    result  = api_post("/run-mapping", json=payload)

    if result:
        progress_bar.progress(100, text="✅ Mapping complete!")
        status_holder.success(f"✅ Mapped **{len(result.get('results', []))}** topics using `{result.get('model_used', 'Gemini')}`.")
        time.sleep(0.6)
        st.session_state.mapping_data = result
        st.session_state.step = 4
        st.rerun()
    else:
        progress_bar.empty()
        status_holder.error("Mapping failed. Check that the backend is running and FAISS index is ready.")
        if st.button("← Back to Review"):
            st.session_state.step = 2; st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# STEP 4 — RESULTS
# ─────────────────────────────────────────────────────────────────────────────
def step_results():
    data    = st.session_state.mapping_data or {}
    results = data.get("results", [])

    step_banner("📊", "Step 4 — Mapping Results",
                f"{len(results)} topics mapped · Model: {data.get('model_used','—')}")

    if not results:
        st.error("No results. Run mapping first.")
        if st.button("← Run Mapping"):
            st.session_state.step = 3; st.rerun()
        return

    # ── Summary metrics ─────────────────────────────────────────────────────
    high_n   = sum(1 for r in results if r.get("best_match", {}) and r["best_match"].get("confidence_label") == "High")
    med_n    = sum(1 for r in results if r.get("best_match", {}) and r["best_match"].get("confidence_label") == "Medium")
    low_n    = len(results) - high_n - med_n
    avg_sim  = (
        sum(r["best_match"]["similarity_score"] for r in results if r.get("best_match"))
        / max(1, sum(1 for r in results if r.get("best_match")))
    )

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("🟢 High Confidence",   high_n)
    c2.metric("🟡 Medium Confidence", med_n)
    c3.metric("🔴 Low / No Match",    low_n)
    c4.metric("Avg Similarity",       f"{avg_sim * 100:.1f}%")

    st.divider()

    # ── Filter tabs ──────────────────────────────────────────────────────────
    tab_all, tab_high, tab_med, tab_low = st.tabs(
        [f"All ({len(results)})", f"🟢 High ({high_n})", f"🟡 Medium ({med_n})", f"🔴 Low ({low_n})"]
    )

    def render_results_table(subset):
        if not subset:
            st.info("No results in this category.")
            return

        # ── Build flat DataFrame for display ────────────────────────────────
        rows = []
        for item in subset:
            m = item.get("best_match") or {}
            rows.append({
                "School Topic":    item.get("school_topic", ""),
                "Matched Lesson":  m.get("matched_lesson", "—"),
                "Matched Topic":   m.get("matched_topic",  "—"),
                "Grade":           m.get("matched_grade",  "—"),
                "Subject":         m.get("matched_subject","—"),
                "Board":           m.get("matched_board",  "—"),
                "Similarity %":    f"{m.get('similarity_score', 0) * 100:.1f}%" if m else "—",
                "Confidence":      (conf_emoji(m.get("confidence_label","Low")) + " " + m.get("confidence_label","Low")) if m else "🔴 Low",
            })
        df = pd.DataFrame(rows)
        df.index = df.index + 1
        df.index.name = "#"

        # Colour cells in Confidence column
        def _colour_conf(val):
            if "High"   in str(val): return "color: #22c55e; font-weight:700"
            if "Medium" in str(val): return "color: #f59e0b; font-weight:700"
            return "color: #ef4444; font-weight:700"

        styled = df.style.map(_colour_conf, subset=["Confidence"])
        st.dataframe(styled, use_container_width=True, height=480)

        # ── Expandable audio snippets ────────────────────────────────────────
        with st.expander("🔊 View Audio Script Snippets", expanded=False):
            for item in subset[:30]:   # cap at 30 to avoid huge pages
                m = item.get("best_match") or {}
                snippet = m.get("audio_script_snippet", "")
                if snippet:
                    st.markdown(
                        f"**{item['school_topic']}** → `{m.get('matched_topic','?')}`"
                    )
                    st.caption(snippet)
                    st.divider()

    # Map filter to subset
    subsets = {
        tab_all:  results,
        tab_high: [r for r in results if r.get("best_match", {}) and r["best_match"].get("confidence_label") == "High"],
        tab_med:  [r for r in results if r.get("best_match", {}) and r["best_match"].get("confidence_label") == "Medium"],
        tab_low:  [r for r in results if not r.get("best_match") or r["best_match"].get("confidence_label") == "Low"],
    }
    for tab, subset in subsets.items():
        with tab:
            render_results_table(subset)

    st.divider()

    # ── Detailed drilldown ───────────────────────────────────────────────────
    with st.expander("🔎 Drilldown — All Candidate Matches per Topic", expanded=False):
        st.caption("Shows top-K matches (not just the best one) for each topic.")
        for item in results:
            top_matches = item.get("top_matches", [])
            school_topic = item.get("school_topic", "")
            if not top_matches:
                continue
            st.markdown(f"**{school_topic}**")
            drill_rows = []
            for m in top_matches:
                drill_rows.append({
                    "Rank":        m.get("rank", ""),
                    "Matched Topic":  m.get("matched_topic",""),
                    "Lesson":         m.get("matched_lesson",""),
                    "Grade":          m.get("matched_grade",""),
                    "Subject":        m.get("matched_subject",""),
                    "Similarity":     f"{m.get('similarity_score',0)*100:.1f}%",
                    "Confidence":     m.get("confidence_label",""),
                })
            st.dataframe(pd.DataFrame(drill_rows), use_container_width=True, hide_index=True)
            st.divider()

    col_go = st.columns([3, 1])[1]
    with col_go:
        if st.button("⬇️ Proceed to Export →", use_container_width=True):
            st.session_state.step = 5
            st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# STEP 5 — EXPORT
# ─────────────────────────────────────────────────────────────────────────────
def step_export():
    data    = st.session_state.mapping_data or {}
    results = data.get("results", [])
    # Read selections made in Step 1
    preset_board   = st.session_state.get("selected_board",   "All Boards")
    preset_grade   = st.session_state.get("selected_grade",   "All Classes")
    preset_subject = st.session_state.get("selected_subject", "All Subjects")

    step_banner("⬇️", "Step 5 — Export Results",
                f"Board: {preset_board}  ·  Class: {preset_grade}  ·  Subject: {preset_subject}  ·  Download the final curriculum mapping.")

    if not results:
        st.error("No mapping data to export. Run the mapping first.")
        if st.button("← Go to Mapping"):
            st.session_state.step = 3; st.rerun()
        return

    # ─────────────────────────────────────────────────────────────────────────
    # BOARD, CLASS & SUBJECT FILTER (pre-filled from Step 1, editable here too)
    # ─────────────────────────────────────────────────────────────────────────
    st.markdown("### 🎯 Board, Class & Subject Filter")
    st.caption(
        "Pre-filled from your Step 1 selection. You can change these here to filter the export differently."
    )

    boards_raw  = api_get("/library/boards") or []
    boards_list = ["All Boards"] + [str(b) for b in boards_raw]
    default_board = preset_board if preset_board in boards_list else "All Boards"

    col_b, col_g, col_s = st.columns(3)

    with col_b:
        selected_board = st.selectbox(
            "🏢 School Board",
            options=boards_list,
            index=boards_list.index(default_board),
            key="export_board"
        )
    
    board_param = selected_board if selected_board != "All Boards" else None
    grades_raw  = api_get(f"/library/grades?board={board_param}") if board_param else api_get("/library/grades")
    grades_list = ["All Classes"] + [str(g) for g in (grades_raw or [])]
    default_grade = preset_grade if preset_grade in grades_list else "All Classes"

    with col_g:
        selected_grade = st.selectbox(
            "📚 Class (Grade)",
            options=grades_list,
            index=grades_list.index(default_grade),
            key="export_grade"
        )

    # Load subjects for chosen grade/board
    grade_param = selected_grade if selected_grade != "All Classes" else None
    
    subjects_raw = api_get(f"/library/subjects?grade={grade_param}&board={board_param}") if (grade_param and board_param) \
                   else (api_get(f"/library/subjects?grade={grade_param}") if grade_param \
                   else (api_get(f"/library/subjects?board={board_param}") if board_param else api_get("/library/subjects")))
    
    subjects_list = ["All Subjects"] + [str(s) for s in (subjects_raw or [])]
    default_subject = preset_subject if preset_subject in subjects_list else "All Subjects"

    with col_s:
        selected_subject = st.selectbox(
            "🔬 Subject",
            options=subjects_list,
            index=subjects_list.index(default_subject),
            key="export_subject",
            help="Subjects filtered by the chosen Class"
        )

    st.divider()

    # ─────────────────────────────────────────────────────────────────────────
    # FILTER RESULTS
    # ─────────────────────────────────────────────────────────────────────────
    def matches_filter(item):
        m = (item.get("best_match") or {}) if isinstance(item.get("best_match"), dict) else {}
        board_ok   = selected_board   == "All Boards"   or m.get("matched_board",   "") == selected_board
        grade_ok   = selected_grade   == "All Classes"  or m.get("matched_grade",   "") == selected_grade
        subject_ok = selected_subject == "All Subjects" or m.get("matched_subject", "") == selected_subject
        return board_ok and grade_ok and subject_ok

    filtered_results = [r for r in results if matches_filter(r)]

    # Status banner
    if selected_grade == "All Classes" and selected_subject == "All Subjects":
        st.success(f"✅ Exporting **all {len(filtered_results)} topics** — no filter applied.")
    else:
        parts = []
        if selected_grade   != "All Classes":  parts.append(f"Class: **{selected_grade}**")
        if selected_subject != "All Subjects": parts.append(f"Subject: **{selected_subject}**")
        label = " · ".join(parts)
        if filtered_results:
            st.success(f"✅ **{len(filtered_results)}** of {len(results)} topics match {label}")
        else:
            st.warning(
                f"⚠️ No results match {label}. "
                "Try different filters or select **All Classes / All Subjects**."
            )

    # ─────────────────────────────────────────────────────────────────────────
    # BUILD FLAT ROWS
    # ─────────────────────────────────────────────────────────────────────────
    flat_rows = []
    for item in filtered_results:
        m = item.get("best_match") or {}
        flat_rows.append({
            "School Topic":         item.get("school_topic", ""),
            "Description":          item.get("description", ""),
            "Matched Board":        m.get("matched_board",  ""),
            "Matched Grade":        m.get("matched_grade",  ""),
            "Matched Subject":      m.get("matched_subject",""),
            "Matched Lesson":       m.get("matched_lesson", ""),
            "Matched Topic":        m.get("matched_topic",  ""),
            "Similarity Score":     m.get("similarity_score", ""),
            "Confidence":           m.get("confidence_label", ""),
            "Audio Script Snippet": m.get("audio_script_snippet", ""),
        })

    # Filename slug  e.g.  CBSE_Class6_Science.xlsx
    b_slug = selected_board.replace(" ", "")   if selected_board   != "All Boards"   else "AllBoards"
    g_slug = selected_grade.replace(" ", "")   if selected_grade   != "All Classes"  else "AllClasses"
    s_slug = selected_subject.replace(" ", "") if selected_subject != "All Subjects" else "AllSubjects"
    file_slug = f"{b_slug}_{g_slug}_{s_slug}"

    # ─────────────────────────────────────────────────────────────────────────
    # PREVIEW TABLE
    # ─────────────────────────────────────────────────────────────────────────
    st.markdown(f"### 👁️ Preview — {len(flat_rows)} rows")

    if flat_rows:
        preview_df = pd.DataFrame(flat_rows)
        preview_df.index = preview_df.index + 1
        preview_df.index.name = "#"

        def _colour_conf(val):
            if "High"   in str(val): return "color:#22c55e;font-weight:700"
            if "Medium" in str(val): return "color:#f59e0b;font-weight:700"
            return "color:#ef4444;font-weight:700"

        st.dataframe(
            preview_df.style.map(_colour_conf, subset=["Confidence"]),
            use_container_width=True, height=380
        )
    else:
        st.info("No rows match the current filter — adjust Class/Subject above.")

    st.divider()

    # ─────────────────────────────────────────────────────────────────────────
    # DOWNLOAD BUTTONS
    # ─────────────────────────────────────────────────────────────────────────
    st.markdown("### ⬇️ Download")

    if not flat_rows:
        st.warning("Nothing to download — adjust the Class/Subject filter above.")
    else:
        col1, col2, col3 = st.columns(3)

        with col1:
            st.markdown("#### 📗 Excel (.xlsx)")
            st.caption("Formatted file with auto-sized columns.")
            if st.button("Generate Excel", key="dl_xlsx", use_container_width=True):
                with st.spinner("Generating Excel…"):
                    resp = api_post_raw("/export?fmt=xlsx", json=filtered_results)
                if resp:
                    st.download_button(
                        label=f"📥 Save  mapping_{file_slug}.xlsx",
                        data=resp.content,
                        file_name=f"mapping_{file_slug}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True,
                        key="save_xlsx",
                    )

        with col2:
            st.markdown("#### 📄 CSV (.csv)")
            st.caption("Universal spreadsheet format.")
            if st.button("Generate CSV", key="dl_csv", use_container_width=True):
                with st.spinner("Generating CSV…"):
                    resp = api_post_raw("/export?fmt=csv", json=filtered_results)
                if resp:
                    st.download_button(
                        label=f"📥 Save  mapping_{file_slug}.csv",
                        data=resp.content,
                        file_name=f"mapping_{file_slug}.csv",
                        mime="text/csv",
                        use_container_width=True,
                        key="save_csv",
                    )

        with col3:
            st.markdown("#### 🗂️ Quick CSV (local)")
            st.caption("Instant download — no API call needed.")
            quick_csv = pd.DataFrame(flat_rows).to_csv(index=False).encode("utf-8")
            st.download_button(
                label=f"📥 Save  mapping_{file_slug}_quick.csv",
                data=quick_csv,
                file_name=f"mapping_{file_slug}_quick.csv",
                mime="text/csv",
                use_container_width=True,
                key="dl_quick_csv",
            )

    st.divider()
    st.info(
        "💡 **Confidence Guide:**\n"
        "- 🟢 **High** (≥ 80%) — Strong match. Safe to use directly.\n"
        "- 🟡 **Medium** (50–79%) — Partial match. Review recommended.\n"
        "- 🔴 **Low** (< 50%) — Weak match. Requires manual mapping."
    )

    st.divider()
    if st.button("🔁 Map Another Curriculum", use_container_width=True):
        for k in ["upload_data", "topics", "mapping_data", "selected_grade", "selected_subject"]:
            st.session_state[k] = None
        st.session_state.step = 1
        st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# STEP PROGRESS BAR  (top of main area)
# ─────────────────────────────────────────────────────────────────────────────
def render_step_progress():
    step = st.session_state.step
    labels = ["Upload", "Review", "AI Map", "Results", "Export"]
    n = len(labels)
    cols = st.columns(n)
    for i, (col, label) in enumerate(zip(cols, labels), start=1):
        with col:
            active  = (i == step)
            done    = (i < step)
            colour  = "#6366f1" if active else ("#22c55e" if done else "#1e2a4a")
            text_c  = "#e0e7ff" if active or done else "#5f6b8a"
            border  = f"2px solid {colour}"
            st.markdown(
                f"""
                <div style="text-align:center; padding:8px 4px; border-radius:10px;
                            border:{border}; background:{'rgba(99,102,241,0.12)' if active else 'rgba(34,197,94,0.07)' if done else 'rgba(255,255,255,0.03)'};">
                  <div style="font-size:18px;">{"✓" if done else str(i)}</div>
                  <div style="font-size:11px; color:{text_c}; font-weight:{'700' if active else '500'};">{label}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────
def main():
    render_sidebar()

    st.title("📚 Curriculum Mapping Automation")
    st.markdown(
        "*Automatically map school curriculum topics to CBSE content using "
        "**Sentence Transformers** + **FAISS** semantic search on audio scripts.*"
    )
    st.divider()

    render_step_progress()
    st.markdown("<br>", unsafe_allow_html=True)

    step = st.session_state.step
    if   step == 1: step_upload()
    elif step == 2: step_review()
    elif step == 3: step_mapping()
    elif step == 4: step_results()
    elif step == 5: step_export()


if __name__ == "__main__":
    main()
