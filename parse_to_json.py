#!/usr/bin/env python3
"""
parse_to_json.py  (v2 – 支援多欄配方)
功能：
  - 解析 all_formularies_text.txt → JSON
  - 偵測同頁含多個欄位（ex: 55 Shore A / 65 Shore A）
  - 每個獨立欄位值各自產生一筆記錄
  - tensile_strength 自動換算 psi / kg·cm² → MPa
"""

from __future__ import annotations

import re
import json
from pathlib import Path

TXT_PATH = Path(__file__).parent / "all_formularies_text.txt"
OUT_PATH = Path(__file__).parent / "formulary_data.json"


# ──────────────────────────────────────────────
# 輔助：抓取一行中所有數值
# ──────────────────────────────────────────────


def clean_and_get_nums(text: str) -> list[float]:
    """清除標籤內的干擾數字（如 200%, 22 Hrs, 70C），再抓取剩餘數值。"""
    t = text
    # 移除 ASTM 測試標準，例如 D 412, D-395, D2240
    t = re.sub(r"\b(?:ASTM\s*)?D\s*-?\s*\d{3,4}(?:-\d+)?\b", "", t, flags=re.IGNORECASE)
    # 移除括號內的純數字或帶逗號小數點數字 (通常是 psi)
    t = re.sub(r"\(\s*\d[\d,\.]*\s*\)", "", t)
    # 移除 min/max 及其前面的數字 (過濾 spec 值)
    t = re.sub(r"\b\d[\d,\.]*(?:\.\d+)?\s*(?:min|max)\.?", "", t, flags=re.IGNORECASE)
    # 移除大於小於符號帶數字 (過濾 spec 值)
    t = re.sub(r"[><=]\s*\d[\d,\.]*(?:\.\d+)?", "", t)
    # 移除範圍數字 (ex: 55-75)
    t = re.sub(r"\b\d[\d,\.]*(?:\.\d+)?\s*-\s*\d[\d,\.]*(?:\.\d+)?\b", "", t)

    t = re.sub(r"\b(100|200|300|400|500)\s*%", "", t)
    t = re.sub(
        r"\b\d+\s*(?:Hrs?\.?|Hours?|C|°C|°|days?|weeks?|mins?|minutes?|kilocycles?|kc)\b",
        "",
        t,
        flags=re.IGNORECASE,
    )

    # 不提取負號（除非是溫度，但物理性質不為負），避免提取到範圍的後半部 -75 -> -75.0
    return [float(m.replace(",", "")) for m in re.findall(r"\d[\d,]*(?:\.\d+)?", t)]


# ──────────────────────────────────────────────
# 欄位 Regex 定義
#   每個 pattern 要能搜到整行，後面的數值可能有一或多個
# ──────────────────────────────────────────────

FIELD_PATTERNS = {
    "hardness": re.compile(
        r"(?:Shore\s+A\s+Hardness|Hardness[,\s]+(?:Shore\s+A|Pts?\.?\s+Change)?)[:\-]?\s*([^\n]+)",
        re.IGNORECASE,
    ),
    "tensile_strength": re.compile(
        r"(?:Tensile(?:\s+Strength)?|T[-\.]B|T\.S\.)\s*[,\-]?\s*(?:MPa|psi|kg[/\s]?cm[²2]?)[\s:]*([^\n]+)",
        re.IGNORECASE,
    ),
    "elongation": re.compile(
        r"(?:Elongation|Elong\.?|E[-\.]B)(?:\s+(?:at\s+Break|@\s*Break|,?\s*%))?[,\s\-]+%?[\s]*([^\n]+)",
        re.IGNORECASE,
    ),
    "modulus_100": re.compile(
        r"(?:100%|M[-_]?100|Modulus\s+@?\s*100%)\s*(?:Modulus)?[,\-]?\s*(?:MPa|psi|kg[/\s]?cm[²2]?)?[\s:]*([^\n]+)",
        re.IGNORECASE,
    ),
    "modulus_300": re.compile(
        r"(?:300%|M[-_]?300|Modulus\s+@?\s*300%)\s*(?:Modulus)?[,\-]?\s*(?:MPa|psi|kg[/\s]?cm[²2]?)?[\s:]*([^\n]+)",
        re.IGNORECASE,
    ),
    "compression_set": re.compile(
        r"Compression\s+Set[^\n]{0,60}?([^\n]+)",
        re.IGNORECASE | re.MULTILINE,
    ),
    "specific_gravity": re.compile(
        r"(?:Specific\s+Gravity|Density(?:,\s*Mg/m3)?)\s*[:\-]?\s*([^\n]+)",
        re.IGNORECASE,
    ),
}

# 判斷張力是 psi 還是 kg/cm² 才需換算
TENSILE_UNIT_RE = re.compile(
    r"(?:Tensile(?:\s+Strength)?|T[-\.]B|T\.S\.)\s*[,\-]?\s*(MPa|psi|kg[/\s]?cm[²2]?)",
    re.IGNORECASE,
)


def _tensile_factor(page_text: str) -> float:
    """取得頁面 tensile 的換算因子（到 MPa）。"""
    m = TENSILE_UNIT_RE.search(page_text)
    if not m:
        return 1.0
    unit = m.group(1).lower().strip()
    if "psi" in unit:
        return 0.006895
    if "kg" in unit:
        return 0.0981
    return 1.0


def _modulus_factor(page_text: str) -> float:
    """取得 modulus 的換算因子（到 MPa）。"""
    # 找 300% or 100% Modulus 那行的單位
    m = re.search(
        r"(?:300%|100%|Modulus)[^\n]*?(MPa|psi|kg[/\s]?cm[²2]?)",
        page_text,
        re.IGNORECASE,
    )
    if not m:
        return 1.0
    unit = m.group(1).lower().strip()
    if "psi" in unit:
        return 0.006895
    if "kg" in unit:
        return 0.0981
    return 1.0


def extract_hardness_durometer_from_text(
    text: str,
) -> tuple[float | None, float | None]:
    """從文字找 hardness / durometer 值（兼容字首/字尾寫法）。"""
    if not text:
        return None, None

    hardness = None
    durometer = None

    # 先找 durometer-centric
    m = re.search(r"(?i)\bdurometer\s*[:\-]?\s*([0-9]{1,3})\b", text)
    if m:
        durometer = float(m.group(1))
    else:
        m = re.search(r"(?i)\b([0-9]{1,3})\s*durometer\b", text)
        if m:
            durometer = float(m.group(1))

    # 同步提取 hardness-from-text（hardness/shore A）
    m = re.search(r"(?i)\bhardness\s*[:\-]?\s*([0-9]{1,3})\b", text)
    if m:
        hardness = float(m.group(1))
    else:
        m = re.search(r"(?i)\b([0-9]{1,3})\s*shore\s*A\b", text)
        if m:
            hardness = float(m.group(1))

    return hardness, durometer


# ──────────────────────────────────────────────
# 從段落抓取各欄位的「全部數值」（多欄支援）
# ──────────────────────────────────────────────


def extract_all_values(key: str, page_text: str) -> list[float | None]:
    """
    回傳一個 list，含每個欄位的數值（可能有多個，對應多欄配方）。
    例如 Hardness 53 64 → [53.0, 64.0]
    若找不到則回傳 [None]。
    """
    pat = FIELD_PATTERNS.get(key)
    if not pat:
        return [None]

    m = pat.search(page_text)
    if not m:
        return [None]

    raw = m.group(1).strip()
    nums = clean_and_get_nums(raw)
    if not nums:
        return [None]

    # 換算
    factor = 1.0
    if key == "tensile_strength":
        factor = _tensile_factor(page_text)
    elif key in ("modulus_100", "modulus_300"):
        factor = _modulus_factor(page_text)

    return [round(n * factor, 4) for n in nums]


# ──────────────────────────────────────────────
# title / supplier 解析
# ──────────────────────────────────────────────

SKIP_WORDS = {
    "THE RUBBER FORMULARY",
    "EPDM",
    "ACM",
    "CR",
    "NBR",
    "NR",
    "SBR",
    "BR",
    "IIR",
    "CONTINUED",
    "CONTINUE",
    "CONTENTS",
    "APPENDIX",
    "FORMULARY",
}

KNOWN_SUPPLIERS = [
    "DSM",
    "R.T. Vanderbilt",
    "Uniroyal",
    "DuPont",
    "Dow",
    "Enichem",
    "Union Carbide",
    "Goodyear",
    "Monsanto",
    "Bayer",
    "Shell",
    "Harwick",
    "Columbian",
    "R&H",
    "Rohm",
    "Akzo",
    "Hercules",
]


def extract_title_supplier(lines: list[str]) -> tuple[str, str, str]:
    clean = [l.strip() for l in lines[:15] if l.strip()]

    printed_page = ""
    if clean and re.fullmatch(r"\d+", clean[0]):
        printed_page = clean[0]
        clean = clean[1:]

    title_parts: list[str] = []
    supplier = ""

    for c in clean:
        if c.upper() in SKIP_WORDS:
            continue
        if re.search(r"^[\d\s]+$", c) or re.search(r"\d+\.\d+", c):
            break
        if re.search(r"\d+$", c) and len(c) > 10:
            break
        if c.upper() in ["INGREDIENTS", "PHYSICAL PROPERTIES", "PROPERTIES"]:
            break
        # Skip header rows like "55 Shore A  65 Shore A"
        if re.search(r"\d+\s+Shore\s+A", c, re.IGNORECASE):
            break
        title_parts.append(c)

    if title_parts:
        last = title_parts[-1]
        is_supplier = False
        if any(ks.lower() in last.lower() for ks in KNOWN_SUPPLIERS) and not any(
            w in last.upper() for w in ["COMPOUND", "HOSE"]
        ):
            is_supplier = True
        elif (
            not last.isupper()
            and len(last) < 25
            and not any(w in last.upper() for w in ["HOSE", "COMPOUND", "MASTERBATCH"])
        ):
            is_supplier = True

        if is_supplier:
            supplier = title_parts.pop()

    title = " / ".join(title_parts) if title_parts else "Unknown"
    title = re.sub(r"(?i)\s*Uniroyal Masterbatch", "", title).strip()
    return title, supplier, printed_page


# ──────────────────────────────────────────────
# 主解析流程（多欄支援版）
# ──────────────────────────────────────────────

NUMERIC_FIELDS = [
    "hardness",
    "durometer",
    "tensile_strength",
    "elongation",
    "modulus_100",
    "modulus_300",
    "compression_set",
    "specific_gravity",
]


def parse_txt(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8")

    source_pattern = re.compile(r"### SOURCE: (.*?) ###")
    source_splits = source_pattern.split(text)

    records: list[dict] = []
    it_src = iter(source_splits)
    next(it_src, None)  # skip leading empty

    while True:
        try:
            rubber_type = next(it_src).strip()
            block_content = next(it_src)
        except StopIteration:
            break

        page_pattern = re.compile(r"--- Page (\d+) ---")
        page_splits = page_pattern.split(block_content)
        it_page = iter(page_splits)
        next(it_page, None)  # skip leading empty

        while True:
            try:
                page_str = next(it_page)
                page_text = next(it_page)
            except StopIteration:
                break

            page_num = int(page_str)
            lines = page_text.split("\n")
            title, supplier, printed_page = extract_title_supplier(lines)

            # 若 page_text 或 title 有「Durometer 65 / 90 DUROMETER / 70 Shore A」之類，補償性擷取
            hardness_from_title, durometer_from_title = (
                extract_hardness_durometer_from_text(page_text)
            )
            if hardness_from_title is None and durometer_from_title is None:
                title_hardness, title_durometer = extract_hardness_durometer_from_text(
                    title
                )
                if title_hardness is not None:
                    hardness_from_title = title_hardness
                if title_durometer is not None:
                    durometer_from_title = title_durometer

            # --- 多欄偵測：找出各欄位的數值列表，取最多欄數 ---
            field_values: dict[str, list] = {}
            max_cols = 1
            for key in NUMERIC_FIELDS:
                vals = extract_all_values(key, page_text)
                field_values[key] = vals
                if vals and vals[0] is not None:
                    max_cols = max(max_cols, len(vals))

            # --- 對每個欄產生一筆記錄 ---
            for col_idx in range(max_cols):
                rec: dict = {
                    "rubber_type": rubber_type,
                    "page": page_num,
                    "printed_page": printed_page,
                    "title": title,
                    "supplier": supplier,
                }
                for key in NUMERIC_FIELDS:
                    vals = field_values[key]
                    if col_idx < len(vals):
                        rec[key] = vals[col_idx]
                    elif len(vals) > 0 and vals[0] is not None:
                        # 如果只有一個值，所有欄共用（例如 Sp.Gr 通常只寫一次）
                        rec[key] = vals[0]
                    else:
                        rec[key] = None

                # 如果在頁面/標題找到 durometer，且資料欄無值，補上
                if rec.get("durometer") is None and durometer_from_title is not None:
                    rec["durometer"] = durometer_from_title

                # 如果在頁面/標題找到 hardness，且資料欄無值，補上
                if rec.get("hardness") is None and hardness_from_title is not None:
                    rec["hardness"] = hardness_from_title

                # 若難度仍缺失，則用 durometer 補硬度
                if rec.get("hardness") is None and rec.get("durometer") is not None:
                    rec["hardness"] = rec["durometer"]

                # 保留 durometer 欄位，並同步 hardness，讓 formulary_data.json 包含原始與補值欄位
                records.append(rec)

    return records


def main():
    records = parse_txt(TXT_PATH)

    # 依使用者要求，移除所有 ACM 膠種的資料
    records = [r for r in records if r.get("rubber_type") != "ACM"]

    OUT_PATH.write_text(
        json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"✅  解析完成，共 {len(records)} 筆記錄，輸出至 {OUT_PATH}")

    fields = NUMERIC_FIELDS
    for f in fields:
        count = sum(1 for r in records if r.get(f) is not None)
        print(f"  {f:20s}: {count}/{len(records)} ({100*count//len(records)}%)")

    hardness_filled = sum(1 for r in records if r.get("hardness") is not None)
    durometer_filled = sum(1 for r in records if r.get("durometer") is not None)
    both_filled = sum(
        1
        for r in records
        if r.get("hardness") is not None and r.get("durometer") is not None
    )
    print("\n🔎 num_records 統計 (補值/原始)：")
    print(f"  hardness 有值: {hardness_filled}/{len(records)}")
    print(f"  durometer 有值: {durometer_filled}/{len(records)}")
    print(f"  同時有兩個值: {both_filled}/{len(records)}")


if __name__ == "__main__":
    main()
