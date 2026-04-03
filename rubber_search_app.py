#!/usr/bin/env python3
"""
橡膠配方規格篩選系統
- [A] - [F] 模組化全寬排版 (垂直堆疊)
- 支援雙主題切換 (Light / Dark)
- 強化區塊邊界感
"""

from __future__ import annotations

import base64
import json
import os
import time
import io
from datetime import datetime
from pathlib import Path

import streamlit as st
import pandas as pd
import pdfplumber
from PIL import Image
from pypdf import PdfReader, PdfWriter

# ─────────────────────────────────────────────
# [B] Header Bar Configuration & Paths
# ─────────────────────────────────────────────
BASE_DIR     = Path(__file__).resolve().parent
JSON_PATH    = BASE_DIR / "formulary_data.json"

PDF_MAP = {
    "ACM": "Rubber Formulary ACM.pdf",
    "CR": "Rubber Formulary CR.pdf",
    "EPDM": "Rubber Formulary EPDM.pdf",
    "NBR": "Rubber Formulary NBR.pdf",
    "NR/SBR/BR": "Rubber Formulary NR:SBR:BR:IIR.pdf",
}

FIELDS = [
    {"key": "hardness",          "label": "Hardness",          "unit": "Shore A"},
    {"key": "tensile_strength",  "label": "Tensile Strength",  "unit": "MPa"},
    {"key": "elongation",        "label": "Elongation",        "unit": "%"},
    {"key": "modulus_100",       "label": "100% Modulus",      "unit": "MPa"},
    {"key": "modulus_300",       "label": "300% Modulus",      "unit": "MPa"},
    {"key": "compression_set",   "label": "Compression Set",   "unit": "%"},
    {"key": "specific_gravity",  "label": "Specific Gravity",  "unit": ""},
]

RUBBER_TYPES = ["NR/SBR/BR", "EPDM", "NBR", "CR", "ACM"]

# ─────────────────────────────────────────────
# Themes Styling Constants [B] & [A] Compactness
# ─────────────────────────────────────────────

COMMON_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');
html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
h1 { font-size: 2.2rem !important; font-weight: 800 !important; letter-spacing: -1px; margin-bottom: 0.1rem !important; }
.filter-header { font-size: 0.70rem; font-weight: 700; text-transform: uppercase; letter-spacing: 1.2px; margin-bottom: 8px; margin-top: 10px; }
.result-chip { display:inline-block; border-radius: 6px; padding: 4px 12px; font-size:.85rem; font-weight:600; margin-bottom: 12px; }
div.stButton > button { border: none !important; border-radius: 8px !important; font-weight: 600 !important; transition: all 0.2s !important; width: 100%; }
.stCheckbox label { font-weight: 600 !important; font-size: 0.9rem !important; }

/* [A] Sidebar Item Compactness */
div[data-testid="stSidebar"] [data-testid="stVerticalBlock"] > div { padding-top: 0 !important; padding-bottom: 0.2rem !important; }
div[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p { margin-bottom: 0px !important; }
div[data-testid="stSidebar"] hr { margin: 0.5rem 0 !important; }

/* Section Box Styling for boundaries */
.section-box {
    border-radius: 12px;
    padding: 20px;
    margin-bottom: 24px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.06);
    border-width: 1px;
    border-style: solid;
}
</style>
"""

LIGHT_THEME_CSS = """
<style>
.stApp { background: #fdfdfd; color: #1e293b; }
section[data-testid="stSidebar"] { background: #ffffff !important; border-right: 1px solid #e2e8f0 !important; }
section[data-testid="stSidebar"] * { color: #334155 !important; }
h1 { background: linear-gradient(90deg, #1e40af, #3b82f6); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; }
.filter-header { color: #64748b !important; }
.result-chip { background: #eff6ff; border: 1px solid #bfdbfe; color:#2563eb; }
div.stButton > button { background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%) !important; color: white !important; }
.stCheckbox label { color: #334155 !important; }
hr { border-color: #e2e8f0 !important; }
div[data-testid="stNumberInput"] input { background: #ffffff !important; border: 1px solid #cbd5e1 !important; color: #1e293b !important; }
div[data-testid="stPills"] button { background: #ffffff !important; border: 1px solid #e2e8f0 !important; color: #475569 !important; }
div[data-testid="stPills"] button[aria-pressed="true"] { background: #3b82f6 !important; color: white !important; }
div[data-testid="stDataFrame"] { background: #ffffff !important; border: 1px solid #e2e8f0 !important; }
.section-box { background: #ffffff; border-color: #e2e8f0; }
</style>
"""

DARK_THEME_CSS = """
<style>
.stApp { background: #0b0f19; color: #f8fafc; }
section[data-testid="stSidebar"] { background: #111827 !important; border-right: 1px solid #1f2937 !important; }
section[data-testid="stSidebar"] * { color: #cbd5e1 !important; }
h1 { background: linear-gradient(90deg, #a78bfa, #60a5fa); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; }
.filter-header { color: #94a3b8 !important; }
.result-chip { background: #1e293b; border: 1px solid #334155; color:#a78bfa; }
div.stButton > button { background: linear-gradient(135deg, #7c3aed 0%, #4f46e5 100%) !important; color: white !important; }
.stCheckbox label { color: #cbd5e1 !important; }
hr { border-color: #1f2937 !important; }
div[data-testid="stNumberInput"] input { background: #1f2937 !important; border: 1px solid #374151 !important; color: #f8fafc !important; }
div[data-testid="stPills"] button { background: #1f2937 !important; border: 1px solid #374151 !important; color: #cbd5e1 !important; }
div[data-testid="stPills"] button[aria-pressed="true"] { background: #7c3aed !important; color: white !important; }
div[data-testid="stDataFrame"] { background: #1f2937 !important; border: 1px solid #374151 !important; }
.section-box { background: #111827; border-color: #1f2937; }
</style>
"""

# ─────────────────────────────────────────────
# Data & PDF Helpers
# ─────────────────────────────────────────────

@st.cache_data(show_spinner=False)
def load_data() -> list[dict]:
    if not JSON_PATH.exists(): return []
    try:
        data = json.loads(JSON_PATH.read_text(encoding="utf-8"))
        for r in data:
            if "rubber_type" not in r: r["rubber_type"] = "EPDM"
        return data
    except Exception: return []

@st.cache_resource
def get_pdf_doc(rubber_type: str):
    filename = PDF_MAP.get(rubber_type)
    if not filename: return None
    path = BASE_DIR / filename
    if path.exists():
        try: return pdfplumber.open(path)
        except: return None
    return None

def apply_filters(records: list[dict], selected_types: list[str], active_filters: dict) -> list[dict]:
    out = []
    for rec in records:
        if selected_types and rec.get("rubber_type") not in selected_types: continue
        pass_all = True
        for key, limits in active_filters.items():
            val = rec.get(key)
            if val is None:
                pass_all = False; break
            lo, hi = limits["lo"], limits["hi"]
            if lo is not None and val < lo:
                pass_all = False; break
            if hi is not None and val > hi:
                pass_all = False; break
        if pass_all: out.append(rec)
    return out

def render_pdf_page_html(rubber_type: str, page_num: int, zoom_mode: str = "完整 A4 (符合頁面)"):
    doc = get_pdf_doc(rubber_type)
    if doc is None:
        st.error(f"找不到檔案: {PDF_MAP.get(rubber_type, rubber_type)}")
        return
    try:
        page = doc.pages[page_num - 1]
        img = page.to_image(resolution=150).original
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        img_str = base64.b64encode(buf.getvalue()).decode()
        
        if zoom_mode == "符合頁寬":
            img_style = "width: 100%; height: auto;"
        elif zoom_mode == "原始高畫質放大":
            img_style = "width: 1400px; max-width: none;"
        else: # "完整 A4 (符合頁面)"
            img_style = "max-width: 100%; max-height: 800px; width: auto; height: auto;"
            
        html = f'''
        <div style="width:100%; overflow-x:auto; text-align:center; padding:10px 0;">
            <img src="data:image/jpeg;base64,{img_str}" style="{img_style} border-radius:8px; box-shadow: 0 4px 10px rgba(0,0,0,0.15);">
        </div>
        '''
        st.markdown(html, unsafe_allow_html=True)
    except Exception as e: st.error(f"渲染錯誤: {e}")

def export_merged_pdf(selected_items: list[dict]) -> bytes:
    writer = PdfWriter()
    readers = {}
    for item in selected_items:
        rtype = item.get("rubber_type", "EPDM")
        pnum = int(item.get("page", 1))
        if rtype not in readers:
            fname = PDF_MAP.get(rtype)
            if fname and (BASE_DIR / fname).exists(): readers[rtype] = PdfReader(BASE_DIR / fname)
            else: continue
        reader = readers[rtype]
        if 1 <= pnum <= len(reader.pages): writer.add_page(reader.pages[pnum - 1])
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()

# ─────────────────────────────────────────────
# UI Entry Point
# ─────────────────────────────────────────────

def main():
    st.set_page_config(page_title="橡膠配方規格篩選系統", page_icon="🧪", layout="wide")
    
    if "app_theme" not in st.session_state:
        st.session_state.app_theme = "Light"
        
    st.markdown(COMMON_CSS, unsafe_allow_html=True)
    if st.session_state.app_theme == "Light":
        st.markdown(LIGHT_THEME_CSS, unsafe_allow_html=True)
    else:
        st.markdown(DARK_THEME_CSS, unsafe_allow_html=True)

    records = load_data()

    # ─────────────────────────────────────────────
    # [A] Sidebar Filters (更緊湊)
    # ─────────────────────────────────────────────
    with st.sidebar:
        st.markdown("## 🔬 規格篩選條件")
        st.markdown("---")
        st.markdown('<p class="filter-header">勾選要篩選的規格</p>', unsafe_allow_html=True)

        active_filters: dict = {}
        for field in FIELDS:
            key, label, unit = field["key"], field["label"], field["unit"]
            enabled = st.checkbox(f"{label}", key=f"chk_{key}")
            if enabled:
                c1, c2 = st.columns(2)
                with c1: lo = st.number_input(f"下限 ({unit})" if unit else "下限", value=None, key=f"lo_{key}")
                with c2: hi = st.number_input(f"上限 ({unit})" if unit else "上限", value=None, key=f"hi_{key}")
                if lo is not None or hi is not None: active_filters[key] = {"lo": lo, "hi": hi}
            st.markdown("---")

    # ─────────────────────────────────────────────
    # [B] Header Bar
    # ─────────────────────────────────────────────
    col_title, col_theme = st.columns([5, 1])
    with col_title:
        st.title("🧪 橡膠配方規格篩選系統")
    with col_theme:
        st.markdown('<div style="margin-bottom:15px"></div>', unsafe_allow_html=True)
        new_theme = st.selectbox("🌓 主題", ["Light", "Dark"], index=0 if st.session_state.app_theme == "Light" else 1, label_visibility="collapsed")
        if new_theme != st.session_state.app_theme:
            st.session_state.app_theme = new_theme
            st.rerun()

    # ─────────────────────────────────────────────
    # [C] Type Pills
    # ─────────────────────────────────────────────
    st.markdown('<div class="section-box">', unsafe_allow_html=True)
    st.markdown('<p class="filter-header">選擇膠種分組</p>', unsafe_allow_html=True)
    selected_rubber_types = st.pills("膠種", RUBBER_TYPES, selection_mode="multi", label_visibility="collapsed")
    st.markdown('</div>', unsafe_allow_html=True)

    # Filter
    filtered = apply_filters(records, selected_rubber_types, active_filters)
    
    # ─────────────────────────────────────────────
    # [D] Results Grid (全寬)
    # ─────────────────────────────────────────────
    st.markdown('<div class="section-box">', unsafe_allow_html=True)
    st.markdown(f'<div class="result-chip">🎯 找到 {len(filtered)} 筆配方</div>', unsafe_allow_html=True)
    
    if len(filtered) == 0:
        st.warning("無符合結果。", icon="⚠️")
        selected_items = []
    else:
        df = pd.DataFrame(filtered)
        display_cols = ["rubber_type", "printed_page", "page", "title", "supplier", "hardness", "tensile_strength", "elongation"]
        existing_cols = [c for c in display_cols if c in df.columns]
        display_df = df[existing_cols].copy()
        
        rename_map = {"rubber_type": "Type", "page": "PDF Page", "printed_page": "Book Page", "title": "Title", "supplier": "Supplier", "hardness": "Hardness", "tensile_strength": "TS (MPa)", "elongation": "Elong (%)"}
        display_df.rename(columns=rename_map, inplace=True)
        
        event = st.dataframe(display_df, use_container_width=True, hide_index=True, height=450, on_select="rerun", selection_mode="multi-row")
        selected_rows = event.selection.rows
        selected_items = [filtered[i] for i in selected_rows] if selected_rows else []
    st.markdown('</div>', unsafe_allow_html=True)

    # ─────────────────────────────────────────────
    # [F] & [E] (垂直排序於下方)
    # ─────────────────────────────────────────────
    if not selected_items:
        st.markdown('<div class="section-box" style="text-align:center; padding:60px 20px;"><div style="font-size:3rem">📋</div><div style="margin-top:10px;">請從上方表格中勾選配方以顯示預覽區域</div></div>', unsafe_allow_html=True)
    else:
        # [F] PDF Viewport (全寬預覽)
        st.markdown('<div class="section-box">', unsafe_allow_html=True)
        col_f1, col_f2, col_f3 = st.columns([3, 1, 5])
        with col_f1:
            st.markdown(f"### 📄 頁面預覽 (已選 {len(selected_items)} 頁)")
        with col_f3:
            zoom_options = ["完整 A4 (符合頁面)", "符合頁寬", "原始高畫質放大"]
            if hasattr(st, "segmented_control"):
                zoom_mode = st.segmented_control("檢視選項", zoom_options, default="完整 A4 (符合頁面)", label_visibility="collapsed")
            else:
                zoom_mode = st.radio("檢視選項", zoom_options, horizontal=True, label_visibility="collapsed")
            if not zoom_mode: zoom_mode = "完整 A4 (符合頁面)"
            
        st.markdown("---")
        with st.container(height=900):
            for i, item in enumerate(selected_items):
                rtype = item.get("rubber_type", "EPDM")
                pnum = int(item.get("page", 1))
                st.markdown(f"**#{i+1} [{rtype}] {item.get('title','')}** (Page {pnum})")
                render_pdf_page_html(rtype, pnum, zoom_mode)
                st.markdown("---")
        st.markdown('</div>', unsafe_allow_html=True)

        # [E] Export Hub (置底下載)
        st.markdown('<div class="section-box">', unsafe_allow_html=True)
        st.markdown("### 📥 匯出選取的頁面")
        c_fn, c_btn = st.columns([3, 1])
        with c_fn:
            r_set = list(set([i.get("rubber_type","") for i in selected_items]))
            r_str = r_set[0].lower() if len(r_set) == 1 else "rubber"
            h_vals = [str(int(i["hardness"])) for i in selected_items if i.get("hardness") is not None]
            h_str = f"{h_vals[0]}" if len(set(h_vals)) == 1 else ""
            title_str = f"_{selected_items[0]['title']}" if len(selected_items) == 1 else ""
            date_str = datetime.now().strftime("%Y%m%d")
            default_fn = f"{r_str}{h_str}{title_str}_{date_str}.pdf".replace(" ", "_")
            final_fn = st.text_input("存檔名稱設定", value=default_fn)
        with c_btn:
            st.markdown('<div style="margin-top:28px"></div>', unsafe_allow_html=True)
            if st.button(f"🚀 合併並下載 PDF"):
                pdf_bytes = export_merged_pdf(selected_items)
                st.download_button("💾 點擊下載", data=pdf_bytes, file_name=final_fn, mime="application/pdf", use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)

if __name__ == "__main__":
    main()
