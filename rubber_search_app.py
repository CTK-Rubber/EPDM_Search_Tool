#!/usr/bin/env python3
"""
橡膠配方規格篩選系統
- 勾選要篩選的規格（Hardness / Tensile Strength / Elongation / 100% Modulus / 300% Modulus / Compression Set / Specific Gravity）
- 每項可設「下限」、「上限」或「範圍」
- 篩選結果以清單顯示，點選後右側嵌入 PDF 並自動跳到對應頁面
"""

from __future__ import annotations

import base64
import json
import subprocess
import sys
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

# ─────────────────────────────────────────────
BASE_DIR   = Path(__file__).resolve().parent
JSON_PATH  = BASE_DIR / "formulary_data.json"
PDF_PATH   = BASE_DIR / "Rubber Formulary EPDM.pdf"
PARSE_SCRIPT = BASE_DIR / "parse_to_json.py"

# ─────────────────────────────────────────────
# 欄位設定（顯示名稱、單位、資料鍵）
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

/* Page background */
.stApp {
    background: linear-gradient(135deg, #0f0c29 0%, #302b63 50%, #24243e 100%);
    min-height: 100vh;
}

/* Sidebar */
section[data-testid="stSidebar"] {
    background: rgba(15, 12, 41, 0.95) !important;
    border-right: 1px solid rgba(255,255,255,0.08);
}
section[data-testid="stSidebar"] * {
    color: #e2e8f0 !important;
}

/* Main title */
h1 {
    background: linear-gradient(90deg, #a78bfa, #60a5fa, #34d399);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    font-size: 2.2rem !important;
    font-weight: 700;
    letter-spacing: -0.5px;
}

/* Cards */
.formula-card {
    background: rgba(255,255,255,0.05);
    border: 1px solid rgba(255,255,255,0.10);
    border-radius: 12px;
    padding: 14px 18px;
    margin-bottom: 10px;
    cursor: pointer;
    transition: all 0.2s ease;
    backdrop-filter: blur(8px);
}
.formula-card:hover {
    border-color: rgba(167,139,250,0.5);
    background: rgba(167,139,250,0.08);
    transform: translateY(-1px);
    box-shadow: 0 8px 30px rgba(167,139,250,0.2);
}
.formula-card.selected {
    border-color: #a78bfa;
    background: rgba(167,139,250,0.15);
    box-shadow: 0 0 0 2px rgba(167,139,250,0.3);
}

/* Spec badge */
.spec-badge {
    display: inline-block;
    background: rgba(96,165,250,0.15);
    border: 1px solid rgba(96,165,250,0.3);
    border-radius: 6px;
    padding: 2px 8px;
    font-size: 0.72rem;
    color: #93c5fd !important;
    margin-right: 5px;
    margin-top: 4px;
    white-space: nowrap;
}

/* Filter section header */
.filter-header {
    font-size: 0.70rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 1.5px;
    color: #94a3b8 !important;
    margin-bottom: 8px;
    margin-top: 16px;
}

/* Metric boxes */
.metric-grid {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin-top: 6px;
}
.metric-box {
    background: rgba(255,255,255,0.06);
    border: 1px solid rgba(255,255,255,0.10);
    border-radius: 8px;
    padding: 8px 14px;
    text-align: center;
    min-width: 90px;
}
.metric-label { font-size: 0.62rem; color:#94a3b8; text-transform:uppercase; letter-spacing:0.8px; }
.metric-value { font-size: 1.1rem; font-weight:600; color:#e2e8f0; }
.metric-unit  { font-size: 0.65rem; color:#6b7280; }

/* Result count chip */
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

/* Streamlit button override */
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

/* Checkbox and radio color */
.stCheckbox label, .stRadio label { color: #e2e8f0 !important; }

/* Scrollable result list */
.result-scroll {
    max-height: 65vh;
    overflow-y: auto;
    padding-right: 4px;
}

/* Divider */
hr { border-color: rgba(255,255,255,0.08) !important; }

/* Number input */
div[data-testid="stNumberInput"] input {
    background: rgba(255,255,255,0.06) !important;
    border: 1px solid rgba(255,255,255,0.15) !important;
    color: #e2e8f0 !important;
    border-radius: 6px;
}

/* Info/warning */
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
    """載入 formulary_data.json；若不存在則自動執行解析腳本。"""
    if not JSON_PATH.exists():
        if PARSE_SCRIPT.exists():
            subprocess.run([sys.executable, str(PARSE_SCRIPT)], check=True)
        else:
            return []
    return json.loads(JSON_PATH.read_text(encoding="utf-8"))


@st.cache_data(show_spinner=False)
def get_pdf_b64() -> str | None:
    if not PDF_PATH.exists():
        return None
    return base64.standard_b64encode(PDF_PATH.read_bytes()).decode("ascii")


# ─────────────────────────────────────────────
# Filtering
# ─────────────────────────────────────────────

def apply_filters(records: list[dict], active_filters: dict) -> list[dict]:
    """
    active_filters = {
        "hardness": {"mode": "Min (≥)", "lo": 60, "hi": None},
        ...
    }
    """
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


import pandas as pd
import os
import time
import streamlit.components.v1 as components

# ─────────────────────────────────────────────
# UI helpers
# ─────────────────────────────────────────────

def render_pdf(page: int, b64: str) -> None:
    # 解決雲端版 (Streamlit Cloud) 點選後畫面不更新的問題
    # 透過 st.markdown 直接注入 embed 標籤，並給予一個隨機 ID 讓瀏覽器強迫重繪
    ts = time.time()
    src = f"data:application/pdf;base64,{b64}#page={page}"
    
    html = f"""
    <div id="pdf-view-container-{ts}" style="width:100%; height:800px;">
        <embed src="{src}" type="application/pdf" width="100%" height="800px" style="border:none; border-radius:10px; box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1);" />
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)


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
    pdf_b64 = get_pdf_b64()

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
        # Re-parse button - Only show if not on the cloud (simple check)
        is_cloud = os.environ.get("HOME") == "/home/appuser"
        if not is_cloud:
            if st.button("🔄 重新解析文字庫 (本機專用)", use_container_width=True):
                if PARSE_SCRIPT.exists():
                    with st.spinner("解析中…"):
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
        st.caption("從 Rubber Formulary EPDM 中依規格快速篩選配方 · 點選結果會自動顯示對應的 PDF 頁面")

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
            # 轉換資料成 DataFrame 以表格呈現
            df = pd.DataFrame(filtered)
            
            # 定義顯示欄位
            display_cols = [
                "printed_page", "page", "title", "supplier", "hardness", "tensile_strength", 
                "elongation", "modulus_100", "modulus_300", "compression_set", "specific_gravity"
            ]
            
            # 確保欄位存在
            existing_cols = [c for c in display_cols if c in df.columns]
            display_df = df[existing_cols].copy()
            
            # 重新命名欄位名稱使其更具可讀性
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
            
            st.caption("👈 點擊表格左側核取方塊以查看對應 PDF 頁面")

            # 顯示 dataframe 並啟用單行選取功能
            event = st.dataframe(
                display_df,
                use_container_width=True,
                hide_index=True,
                height=600,
                on_select="rerun",
                selection_mode="single-row"
            )
            
            # 檢查選取狀態
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
                        請從左側表格中點選配方以預覽 PDF
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
                        PDF 預覽
                    </span>
                    <div style='font-size:1rem;font-weight:600;color:#e2e8f0;margin-top:2px;'>{title}</div>
                    <span style='font-size:0.75rem;color:#a78bfa;'>→ 跳至第 {page} 頁</span>
                </div>
                """,
                unsafe_allow_html=True,
            )

            if pdf_b64 is None:
                st.error(f"找不到 PDF 檔案：{PDF_PATH}", icon="🚫")
                st.info(f"請確認 PDF 位於：`{PDF_PATH}`")
            else:
                render_pdf(page, pdf_b64)


if __name__ == "__main__":
    main()
