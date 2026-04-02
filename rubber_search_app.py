#!/usr/bin/env python3
"""
橡膠配方規格篩選系統
- 勾選要篩選的規格（Hardness / Tensile Strength / Elongation / 100% Modulus / 300% Modulus / Compression Set / Specific Gravity）
- 每項可設「下限」、「上限」或「範圍」
- 篩選結果以表格顯示，點選後右側渲染 PDF 頁面圖片以確保雲端版本相容性
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import streamlit as st
import pandas as pd
import pdfplumber
from PIL import Image

# ─────────────────────────────────────────────
# Path configuration
# ─────────────────────────────────────────────
BASE_DIR     = Path(__file__).resolve().parent
JSON_PATH    = BASE_DIR / "formulary_data.json"
PDF_PATH     = BASE_DIR / "Rubber Formulary EPDM.pdf"
PARSE_SCRIPT = BASE_DIR / "parse_to_json.py"

# ─────────────────────────────────────────────
# 欄位設定
# ─────────────────────────────────────────────
FIELDS = [
    {"key": "hardness",          "label": "Hardness",          "unit": "Shore A"},
    {"key": "tensile_strength",  "label": "Tensile Strength",  "unit": "MPa"},
    {"key": "elongation",        "label": "Elongation",        "unit": "%"},
    {"key": "modulus_100",       "label": "100% Modulus",      "unit": "MPa"},
    {"key": "modulus_300",       "label": "300% Modulus",      "unit": "MPa"},
    {"key": "compression_set",   "label": "Compression Set",   "unit": "%"},
    {"key": "specific_gravity",  "label": "Specific Gravity",  "unit": ""},
]

FILTER_MODES = ["Min (≥)", "Max (≤)", "Range (≥ and ≤)"]

# ─────────────────────────────────────────────
# CSS
# ─────────────────────────────────────────────
CUSTOM_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

html, body, [class*="css"] {
    font-family: 'Inter', sans-serif;
}

.stApp {
    background: linear-gradient(135deg, #0f0c29 0%, #302b63 50%, #24243e 100%);
    min-height: 100vh;
}

section[data-testid="stSidebar"] {
    background: rgba(15, 12, 41, 0.95) !important;
    border-right: 1px solid rgba(255,255,255,0.08);
}
section[data-testid="stSidebar"] * {
    color: #e2e8f0 !important;
}

h1 {
    background: linear-gradient(90deg, #a78bfa, #60a5fa, #34d399);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    font-size: 2.2rem !important;
    font-weight: 700;
    letter-spacing: -0.5px;
}

.filter-header {
    font-size: 0.70rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 1.5px;
    color: #94a3b8 !important;
    margin-bottom: 8px;
    margin-top: 16px;
}

.result-chip {
    display:inline-block;
    background: linear-gradient(90deg, #a78bfa22, #60a5fa22);
    border: 1px solid rgba(167,139,250,0.3);
    border-radius: 20px;
    padding: 4px 14px;
    font-size:.85rem;
    color:#a78bfa;
    font-weight:600;
    margin-bottom: 12px;
}

div.stButton > button {
    background: linear-gradient(90deg, #7c3aed, #2563eb) !important;
    color: white !important;
    border: none !important;
    border-radius: 8px !important;
    font-weight: 500 !important;
    transition: all 0.2s !important;
    width: 100%;
}
div.stButton > button:hover {
    opacity: 0.9;
    transform: translateY(-1px);
    box-shadow: 0 4px 15px rgba(124,58,237,0.4) !important;
}

.stCheckbox label, .stRadio label { color: #e2e8f0 !important; }

hr { border-color: rgba(255,255,255,0.08) !important; }

div[data-testid="stNumberInput"] input {
    background: rgba(255,255,255,0.06) !important;
    border: 1px solid rgba(255,255,255,0.15) !important;
    color: #e2e8f0 !important;
    border-radius: 6px;
}

.stAlert {
    border-radius: 10px !important;
}
</style>
"""

# ─────────────────────────────────────────────
# Data Loading
# ─────────────────────────────────────────────

@st.cache_data(show_spinner=False)
def load_data() -> list[dict]:
    if not JSON_PATH.exists():
        return []
    try:
        return json.loads(JSON_PATH.read_text(encoding="utf-8"))
    except Exception:
        return []

@st.cache_resource
def get_pdf_doc():
    """使用 pdfplumber 開啟並快取 PDF 文件對象"""
    if PDF_PATH.exists():
        return pdfplumber.open(PDF_PATH)
    return None

# ─────────────────────────────────────────────
# Filtering
# ─────────────────────────────────────────────

def apply_filters(records: list[dict], active_filters: dict) -> list[dict]:
    out = []
    for rec in records:
        pass_all = True
        for key, cfg in active_filters.items():
            val = rec.get(key)
            if val is None:
                pass_all = False
                break
            mode = cfg["mode"]
            lo, hi = cfg["lo"], cfg["hi"]
            if mode == "Min (≥)" and lo is not None and val < lo:
                pass_all = False; break
            if mode == "Max (≤)" and hi is not None and val > hi:
                pass_all = False; break
            if mode == "Range (≥ and ≤)":
                if lo is not None and val < lo:
                    pass_all = False; break
                if hi is not None and val > hi:
                    pass_all = False; break
        if pass_all:
            out.append(rec)
    return out

# ─────────────────────────────────────────────
# UI helpers
# ─────────────────────────────────────────────

def render_pdf(page_num: int) -> None:
    """
    將 PDF 的特定頁面渲染為圖片並顯示。
    解決雲端版 (Streamlit Cloud) 的 iframe 安全限制問題。
    """
    doc = get_pdf_doc()
    if doc is None:
        st.error(f"找不到 PDF 檔案：{PDF_PATH.name}")
        return

    try:
        if page_num < 1 or page_num > len(doc.pages):
            st.error(f"頁碼 {page_num} 超出範圍 (總計 {len(doc.pages)} 頁)")
            return
            
        page = doc.pages[page_num - 1]
        
        with st.spinner(f"正在渲染第 {page_num} 頁..."):
            # 渲染為圖片 (解析度 150 適合瀏覽器閱讀)
            img = page.to_image(resolution=150).original
            
            # 顯示圖片
            st.image(
                img, 
                use_container_width=True, 
                caption=f"PDF 第 {page_num} 頁渲染圖 (來自 {PDF_PATH.name})",
                output_format="JPEG"
            )
            
            # 提供下載連結作為備案
            with open(PDF_PATH, "rb") as f:
                st.download_button(
                    label="💾 下載原始 PDF 存檔",
                    data=f,
                    file_name=PDF_PATH.name,
                    mime="application/pdf",
                    use_container_width=True
                )
    except Exception as e:
        st.error(f"渲染 PDF 發生錯誤: {e}")

# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

def main():
    st.set_page_config(
        page_title="橡膠配方規格篩選系統",
        page_icon="🔬",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

    # session state
    if "selected_page" not in st.session_state:
        st.session_state.selected_page = None
    if "selected_title" not in st.session_state:
        st.session_state.selected_title = ""

    records = load_data()

    # ── SIDEBAR ──────────────────────────────────
    with st.sidebar:
        st.markdown("## 🔬 規格篩選條件")
        st.markdown("---")
        st.markdown('<p class="filter-header">勾選要篩選的規格</p>', unsafe_allow_html=True)

        active_filters: dict = {}

        for field in FIELDS:
            key   = field["key"]
            label = field["label"]
            unit  = field["unit"]
            unit_str = f" ({unit})" if unit else ""

            enabled = st.checkbox(f"**{label}**{unit_str}", key=f"chk_{key}")

            if enabled:
                mode = st.radio(
                    "篩選方式",
                    FILTER_MODES,
                    key=f"mode_{key}",
                    horizontal=False,
                    label_visibility="collapsed",
                )

                lo, hi = None, None

                if mode in ("Min (≥)", "Range (≥ and ≤)"):
                    lo = st.number_input(
                        f"最小值{unit_str}",
                        value=0.0,
                        step=0.1 if key == "specific_gravity" else 1.0,
                        key=f"lo_{key}",
                        label_visibility="visible",
                    )

                if mode in ("Max (≤)", "Range (≥ and ≤)"):
                    hi = st.number_input(
                        f"最大值{unit_str}",
                        value=100.0,
                        step=0.1 if key == "specific_gravity" else 1.0,
                        key=f"hi_{key}",
                        label_visibility="visible",
                    )

                active_filters[key] = {"mode": mode, "lo": lo, "hi": hi}
                st.markdown("---")

        st.markdown("---")
        # 偵測是否為雲端環境
        is_cloud = os.environ.get("HOME") == "/home/appuser" or "STREAMLIT_RUNTIME_ENV" in os.environ
        if not is_cloud:
            if st.button("🔄 重新解析文字庫 (本機專用)", use_container_width=True):
                if PARSE_SCRIPT.exists():
                    with st.spinner("解析中…"):
                        import subprocess
                        import sys
                        subprocess.run([sys.executable, str(PARSE_SCRIPT)], check=True)
                    st.cache_data.clear()
                    st.success("解析完成！")
                    st.rerun()
                else:
                    st.error(f"找不到解析腳本：{PARSE_SCRIPT}")

    # ── MAIN AREA ────────────────────────────────
    col_title, _ = st.columns([3, 1])
    with col_title:
        st.title("🧪 橡膠配方規格篩選系統")
        st.caption("從 Rubber Formulary EPDM 中依規格快速篩選配方 · 點選結果會自動顯示對應的 PDF 頁面影像")

    st.markdown("---")

    # Apply filters
    if active_filters:
        filtered = apply_filters(records, active_filters)
    else:
        filtered = records

    col_list, col_pdf = st.columns([1, 1], gap="large")

    # ── LEFT: Result list ──
    with col_list:
        n = len(filtered)
        st.markdown(f'<div class="result-chip">🎯 找到 {n} 筆配方</div>', unsafe_allow_html=True)

        if n == 0:
            st.warning("目前篩選條件下無符合結果，請調整規格範圍。", icon="⚠️")
        else:
            df = pd.DataFrame(filtered)
            display_cols = [
                "printed_page", "page", "title", "supplier", "hardness", "tensile_strength", 
                "elongation", "modulus_100", "modulus_300", "compression_set", "specific_gravity"
            ]
            existing_cols = [c for c in display_cols if c in df.columns]
            display_df = df[existing_cols].copy()
            
            rename_map = {
                "page": "PDF Page", 
                "printed_page": "Book Page",
                "title": "Title", 
                "supplier": "Supplier", 
                "hardness": "Hardness (Shore A)", 
                "tensile_strength": "TS (MPa)", 
                "elongation": "Elong (%)", 
                "modulus_100": "100% Mod (MPa)", 
                "modulus_300": "300% Mod (MPa)", 
                "compression_set": "Comp. Set (%)", 
                "specific_gravity": "SG"
            }
            display_df.rename(columns=rename_map, inplace=True)
            
            st.caption("👈 點擊表格左側核取方塊以查看對應 PDF 頁面圖片")

            event = st.dataframe(
                display_df,
                use_container_width=True,
                hide_index=True,
                height=600,
                on_select="rerun",
                selection_mode="single-row"
            )
            
            selected_rows = event.selection.rows
            if selected_rows:
                selected_idx = selected_rows[0]
                st.session_state.selected_page = int(display_df.iloc[selected_idx]["PDF Page"])
                st.session_state.selected_title = str(display_df.iloc[selected_idx]["Title"])

    # ── RIGHT: PDF Preview ──
    with col_pdf:
        if st.session_state.selected_page is None:
            st.markdown(
                """
                <div style='text-align:center;padding:80px 20px;
                    background:rgba(255,255,255,0.03);border-radius:12px;
                    border:1px dashed rgba(255,255,255,0.12);height:500px;
                    display:flex;flex-direction:column;justify-content:center;align-items:center;'>
                    <div style='font-size:3.5rem'>📋</div>
                    <div style='color:#94a3b8;margin-top:16px;font-size:1rem;max-width:200px;text-align:center'>
                        請從左側表格中點選配方以預覽 PDF 影像
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        else:
            page  = st.session_state.selected_page
            title = st.session_state.selected_title
            st.markdown(
                f"""
                <div style='margin-bottom:10px;'>
                    <span style='font-size:0.65rem;color:#6b7280;text-transform:uppercase;letter-spacing:1px;'>
                        PDF 預覽 (影像渲染)
                    </span>
                    <div style='font-size:1rem;font-weight:600;color:#e2e8f0;margin-top:2px;'>{title}</div>
                    <span style='font-size:0.75rem;color:#a78bfa;'>→ 跳至第 {page} 頁</span>
                </div>
                """,
                unsafe_allow_html=True,
            )
            render_pdf(page)

if __name__ == "__main__":
    main()
