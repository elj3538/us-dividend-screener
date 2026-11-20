"""WikipediaからS&P Composite 1500（500+400+600）構成銘柄および配当王・配当貴族リストを取得するモジュール。"""

from __future__ import annotations

import json
import logging
from io import StringIO
from pathlib import Path
from typing import Any

import pandas as pd
import requests

logger = logging.getLogger(__name__)

WIKIPEDIA_URLS = [
    ("S&P 500", "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"),
    ("S&P 400", "https://en.wikipedia.org/wiki/List_of_S%26P_400_companies"),
    ("S&P 600", "https://en.wikipedia.org/wiki/List_of_S%26P_600_companies"),
]
WIKIPEDIA_ARISTOCRATS_URL = "https://en.wikipedia.org/wiki/S%26P_500_Dividend_Aristocrats"

SECTOR_EN_TO_JA: dict[str, str] = {
    "Information Technology": "情報技術",
    "Health Care": "ヘルスケア",
    "Consumer Discretionary": "一般消費財",
    "Consumer Staples": "生活必需品",
    "Communication Services": "コミュニケーション",
    "Industrials": "資本財",
    "Energy": "エネルギー",
    "Utilities": "公益事業",
    "Materials": "素材",
    "Financials": "金融",
    "Real Estate": "不動産",
}

SECTOR_ORDER: list[str] = list(SECTOR_EN_TO_JA.values())

# 配当王（50年以上連続増配の代表的な米国上場銘柄）
DIVIDEND_KINGS: set[str] = {
    "ABM", "ABBV", "ABT", "ADM", "AWR", "BKH", "CWT", "CBSH", "CINF", "CL",
    "DOV", "EMR", "FRT", "FTS", "GPC", "GWW", "HRL", "ITW", "JNJ", "KMB",
    "KO", "LANC", "LOW", "MGEE", "MO", "MSA", "MSEX", "NDSN", "NFG", "NUE",
    "NWN", "PEP", "PG", "PH", "PPG", "RPM", "SJW", "SYY", "TGT", "TR",
    "UVV", "WMT", "SCL", "SWK", "SYK", "ADP", "BDX", "CAH", "CTAS", "ED",
    "FAST", "GD", "IBM", "K", "LIN", "MKC", "O", "PNR", "SHW", "SPGI",
}

# 配当貴族フォールバック（Wikipedia取得失敗時用）
FALLBACK_ARISTOCRATS: set[str] = {
    "ABBV", "ABT", "ADM", "ADP", "AFL", "ALB", "AMCR", "AOS", "APD", "ATO",
    "BDX", "BF.B", "BRO", "CAH", "CAT", "CB", "CHD", "CHRW", "CINF", "CL",
    "CLX", "CTAS", "CVX", "DOV", "ECL", "ED", "EMR", "ESS", "EXPD", "FAST",
    "FRT", "GD", "GPC", "GWW", "HRL", "IBM", "ITW", "JNJ", "KMB", "KO",
    "LIN", "LOW", "MCD", "MDT", "MKC", "NEE", "NUE", "O", "PEP", "PG",
    "PNR", "PPG", "ROP", "SHW", "SJM", "SPGI", "SWK", "SYY", "TROW", "TGT",
    "WMT", "WST", "XOM",
}

# オフライン・テスト用フォールバック（主要配当株）
FALLBACK_CONSTITUENTS: list[dict[str, Any]] = [
    {"symbol": "JNJ", "yf_symbol": "JNJ", "name": "Johnson & Johnson", "sector_en": "Health Care", "sector_ja": "ヘルスケア", "sub_industry": "Pharmaceuticals", "index_group": "S&P 500"},
    {"symbol": "PG", "yf_symbol": "PG", "name": "Procter & Gamble", "sector_en": "Consumer Staples", "sector_ja": "生活必需品", "sub_industry": "Personal Care Products", "index_group": "S&P 500"},
    {"symbol": "KO", "yf_symbol": "KO", "name": "Coca-Cola Company (The)", "sector_en": "Consumer Staples", "sector_ja": "生活必需品", "sub_industry": "Soft Drinks & Non-alcoholic Beverages", "index_group": "S&P 500"},
    {"symbol": "PEP", "yf_symbol": "PEP", "name": "PepsiCo", "sector_en": "Consumer Staples", "sector_ja": "生活必需品", "sub_industry": "Soft Drinks & Non-alcoholic Beverages", "index_group": "S&P 500"},
    {"symbol": "ABBV", "yf_symbol": "ABBV", "name": "AbbVie", "sector_en": "Health Care", "sector_ja": "ヘルスケア", "sub_industry": "Biotechnology", "index_group": "S&P 500"},
    {"symbol": "XOM", "yf_symbol": "XOM", "name": "ExxonMobil", "sector_en": "Energy", "sector_ja": "エネルギー", "sub_industry": "Integrated Oil & Gas", "index_group": "S&P 500"},
    {"symbol": "CVX", "yf_symbol": "CVX", "name": "Chevron Corporation", "sector_en": "Energy", "sector_ja": "エネルギー", "sub_industry": "Integrated Oil & Gas", "index_group": "S&P 500"},
    {"symbol": "NEE", "yf_symbol": "NEE", "name": "NextEra Energy", "sector_en": "Utilities", "sector_ja": "公益事業", "sub_industry": "Multi-Utilities", "index_group": "S&P 500"},
    {"symbol": "MCD", "yf_symbol": "MCD", "name": "McDonald's", "sector_en": "Consumer Discretionary", "sector_ja": "一般消費財", "sub_industry": "Restaurants", "index_group": "S&P 500"},
    {"symbol": "LOW", "yf_symbol": "LOW", "name": "Lowe's", "sector_en": "Consumer Discretionary", "sector_ja": "一般消費財", "sub_industry": "Home Improvement Retail", "index_group": "S&P 500"},
    {"symbol": "CAT", "yf_symbol": "CAT", "name": "Caterpillar Inc.", "sector_en": "Industrials", "sector_ja": "資本財", "sub_industry": "Construction Machinery & Heavy Transportation Equipment", "index_group": "S&P 500"},
    {"symbol": "ITW", "yf_symbol": "ITW", "name": "Illinois Tool Works", "sector_en": "Industrials", "sector_ja": "資本財", "sub_industry": "Industrial Machinery & Supplies & Components", "index_group": "S&P 500"},
    {"symbol": "IBM", "yf_symbol": "IBM", "name": "IBM", "sector_en": "Information Technology", "sector_ja": "情報技術", "sub_industry": "IT Consulting & Other Services", "index_group": "S&P 500"},
    {"symbol": "TXN", "yf_symbol": "TXN", "name": "Texas Instruments", "sector_en": "Information Technology", "sector_ja": "情報技術", "sub_industry": "Semiconductors", "index_group": "S&P 500"},
    {"symbol": "JPM", "yf_symbol": "JPM", "name": "JPMorgan Chase", "sector_en": "Financials", "sector_ja": "金融", "sub_industry": "Diversified Banks", "index_group": "S&P 500"},
    {"symbol": "AFL", "yf_symbol": "AFL", "name": "Aflac", "sector_en": "Financials", "sector_ja": "金融", "sub_industry": "Life & Health Insurance", "index_group": "S&P 500"},
    {"symbol": "O", "yf_symbol": "O", "name": "Realty Income", "sector_en": "Real Estate", "sector_ja": "不動産", "sub_industry": "Retail REITs", "index_group": "S&P 500"},
    {"symbol": "LIN", "yf_symbol": "LIN", "name": "Linde plc", "sector_en": "Materials", "sector_ja": "素材", "sub_industry": "Industrial Gases", "index_group": "S&P 500"},
    {"symbol": "VZ", "yf_symbol": "VZ", "name": "Verizon", "sector_en": "Communication Services", "sector_ja": "コミュニケーション", "sub_industry": "Integrated Telecommunication Services", "index_group": "S&P 500"},
    {"symbol": "ADP", "yf_symbol": "ADP", "name": "Automatic Data Processing", "sector_en": "Industrials", "sector_ja": "資本財", "sub_industry": "Human Resource & Employment Services", "index_group": "S&P 500"},
]

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
}


def to_yf_symbol(symbol: str) -> str:
    """Wikipedia表記（BRK.B等）をyfinance表記（BRK-B等）に変換する。"""
    return symbol.strip().replace(".", "-")


def _fetch_aristocrats_set() -> set[str]:
    """WikipediaからS&P 500配当貴族リストを取得する。"""
    try:
        resp = requests.get(WIKIPEDIA_ARISTOCRATS_URL, headers=_HEADERS, timeout=20)
        resp.raise_for_status()
        tables = pd.read_html(StringIO(resp.text))
        for tbl in tables:
            cols = [str(c).strip() for c in tbl.columns]
            sym_col = next((c for c in cols if "Ticker" in c or "Symbol" in c), None)
            if sym_col and len(tbl) >= 40:
                syms = {str(v).strip() for v in tbl[sym_col].dropna() if str(v).strip()}
                if len(syms) >= 40:
                    logger.info("Wikipediaから配当貴族 %d 銘柄を取得しました。", len(syms))
                    return syms
    except Exception as exc:
        logger.warning("配当貴族リストの取得に失敗（フォールバック使用）: %s", exc)
    return set(FALLBACK_ARISTOCRATS)


def _parse_sp_table(df: pd.DataFrame, index_group: str) -> list[dict[str, Any]]:
    """WikipediaのS&P構成銘柄テーブルを正規化する。"""
    cols = {str(c).strip(): c for c in df.columns}
    sym_col = next((cols[k] for k in cols if k in ("Symbol", "Ticker symbol", "Ticker")), None)
    name_col = next((cols[k] for k in cols if k in ("Security", "Company")), None)
    sec_col = next((cols[k] for k in cols if "GICS Sector" in k or k == "Sector"), None)
    sub_col = next((cols[k] for k in cols if "Sub-Industry" in k), None)
    if sym_col is None:
        return []

    rows: list[dict[str, Any]] = []
    for _, row in df.iterrows():
        symbol = str(row.get(sym_col, "")).strip()
        if not symbol or symbol == "nan":
            continue
        sector_en = str(row.get(sec_col, "")).strip() if sec_col else ""
        rows.append(
            {
                "symbol": symbol,
                "yf_symbol": to_yf_symbol(symbol),
                "name": str(row.get(name_col, symbol)).strip() if name_col else symbol,
                "sector_en": sector_en,
                "sector_ja": SECTOR_EN_TO_JA.get(sector_en, sector_en or "その他"),
                "sub_industry": str(row.get(sub_col, "")).strip() if sub_col else "",
                "index_group": index_group,
            }
        )
    return rows


def fetch_sp1500_constituents(
    cache_dir: Path | None = None,
    use_cache: bool = True,
    limit: int | None = None,
    sp500_only: bool = False,
) -> list[dict[str, Any]]:
    """S&P Composite 1500（500+400+600）構成銘柄リストを取得し、配当王・配当貴族フラグを付与する。"""
    cache_name = "sp500_constituents.json" if sp500_only else "sp1500_constituents.json"
    cache_file = cache_dir / cache_name if cache_dir else None

    if use_cache and cache_file and cache_file.exists():
        logger.info("キャッシュから構成銘柄を読み込みます: %s", cache_file)
        items = json.loads(cache_file.read_text(encoding="utf-8"))
        return items[:limit] if limit else items

    aristocrats = _fetch_aristocrats_set()
    seen: set[str] = set()
    items: list[dict[str, Any]] = []

    target_urls = WIKIPEDIA_URLS[:1] if sp500_only else WIKIPEDIA_URLS
    for index_group, url in target_urls:
        try:
            resp = requests.get(url, headers=_HEADERS, timeout=20)
            resp.raise_for_status()
            tables = pd.read_html(StringIO(resp.text))
            parsed = _parse_sp_table(tables[0], index_group)
            added = 0
            for item in parsed:
                sym = item["symbol"]
                if sym in seen:
                    continue
                seen.add(sym)
                item["is_king"] = sym in DIVIDEND_KINGS
                item["is_aristocrat"] = sym in aristocrats
                items.append(item)
                added += 1
            logger.info("%s: %d 銘柄を取得しました。", index_group, added)
        except Exception as exc:
            logger.warning("%s の取得に失敗しました: %s", index_group, exc)

    if not items:
        logger.warning("Wikipediaからの取得に失敗したためフォールバックを使用します。")
        for fb in FALLBACK_CONSTITUENTS:
            item = dict(fb)
            item["is_king"] = item["symbol"] in DIVIDEND_KINGS
            item["is_aristocrat"] = item["symbol"] in aristocrats
            items.append(item)

    if cache_file and items:
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")

    return items[:limit] if limit else items
