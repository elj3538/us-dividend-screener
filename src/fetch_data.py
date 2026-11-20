"""yfinanceから米国配当株の株価・配当履歴・財務・決算データを取得しスクリーニング＆キャッシュするモジュール。"""

from __future__ import annotations

import json
import logging
import math
import os
import shutil
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import certifi
import pandas as pd


def _ensure_ascii_ca_bundle() -> None:
    src = certifi.where()
    try:
        src.encode("ascii")
        return
    except UnicodeEncodeError:
        pass
    dst = Path(tempfile.gettempdir()) / "agy_cacert.pem"
    if not dst.exists() or dst.stat().st_size != Path(src).stat().st_size:
        shutil.copyfile(src, dst)
    os.environ["CURL_CA_BUNDLE"] = str(dst)
    os.environ["SSL_CERT_FILE"] = str(dst)


_ensure_ascii_ca_bundle()

import yfinance as yf

logger = logging.getLogger(__name__)


def _safe_float(val: Any) -> float | None:
    if val is None:
        return None
    try:
        f = float(val)
        if math.isnan(f) or math.isinf(f):
            return None
        return f
    except (TypeError, ValueError):
        return None


def fetch_us10y_yield(cache_dir: Path | None = None) -> float:
    """米10年国債利回り（%）を ^TNX から取得する（失敗時は 4.2% フォールバック）。"""
    cache_file = cache_dir / "us10y.json" if cache_dir else None
    if cache_file and cache_file.exists():
        age_hours = (time.time() - cache_file.stat().st_mtime) / 3600.0
        if age_hours <= 20.0:
            try:
                return float(json.loads(cache_file.read_text(encoding="utf-8"))["yield_pct"])
            except Exception:
                pass
    try:
        hist = yf.Ticker("^TNX").history(period="5d")
        if hist is not None and not hist.empty and "Close" in hist.columns:
            val = _safe_float(hist["Close"].dropna().iloc[-1])
            if val is not None and 0.1 < val < 15.0:
                val = round(val, 2)
                if cache_file:
                    cache_file.parent.mkdir(parents=True, exist_ok=True)
                    cache_file.write_text(json.dumps({"yield_pct": val}), encoding="utf-8")
                return val
    except Exception as exc:
        logger.warning("米10年国債利回りの取得に失敗（4.2%%を使用）: %s", exc)
    return 4.2


def _extract_series(df: pd.DataFrame | None, candidates: list[str], limit: int = 5) -> list[dict[str, Any]]:
    if df is None or df.empty:
        return []
    row_name = next((name for name in candidates if name in df.index), None)
    if row_name is None:
        return []

    series = df.loc[row_name]
    if isinstance(series, pd.DataFrame):
        series = series.iloc[0]

    cols = sorted(df.columns, key=lambda c: str(c), reverse=True)[:limit]
    result: list[dict[str, Any]] = []
    for col in cols:
        val = _safe_float(series.get(col))
        if val is not None:
            date_str = col.strftime("%Y-%m-%d") if hasattr(col, "strftime") else str(col)[:10]
            result.append({"date": date_str, "value": val})
    return result


def _calc_returns_and_technicals(hist: pd.DataFrame | None) -> dict[str, Any]:
    empty = {
        "latest_close": None,
        "latest_date": None,
        "returns": {"D": None, "W": None, "M": None, "3M": None, "6M": None, "9M": None, "Y": None},
        "rsi14": None,
        "macd": None,
        "macd_signal": None,
        "yearly_prices": {},
        "price_series_weekly": [],
    }
    if hist is None or hist.empty or "Close" not in hist.columns:
        return empty

    close = hist["Close"].dropna()
    if close.empty:
        return empty

    latest_close = _safe_float(close.iloc[-1])
    latest_date = close.index[-1].strftime("%Y-%m-%d") if hasattr(close.index[-1], "strftime") else str(close.index[-1])[:10]

    offsets = {"D": 1, "W": 5, "M": 21, "3M": 63, "6M": 126, "9M": 189, "Y": 252}
    returns: dict[str, float | None] = {}
    n = len(close)
    for label, offset in offsets.items():
        if n > offset and latest_close is not None:
            prev = _safe_float(close.iloc[-1 - offset])
            if prev and prev > 0:
                returns[label] = round((latest_close / prev - 1.0) * 100.0, 2)
            else:
                returns[label] = None
        else:
            returns[label] = None

    # RSI(14)
    rsi14 = None
    if n >= 15:
        delta = close.diff()
        gain = delta.clip(lower=0).rolling(14).mean()
        loss = (-delta.clip(upper=0)).rolling(14).mean()
        last_gain = _safe_float(gain.iloc[-1])
        last_loss = _safe_float(loss.iloc[-1])
        if last_gain is not None and last_loss is not None:
            if last_loss == 0:
                rsi14 = 100.0
            else:
                rs = last_gain / last_loss
                rsi14 = round(100.0 - (100.0 / (1.0 + rs)), 2)

    # MACD(12, 26, 9)
    macd_val = None
    macd_sig = None
    if n >= 35:
        ema12 = close.ewm(span=12, adjust=False).mean()
        ema26 = close.ewm(span=26, adjust=False).mean()
        macd_line = ema12 - ema26
        signal_line = macd_line.ewm(span=9, adjust=False).mean()
        macd_val = _safe_float(macd_line.iloc[-1])
        macd_sig = _safe_float(signal_line.iloc[-1])
        if macd_val is not None:
            macd_val = round(macd_val, 3)
        if macd_sig is not None:
            macd_sig = round(macd_sig, 3)

    # 年別株価（過去レンジ＆年平均株価算出用）
    yearly_prices: dict[str, dict[str, float]] = {}
    if hasattr(close.index, "year"):
        for yr, grp in close.groupby(close.index.year):
            yearly_prices[str(yr)] = {
                "min": round(float(grp.min()), 2),
                "max": round(float(grp.max()), 2),
                "avg": round(float(grp.mean()), 2),
            }

    # 週次サンプリング（個別レポートの株価SVG用：直近約2年＝100点）
    weekly_pts: list[dict[str, Any]] = []
    tail = close.iloc[-504:] if n > 504 else close
    step = max(1, len(tail) // 90)
    for idx in range(0, len(tail), step):
        dt = tail.index[idx]
        d_str = dt.strftime("%Y-%m-%d") if hasattr(dt, "strftime") else str(dt)[:10]
        v = _safe_float(tail.iloc[idx])
        if v is not None:
            weekly_pts.append({"date": d_str, "close": round(v, 2)})
    if latest_close is not None and (not weekly_pts or weekly_pts[-1]["date"] != latest_date):
        weekly_pts.append({"date": latest_date, "close": round(latest_close, 2)})

    return {
        "latest_close": round(latest_close, 2) if latest_close is not None else None,
        "latest_date": latest_date,
        "returns": returns,
        "rsi14": rsi14,
        "macd": macd_val,
        "macd_signal": macd_sig,
        "yearly_prices": yearly_prices,
        "price_series_weekly": weekly_pts,
    }


def _calc_dividend_metrics(
    divs: pd.Series | None,
    cur_price: float | None,
    yearly_prices: dict[str, dict[str, float]],
    info: dict[str, Any],
) -> dict[str, Any]:
    """配当履歴（分割調整済み）と株価から配当株スクリーニング・採点用の全指標を算出する。"""
    now = datetime.now(timezone.utc)
    cur_year = now.year
    last_full_year = cur_year - 1

    annual_div_map: dict[int, float] = {}
    ttm_dividend = 0.0

    if divs is not None and not divs.empty:
        divs_clean = divs[divs > 0].dropna()
        if not divs_clean.empty:
            # タイムゾーンを揃えて直近365日を集計
            cutoff = pd.Timestamp(now - timedelta(days=366))
            idx = divs_clean.index
            if getattr(idx, "tz", None) is None:
                cutoff = cutoff.tz_localize(None)
            else:
                cutoff = cutoff.tz_convert(idx.tz)
            ttm_series = divs_clean[divs_clean.index >= cutoff]
            ttm_dividend = float(ttm_series.sum())

            for yr, grp in divs_clean.groupby(divs_clean.index.year):
                annual_div_map[int(yr)] = round(float(grp.sum()), 4)

    # 直近1年実績配当利回り（%）
    ttm_yield = None
    if cur_price and cur_price > 0 and ttm_dividend > 0:
        ttm_yield = round(ttm_dividend / cur_price * 100.0, 2)

    # 予想配当利回り（%）：info.dividendRate / cur_price を優先（yfinanceのdividendYieldは100倍ズレることがあるため）
    div_rate = _safe_float(info.get("dividendRate"))
    forward_yield = None
    if div_rate and div_rate > 0 and cur_price and cur_price > 0:
        forward_yield = round(div_rate / cur_price * 100.0, 2)
    elif ttm_yield is not None:
        forward_yield = ttm_yield
    else:
        raw_dy = _safe_float(info.get("dividendYield"))
        if raw_dy is not None and raw_dy > 0:
            # yfinanceバージョンにより 0.032 または 3.2 が返るため補正
            forward_yield = round(raw_dy * 100.0 if raw_dy < 0.35 else raw_dy, 2)

    # 異常値ガード（25%超は特別配当やデータ異常の可能性が高いため抑制）
    if forward_yield is not None and forward_yield > 25.0:
        forward_yield = ttm_yield if (ttm_yield and ttm_yield <= 25.0) else None

    # 3年平均配当利回り（%）と過去5年の年次利回りレンジ
    yearly_yields: list[float] = []
    recent_3y_yields: list[float] = []
    for yr in range(last_full_year - 4, last_full_year + 1):
        d = annual_div_map.get(yr)
        p_info = yearly_prices.get(str(yr))
        if d and d > 0 and p_info and p_info.get("avg", 0) > 0:
            y_pct = d / p_info["avg"] * 100.0
            if y_pct <= 25.0:
                yearly_yields.append(round(y_pct, 2))
                if yr >= last_full_year - 2:
                    recent_3y_yields.append(y_pct)

    avg_3y_yield = round(sum(recent_3y_yields) / len(recent_3y_yields), 2) if recent_3y_yields else None

    # 配当利回り過去レンジ内の位置（%）：高いほど割安（過去最大利回りに近いほど100%）
    yield_range_pos = None
    if forward_yield is not None and len(yearly_yields) >= 2:
        y_min = min(yearly_yields)
        y_max = max(yearly_yields)
        if y_max > y_min:
            pos = (forward_yield - y_min) / (y_max - y_min) * 100.0
            yield_range_pos = round(max(0.0, min(100.0, pos)), 1)
        else:
            yield_range_pos = 50.0

    # 連続非減配年数 & 連続増配年数（直近完了年から遡る）
    non_cut_years = 0
    consecutive_growth_years = 0
    if last_full_year in annual_div_map and annual_div_map[last_full_year] > 0:
        # まず今年のTTMが昨年より大きく減配していないか確認（10%以上の急減は減配扱い）
        ttm_ok = True
        if ttm_dividend > 0 and ttm_dividend < annual_div_map[last_full_year] * 0.90:
            ttm_ok = False
        if ttm_ok:
            yr = last_full_year
            while True:
                cur_d = annual_div_map.get(yr, 0.0)
                prev_d = annual_div_map.get(yr - 1, 0.0)
                if cur_d > 0 and prev_d > 0 and cur_d >= prev_d * 0.985:
                    non_cut_years += 1
                    yr -= 1
                else:
                    break

            yr = last_full_year
            while True:
                cur_d = annual_div_map.get(yr, 0.0)
                prev_d = annual_div_map.get(yr - 1, 0.0)
                if cur_d > 0 and prev_d > 0 and cur_d > prev_d * 1.001:
                    consecutive_growth_years += 1
                    yr -= 1
                else:
                    break

    # 5年増配率 CAGR（%）：5年前がなければ4年前・3年前で代替
    div_cagr_5y = None
    latest_full_div = annual_div_map.get(last_full_year)
    if latest_full_div and latest_full_div > 0:
        for span in (5, 4, 3):
            old_div = annual_div_map.get(last_full_year - span)
            if old_div and old_div > 0:
                cagr = ((latest_full_div / old_div) ** (1.0 / span) - 1.0) * 100.0
                div_cagr_5y = round(max(-50.0, min(80.0, cagr)), 2)
                break

    # 直近10年分の年次配当リスト（昇順・レポートグラフ用）
    annual_dividends = [
        {"year": yr, "amount": annual_div_map[yr]}
        for yr in sorted(annual_div_map.keys())
        if yr >= last_full_year - 9 and yr <= cur_year
    ]

    return {
        "ttm_dividend": round(ttm_dividend, 4),
        "ttm_yield": ttm_yield,
        "forward_dividend": round(div_rate, 4) if div_rate else round(ttm_dividend, 4),
        "forward_yield": forward_yield,
        "avg_3y_yield": avg_3y_yield,
        "yield_range_pos": yield_range_pos,
        "yield_history_min": min(yearly_yields) if yearly_yields else None,
        "yield_history_max": max(yearly_yields) if yearly_yields else None,
        "non_cut_years": non_cut_years,
        "consecutive_growth_years": consecutive_growth_years,
        "div_cagr_5y": div_cagr_5y,
        "annual_dividends": annual_dividends,
    }


def check_dividend_screen(div_data: dict[str, Any]) -> tuple[bool, str]:
    """参考サイト準拠の配当スクリーニング条件（実績利回り>=1.5%, 3年平均>=1.2%, 直近5年減配なし）を判定する。"""
    ttm_y = div_data.get("ttm_yield")
    avg3_y = div_data.get("avg_3y_yield")
    non_cut = div_data.get("non_cut_years", 0)

    if ttm_y is None or ttm_y < 1.5:
        return False, f"直近1年実績利回り不足 ({ttm_y if ttm_y is not None else '-'}% < 1.5%)"
    if avg3_y is None or avg3_y < 1.2:
        return False, f"3年平均利回り不足 ({avg3_y if avg3_y is not None else '-'}% < 1.2%)"
    if non_cut < 5:
        return False, f"連続非減配年数不足 ({non_cut}年 < 5年)"
    return True, "通過"


def fetch_stock_data(
    constituent: dict[str, Any],
    cache_dir: Path,
    use_cache: bool = True,
    max_cache_age_hours: float = 20.0,
    sleep_sec: float = 0.1,
    skip_non_dividend: bool = True,
) -> dict[str, Any] | None:
    """1銘柄分のデータを取得。skip_non_dividend=Trueの場合、配当条件未達銘柄は財務諸表取得を省き高速化する。"""
    yf_symbol = constituent["yf_symbol"]
    stock_cache_dir = cache_dir / "stocks"
    stock_cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = stock_cache_dir / f"{yf_symbol}.json"

    if use_cache and cache_file.exists():
        age_hours = (time.time() - cache_file.stat().st_mtime) / 3600.0
        if age_hours <= max_cache_age_hours:
            try:
                cached = json.loads(cache_file.read_text(encoding="utf-8"))
                # キャッシュが完全取得済み、または対象外として記録済みならそのまま返す
                if cached.get("screen_passed") or skip_non_dividend:
                    return cached
            except Exception:
                pass

    for attempt in range(4):
        try:
            ticker = yf.Ticker(yf_symbol)
            hist = ticker.history(period="5y", interval="1d", auto_adjust=True)
            tech = _calc_returns_and_technicals(hist)
            divs = ticker.dividends
            cur_price = tech["latest_close"]

            # まず配当履歴のみで軽量スクリーニング判定（非配当株への過剰なAPIアクセスを回避）
            pre_div = _calc_dividend_metrics(divs, cur_price, tech["yearly_prices"], {})
            passed, reason = check_dividend_screen(pre_div)

            if skip_non_dividend and not passed:
                light_data: dict[str, Any] = {
                    "symbol": constituent["symbol"],
                    "yf_symbol": yf_symbol,
                    "name": constituent["name"],
                    "sector_en": constituent["sector_en"],
                    "sector_ja": constituent["sector_ja"],
                    "sub_industry": constituent.get("sub_industry", ""),
                    "index_group": constituent.get("index_group", "S&P 500"),
                    "is_king": bool(constituent.get("is_king", False)),
                    "is_aristocrat": bool(constituent.get("is_aristocrat", False)),
                    "fetched_at": datetime.now(timezone.utc).isoformat(),
                    "screen_passed": False,
                    "screen_reason": reason,
                    "dividend": pre_div,
                }
                cache_file.write_text(json.dumps(light_data, ensure_ascii=False), encoding="utf-8")
                if sleep_sec > 0:
                    time.sleep(sleep_sec)
                return light_data

            # 配当スクリーニング通過銘柄はフルデータ（info・財務諸表・CF）を取得
            info = ticker.info or {}
            cur_price = (
                _safe_float(info.get("currentPrice"))
                or _safe_float(info.get("regularMarketPrice"))
                or tech["latest_close"]
            )
            div_full = _calc_dividend_metrics(divs, cur_price, tech["yearly_prices"], info)
            passed, reason = check_dividend_screen(div_full)

            inc = ticker.income_stmt
            q_inc = ticker.quarterly_income_stmt
            bs = ticker.balance_sheet
            cf = ticker.cashflow

            data: dict[str, Any] = {
                "symbol": constituent["symbol"],
                "yf_symbol": yf_symbol,
                "name": constituent["name"],
                "short_name": info.get("shortName") or constituent["name"],
                "sector_en": constituent["sector_en"],
                "sector_ja": constituent["sector_ja"],
                "sub_industry": constituent.get("sub_industry", ""),
                "industry_yf": info.get("industry", ""),
                "index_group": constituent.get("index_group", "S&P 500"),
                "is_king": bool(constituent.get("is_king", False)),
                "is_aristocrat": bool(constituent.get("is_aristocrat", False)),
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "screen_passed": passed,
                "screen_reason": reason,
                "dividend": div_full,
                "price": {
                    "current": cur_price,
                    "latest_date": tech["latest_date"],
                    "market_cap": _safe_float(info.get("marketCap")),
                    "enterprise_value": _safe_float(info.get("enterpriseValue")),
                    "returns": tech["returns"],
                    "rsi14": tech["rsi14"],
                    "macd": tech["macd"],
                    "macd_signal": tech["macd_signal"],
                    "yearly_prices": tech["yearly_prices"],
                    "price_series_weekly": tech["price_series_weekly"],
                },
                "valuation": {
                    "trailing_pe": _safe_float(info.get("trailingPE")),
                    "forward_pe": _safe_float(info.get("forwardPE")),
                    "price_to_book": _safe_float(info.get("priceToBook")),
                    "dividend_yield": div_full["forward_yield"],
                    "trailing_eps": _safe_float(info.get("trailingEps")),
                    "forward_eps": _safe_float(info.get("forwardEps")),
                    "book_value": _safe_float(info.get("bookValue")),
                    "roe_info": _safe_float(info.get("returnOnEquity")),
                    "roa_info": _safe_float(info.get("returnOnAssets")),
                    "payout_ratio_info": _safe_float(info.get("payoutRatio")),
                    "shares_outstanding": _safe_float(info.get("sharesOutstanding")),
                },
                "analyst": {
                    "num_opinions": info.get("numberOfAnalystOpinions"),
                    "target_mean_price": _safe_float(info.get("targetMeanPrice")),
                    "target_high_price": _safe_float(info.get("targetHighPrice")),
                    "target_low_price": _safe_float(info.get("targetLowPrice")),
                    "recommendation_mean": _safe_float(info.get("recommendationMean")),
                },
                "financials": {
                    "revenue": _extract_series(inc, ["Total Revenue", "Operating Revenue"]),
                    "operating_income": _extract_series(inc, ["Operating Income", "EBIT"]),
                    "ebit": _extract_series(inc, ["EBIT", "Operating Income"]),
                    "net_income": _extract_series(inc, ["Net Income", "Net Income Common Stockholders"]),
                    "eps": _extract_series(inc, ["Diluted EPS", "Basic EPS"]),
                    "interest_expense": _extract_series(inc, ["Interest Expense", "Interest Expense Non Operating"]),
                    "shares": _extract_series(inc, ["Diluted Average Shares", "Basic Average Shares"]),
                },
                "quarterly": {
                    "revenue": _extract_series(q_inc, ["Total Revenue", "Operating Revenue"], limit=6),
                    "operating_income": _extract_series(q_inc, ["Operating Income", "EBIT"], limit=6),
                    "net_income": _extract_series(q_inc, ["Net Income", "Net Income Common Stockholders"], limit=6),
                },
                "balance_sheet": {
                    "total_debt": _extract_series(bs, ["Total Debt", "Long Term Debt And Capital Lease Obligation"]),
                    "cash": _extract_series(bs, ["Cash And Cash Equivalents", "Cash Cash Equivalents And Short Term Investments"]),
                    "equity": _extract_series(bs, ["Stockholders Equity", "Common Stock Equity", "Total Equity Gross Minority Interest"]),
                    "total_assets": _extract_series(bs, ["Total Assets"]),
                },
                "cashflow": {
                    "operating_cf": _extract_series(cf, ["Operating Cash Flow", "Cash Flow From Continuing Operating Activities"]),
                    "capex": _extract_series(cf, ["Capital Expenditure"]),
                    "free_cf": _extract_series(cf, ["Free Cash Flow"]),
                    "depreciation": _extract_series(cf, ["Depreciation And Amortization", "Depreciation Amortization Depletion"]),
                    "dividends_paid": _extract_series(cf, ["Cash Dividends Paid", "Common Stock Dividend Paid"]),
                    "buybacks": _extract_series(cf, ["Repurchase Of Capital Stock"]),
                    "sbc": _extract_series(cf, ["Stock Based Compensation"]),
                },
                "summary": info.get("longBusinessSummary", ""),
            }

            cache_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            if sleep_sec > 0:
                time.sleep(sleep_sec)
            return data
        except Exception as exc:
            msg = str(exc)
            if "Too Many Requests" in msg or "Rate limited" in msg or "429" in msg:
                wait_s = 8.0 * (attempt + 1)
                logger.warning("%s レート制限 (attempt %d): %.0f秒待機します", yf_symbol, attempt + 1, wait_s)
                time.sleep(wait_s)
            else:
                logger.warning("%s の取得に失敗 (attempt %d): %s", yf_symbol, attempt + 1, exc)
                time.sleep(1.5)

    if cache_file.exists():
        try:
            return json.loads(cache_file.read_text(encoding="utf-8"))
        except Exception:
            pass
    return None
