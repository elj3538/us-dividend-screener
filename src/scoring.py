"""米国株 配当株 軍分けランキングの選定スコア・買い時スコア・軍分け・業種級を算出するモジュール。"""

from __future__ import annotations

import math
from statistics import median
from typing import Any

RATE_SENSITIVE_SECTORS = {"公益事業", "不動産", "コミュニケーション", "生活必需品"}


def _piecewise(val: float | None, points: list[tuple[float, float]]) -> float | None:
    """区分線形補間で指標値を0〜110のスコアに変換する。pointsはx昇順。"""
    if val is None or math.isnan(val) or math.isinf(val):
        return None
    if val <= points[0][0]:
        return points[0][1]
    if val >= points[-1][0]:
        return points[-1][1]
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        if x0 <= val <= x1:
            if x1 == x0:
                return y1
            ratio = (val - x0) / (x1 - x0)
            return y0 + ratio * (y1 - y0)
    return None


def _avg(values: list[float | None]) -> float | None:
    valid = [v for v in values if v is not None]
    return sum(valid) / len(valid) if valid else None


def _weighted_avg(pairs: list[tuple[float | None, float]]) -> float | None:
    num = 0.0
    den = 0.0
    for val, w in pairs:
        if val is not None:
            num += val * w
            den += w
    return num / den if den > 0 else None


def _calc_cagr(series: list[dict[str, Any]]) -> float | None:
    """新しい順の年次シリーズからCAGR(%)を算出する。"""
    if len(series) < 2:
        return None
    latest = series[0]["value"]
    oldest = series[-1]["value"]
    years = len(series) - 1
    if oldest is None or latest is None or oldest <= 0 or latest <= 0:
        if oldest and oldest != 0 and latest is not None:
            pct = (latest - oldest) / abs(oldest) * 100.0 / years
            return max(-50.0, min(50.0, pct))
        return None
    cagr = ((latest / oldest) ** (1.0 / years) - 1.0) * 100.0
    return round(max(-80.0, min(150.0, cagr)), 2)


def _grade3(val: float | None, good_cond: bool, warn_cond: bool, labels: tuple[str, str, str] = ("良好", "注意", "弱い")) -> str | None:
    if val is None:
        return None
    if good_cond:
        return labels[0]
    if warn_cond:
        return labels[1]
    return labels[2]


def classify_model(stock: dict[str, Any]) -> str:
    """銘柄の業種から採点モデル（general / financial / reit）を判定する。"""
    sector_en = stock.get("sector_en", "")
    sub = stock.get("sub_industry", "")
    ind = stock.get("industry_yf", "")
    sym = stock.get("symbol", "")

    if sector_en == "Real Estate":
        if "REIT" in sub or "REIT" in ind:
            return "reit"
        return "general"

    if sector_en == "Financials":
        general_fin_tickers = {
            "V", "MA", "PYPL", "AXP", "MSCI", "SPGI", "MCO", "ICE",
            "CME", "NDAQ", "CBOE", "FDS", "FIS", "FI", "JKHY", "GPN",
        }
        if sym in general_fin_tickers:
            return "general"
        if any(k in sub or k in ind for k in ["Bank", "Insurance", "Capital Markets", "Brokerage"]) or sym in {"GS", "MS"}:
            return "financial"
    return "general"


def _compute_raw_metrics(stock: dict[str, Any], us10y_yield: float) -> dict[str, Any]:
    fin = stock.get("financials", {})
    q = stock.get("quarterly", {})
    bs = stock.get("balance_sheet", {})
    cf = stock.get("cashflow", {})
    val = stock.get("valuation", {})
    price_info = stock.get("price", {})
    div_info = stock.get("dividend", {})

    model = classify_model(stock)
    mkt_cap = price_info.get("market_cap")
    cur_price = price_info.get("current")

    rev_s = fin.get("revenue", [])
    op_s = fin.get("operating_income", [])
    ebit_s = fin.get("ebit", []) or op_s
    ni_s = fin.get("net_income", [])
    eps_s = fin.get("eps", [])
    int_s = fin.get("interest_expense", [])

    debt_s = bs.get("total_debt", [])
    cash_s = bs.get("cash", [])
    eq_s = bs.get("equity", [])
    assets_s = bs.get("total_assets", [])

    ocf_s = cf.get("operating_cf", [])
    capex_s = cf.get("capex", [])
    fcf_s = cf.get("free_cf", [])
    dep_s = cf.get("depreciation", [])
    div_paid_s = cf.get("dividends_paid", [])
    buybacks_s = cf.get("buybacks", [])

    # 業績指標
    rev_cagr = _calc_cagr(rev_s)
    eps_cagr = _calc_cagr(eps_s) or _calc_cagr(ni_s)

    op_margin = None
    if rev_s and op_s and rev_s[0]["value"] and rev_s[0]["value"] > 0:
        op_margin = round(op_s[0]["value"] / rev_s[0]["value"] * 100.0, 2)

    # 利益安定度（黒字年割合＋変動の小ささ）
    profit_series = [x["value"] for x in (op_s or ni_s) if x.get("value") is not None]
    profit_stability = None
    if len(profit_series) >= 2:
        pos_ratio = sum(1 for v in profit_series if v > 0) / len(profit_series)
        mean_abs = sum(abs(v) for v in profit_series) / len(profit_series)
        if mean_abs > 0:
            diffs = [abs(profit_series[i] - profit_series[i + 1]) / mean_abs for i in range(len(profit_series) - 1)]
            vol = sum(diffs) / len(diffs)
            profit_stability = round(max(0.0, min(110.0, pos_ratio * 90.0 + max(0.0, 20.0 - vol * 35.0))), 1)

    # 直近四半期 急減速チェック
    q_rev = q.get("revenue", [])
    q_op = q.get("operating_income", [])
    q_ni = q.get("net_income", [])
    q_rev_yoy = None
    q_profit_yoy = None
    rapid_decel = False
    if len(q_rev) >= 5 and q_rev[4]["value"] and q_rev[4]["value"] > 0:
        q_rev_yoy = round((q_rev[0]["value"] / q_rev[4]["value"] - 1.0) * 100.0, 2)
    prof_q = q_op if len(q_op) >= 5 else q_ni
    if len(prof_q) >= 5 and prof_q[4]["value"] and abs(prof_q[4]["value"]) > 0:
        q_profit_yoy = round((prof_q[0]["value"] - prof_q[4]["value"]) / abs(prof_q[4]["value"]) * 100.0, 2)
    if q_rev_yoy is not None and q_profit_yoy is not None:
        if q_rev_yoy < -5.0 and q_profit_yoy < -10.0:
            rapid_decel = True
        elif rev_cagr is not None and (rev_cagr - q_rev_yoy) >= 12.0 and q_profit_yoy < 0:
            rapid_decel = True

    # 財務指標
    debt_v = debt_s[0]["value"] if debt_s else None
    cash_v = cash_s[0]["value"] if cash_s else 0.0
    eq_v = eq_s[0]["value"] if eq_s else None
    assets_v = assets_s[0]["value"] if assets_s else None
    ocf_v = ocf_s[0]["value"] if ocf_s else None
    capex_v = capex_s[0]["value"] if capex_s else None
    fcf_v = fcf_s[0]["value"] if fcf_s else None
    if fcf_v is None and ocf_v is not None and capex_v is not None:
        fcf_v = ocf_v - abs(capex_v)

    de_ratio = round(debt_v / eq_v, 2) if (debt_v is not None and eq_v and eq_v > 0) else None
    net_de = round((debt_v - (cash_v or 0.0)) / eq_v, 2) if (debt_v is not None and eq_v and eq_v > 0) else None
    debt_to_ocf = round(debt_v / ocf_v, 2) if (debt_v is not None and ocf_v and ocf_v > 0) else None

    ebit_v = ebit_s[0]["value"] if ebit_s else None
    int_v = abs(int_s[0]["value"]) if (int_s and int_s[0]["value"]) else None
    icov = round(ebit_v / int_v, 2) if (ebit_v is not None and int_v and int_v > 0) else None

    # CF・配当指標
    ocf_positive = (ocf_v is not None and ocf_v > 0)
    fcf_positive = (fcf_v is not None and fcf_v > 0)
    div_paid_v = abs(div_paid_s[0]["value"]) if (div_paid_s and div_paid_s[0]["value"]) else None
    fcf_payout = None
    if div_paid_v is not None and fcf_v is not None and fcf_v > 0:
        fcf_payout = round(div_paid_v / fcf_v * 100.0, 1)
    elif div_paid_v is not None and fcf_v is not None and fcf_v <= 0:
        fcf_payout = 150.0  # FCF赤字で配当支払

    # 配当性向（純利益ベース %）
    payout_ratio = None
    ni_v = ni_s[0]["value"] if ni_s else None
    if div_paid_v is not None and ni_v is not None and ni_v > 0:
        payout_ratio = round(div_paid_v / ni_v * 100.0, 1)
    elif val.get("payout_ratio_info") is not None:
        pr = val["payout_ratio_info"]
        payout_ratio = round(pr * 100.0 if pr <= 3.0 else pr, 1)

    # ROE / ROA (%)
    roe = None
    if ni_v is not None and eq_v and eq_v > 0:
        roe = round(ni_v / eq_v * 100.0, 1)
    elif val.get("roe_info") is not None:
        roe = round(val["roe_info"] * 100.0, 1)

    roa = None
    if ni_v is not None and assets_v and assets_v > 0:
        roa = round(ni_v / assets_v * 100.0, 1)
    elif val.get("roa_info") is not None:
        roa = round(val["roa_info"] * 100.0, 1)

    # 配当・総還元指標
    forward_yield = div_info.get("forward_yield")
    ttm_yield = div_info.get("ttm_yield")
    avg_3y_yield = div_info.get("avg_3y_yield")
    div_cagr_5y = div_info.get("div_cagr_5y")
    consec_growth = div_info.get("consecutive_growth_years", 0)
    non_cut_years = div_info.get("non_cut_years", 0)
    yield_range_pos = div_info.get("yield_range_pos")

    buyback_v = abs(buybacks_s[0]["value"]) if (buybacks_s and buybacks_s[0]["value"]) else 0.0
    buyback_yield = round(buyback_v / mkt_cap * 100.0, 2) if (mkt_cap and mkt_cap > 0 and buyback_v > 0) else 0.0
    total_yield = round((forward_yield or 0.0) + buyback_yield, 2) if forward_yield is not None else None

    # Chowderルール（予想配当利回り + 5年増配率）
    chowder = None
    if forward_yield is not None and div_cagr_5y is not None:
        chowder = round(forward_yield + div_cagr_5y, 2)

    # 金利スプレッド（予想配当利回り - 米10年国債利回り）
    rate_spread = round(forward_yield - us10y_yield, 2) if forward_yield is not None else None

    # バリュエーション（PER・PBR・PER過去レンジ位置）
    trailing_pe = val.get("trailing_pe")
    if trailing_pe is not None and (trailing_pe <= 0 or trailing_pe > 200):
        trailing_pe = None
    pbr = val.get("price_to_book")
    if pbr is not None and (pbr <= 0 or pbr > 100):
        pbr = None

    per_range_pos = None
    yearly_prices = price_info.get("yearly_prices", {})
    if trailing_pe is not None and eps_s and yearly_prices:
        hist_pers: list[float] = []
        for row in eps_s:
            yr = row["date"][:4]
            e = row["value"]
            p_info = yearly_prices.get(yr)
            if e and e > 0 and p_info and p_info.get("avg", 0) > 0:
                pe_yr = p_info["avg"] / e
                if 2.0 <= pe_yr <= 120.0:
                    hist_pers.append(pe_yr)
        if len(hist_pers) >= 2:
            p_min, p_max = min(hist_pers), max(hist_pers)
            if p_max > p_min:
                # 低いPERほど割安＝高%
                pos = (p_max - trailing_pe) / (p_max - p_min) * 100.0
                per_range_pos = round(max(0.0, min(100.0, pos)), 1)
            else:
                per_range_pos = 50.0

    # --- 1. 業績スコア ---
    s_rev = _piecewise(rev_cagr, [(-10, 15), (0, 50), (5, 78), (10, 95), (18, 110)])
    s_eps = _piecewise(eps_cagr, [(-15, 10), (0, 50), (6, 80), (12, 98), (20, 110)])
    s_margin = _piecewise(op_margin, [(0, 15), (8, 55), (15, 80), (25, 98), (35, 110)])
    perf_raw = _avg([s_rev, s_eps, s_margin, profit_stability])
    if perf_raw is not None and rapid_decel:
        # 急減速ペナルティ（最大40%減点）
        penalty = 0.70 if (q_profit_yoy is not None and q_profit_yoy < -25.0) else 0.80
        perf_score = round(perf_raw * penalty, 1)
    else:
        perf_score = round(perf_raw, 1) if perf_raw is not None else None

    # --- 2. 財務スコア ---
    s_de = _piecewise(de_ratio, [(0.0, 105), (0.5, 92), (1.0, 75), (2.0, 48), (3.5, 15)])
    s_nde = _piecewise(net_de, [(-0.2, 110), (0.3, 92), (0.8, 75), (1.8, 45), (3.0, 15)])
    s_docf = _piecewise(debt_to_ocf, [(0.5, 108), (2.0, 88), (3.5, 68), (6.0, 38), (10.0, 10)])
    s_icov = _piecewise(icov, [(1.5, 15), (3.0, 48), (6.0, 76), (12.0, 95), (25.0, 110)])
    fin_score = _avg([s_de, s_nde, s_docf, s_icov])
    fin_score = round(fin_score, 1) if fin_score is not None else None

    # --- 3. キャッシュフロースコア ---
    s_ocf = 95.0 if ocf_positive else (20.0 if ocf_v is not None else None)
    s_fcf = 98.0 if fcf_positive else (15.0 if fcf_v is not None else None)
    s_fcf_pay = _piecewise(fcf_payout, [(25, 108), (50, 95), (70, 78), (95, 52), (120, 18)])
    cf_score = _avg([s_ocf, s_fcf, s_fcf_pay])
    cf_score = round(cf_score, 1) if cf_score is not None else None

    # --- 4. 配当の持続力スコア ---
    s_div_cagr = _piecewise(div_cagr_5y, [(-2, 15), (0, 42), (4, 72), (7, 90), (12, 108)])
    s_consec_g = _piecewise(float(consec_growth), [(0, 35), (5, 65), (10, 82), (20, 98), (30, 110)])
    s_non_cut = _piecewise(float(non_cut_years), [(5, 62), (10, 80), (20, 96), (30, 110)])
    s_payout = _piecewise(payout_ratio, [(20, 98), (45, 95), (60, 80), (80, 52), (105, 18)])
    s_roe = _piecewise(roe, [(0, 15), (7, 55), (12, 80), (18, 96), (28, 110)])
    s_tot_y = _piecewise(total_yield, [(1.5, 45), (3.0, 72), (5.0, 92), (7.5, 108)])
    div_score = _avg([s_div_cagr, s_consec_g, s_non_cut, s_payout, s_roe, s_tot_y])
    div_score = round(div_score, 1) if div_score is not None else None

    # --- 選定スコア統合（モデル別） ---
    if model == "financial":
        fin_quality = _avg([s_roe, s_rev, s_eps, profit_stability])
        if fin_quality is not None and rapid_decel:
            fin_quality *= 0.80
        select_raw = _weighted_avg([(fin_quality, 0.55), (div_score, 0.45)])
        used_parts = [x for x in [s_roe, s_rev, s_eps, profit_stability, s_div_cagr, s_consec_g, s_non_cut, s_payout, s_tot_y] if x is not None]
        total_parts = 9
    elif model == "reit":
        # FFO近似 = 純利益 + 減価償却費
        ffo_series: list[dict[str, Any]] = []
        dep_map = {x["date"]: x["value"] for x in dep_s}
        for row in ni_s:
            d = row["date"]
            ffo_v = row["value"] + abs(dep_map.get(d, 0.0))
            ffo_series.append({"date": d, "value": ffo_v})
        ffo_cagr = _calc_cagr(ffo_series)
        s_ffo_g = _piecewise(ffo_cagr, [(-5, 20), (0, 52), (4, 80), (8, 98), (14, 110)])
        reit_quality = _avg([s_ffo_g, s_rev, profit_stability, s_icov])
        if reit_quality is not None and rapid_decel:
            reit_quality *= 0.80
        select_raw = _weighted_avg([(reit_quality, 0.55), (div_score, 0.45)])
        used_parts = [x for x in [s_ffo_g, s_rev, profit_stability, s_icov, s_div_cagr, s_consec_g, s_non_cut, s_tot_y] if x is not None]
        total_parts = 8
    else:
        select_raw = _weighted_avg([
            (perf_score, 0.25),
            (fin_score, 0.20),
            (cf_score, 0.15),
            (div_score, 0.40),
        ])
        used_parts = [
            x for x in [
                s_rev, s_eps, s_margin, profit_stability,
                s_de, s_nde, s_docf, s_icov,
                s_ocf, s_fcf, s_fcf_pay,
                s_div_cagr, s_consec_g, s_non_cut, s_payout, s_roe, s_tot_y,
            ] if x is not None
        ]
        total_parts = 17

    select_score = round(min(110.0, max(0.0, select_raw)), 1) if select_raw is not None else None
    cov_ratio = len(used_parts) / total_parts if total_parts > 0 else 0.0
    coverage = "高" if cov_ratio >= 0.85 else ("中" if cov_ratio >= 0.65 else "低")

    # ⚠注意フラグ（採点・軍分けには不使用）
    warn_reasons: list[str] = []
    if rapid_decel:
        warn_reasons.append("直近四半期急減速")
    if fcf_v is not None and fcf_v <= 0 and model == "general":
        warn_reasons.append("フリーCF赤字")
    if fcf_payout is not None and fcf_payout > 100.0 and model == "general":
        warn_reasons.append("FCF配当性向100%超")
    if payout_ratio is not None and payout_ratio > 80.0 and model == "general":
        warn_reasons.append("配当性向80%超")

    return {
        "symbol": stock["symbol"],
        "yf_symbol": stock["yf_symbol"],
        "name": stock["name"],
        "sector_en": stock["sector_en"],
        "sector_ja": stock["sector_ja"],
        "sub_industry": stock.get("sub_industry", ""),
        "index_group": stock.get("index_group", "S&P 500"),
        "is_king": bool(stock.get("is_king", False)),
        "is_aristocrat": bool(stock.get("is_aristocrat", False)),
        "model": model,
        "close": round(cur_price, 2) if cur_price is not None else None,
        "latest_date": price_info.get("latest_date"),
        "market_cap_m": round(mkt_cap / 1e6, 1) if mkt_cap else None,
        "returns": price_info.get("returns", {}),
        "select_score": select_score,
        "buy_score": None,  # 業種比較後に算出
        "perf_score": perf_score,
        "fin_score": fin_score,
        "cf_score": cf_score,
        "div_score": div_score,
        "coverage": coverage,
        "coverage_pct": round(cov_ratio * 100.0, 1),
        "rapid_decel": rapid_decel,
        "warn_reasons": warn_reasons,
        "metrics": {
            "forward_yield": forward_yield,
            "ttm_yield": ttm_yield,
            "avg_3y_yield": avg_3y_yield,
            "div_cagr_5y": div_cagr_5y,
            "consec_growth": consec_growth,
            "non_cut_years": non_cut_years,
            "payout_ratio": payout_ratio,
            "fcf_payout": fcf_payout,
            "buyback_yield": buyback_yield,
            "total_yield": total_yield,
            "chowder": chowder,
            "yield_range_pos": yield_range_pos,
            "rate_spread": rate_spread,
            "roe": roe,
            "roa": roa,
            "rev_cagr": rev_cagr,
            "eps_cagr": eps_cagr,
            "op_margin": op_margin,
            "profit_stability": profit_stability,
            "de_ratio": de_ratio,
            "net_de": net_de,
            "debt_to_ocf": debt_to_ocf,
            "icov": icov,
            "ocf_positive": ocf_positive,
            "fcf_positive": fcf_positive,
            "trailing_pe": round(trailing_pe, 2) if trailing_pe is not None else None,
            "pbr": round(pbr, 2) if pbr is not None else None,
            "per_range_pos": per_range_pos,
            "per_rel": None,
            "pbr_rel": None,
            "q_rev_yoy": q_rev_yoy,
            "q_profit_yoy": q_profit_yoy,
            "rsi14": price_info.get("rsi14"),
            "macd": price_info.get("macd"),
        },
        "grades": {
            "perf": _grade3(perf_score, (perf_score or 0) >= 80, (perf_score or 0) >= 62),
            "fin": _grade3(fin_score, (fin_score or 0) >= 80, (fin_score or 0) >= 62),
            "fcf": "良好" if fcf_positive else ("弱い" if fcf_v is not None else None),
            "fcf_pay": _grade3(fcf_payout, (fcf_payout or 999) <= 70, (fcf_payout or 999) <= 100),
            "div_cagr": _grade3(div_cagr_5y, (div_cagr_5y or -99) >= 5.0, (div_cagr_5y or -99) >= 0.0),
            "consec_g": _grade3(float(consec_growth), consec_growth >= 15, consec_growth >= 5),
            "non_cut": _grade3(float(non_cut_years), non_cut_years >= 20, non_cut_years >= 5),
            "payout": _grade3(payout_ratio, (payout_ratio or 999) <= 55.0, (payout_ratio or 999) <= 80.0),
            "roe": _grade3(roe, (roe or -99) >= 12.0, (roe or -99) >= 7.0),
            "roa": _grade3(roa, (roa or -99) >= 5.0, (roa or -99) >= 3.0),
            "yield_pos": _grade3(yield_range_pos, (yield_range_pos or -1) >= 60.0, (yield_range_pos or -1) >= 20.0, ("割安", "標準", "割高")),
            "fwd_yield": _grade3(forward_yield, (forward_yield or -1) >= 3.0, (forward_yield or -1) >= 1.5),
            "chowder": _grade3(chowder, (chowder or -99) >= 12.0, (chowder or -99) >= 8.0),
            "per_pos": _grade3(per_range_pos, (per_range_pos or -1) >= 60.0, (per_range_pos or -1) >= 20.0, ("割安", "標準", "割高")),
            "per_rel": None,
            "pbr_rel": None,
        },
        "detail": {
            "summary": stock.get("summary", ""),
            "summary_ja": "",
            "analyst": stock.get("analyst", {}),
            "annual_dividends": div_info.get("annual_dividends", []),
            "forward_dividend": div_info.get("forward_dividend"),
            "ttm_dividend": div_info.get("ttm_dividend"),
            "yield_history_min": div_info.get("yield_history_min"),
            "yield_history_max": div_info.get("yield_history_max"),
            "price_series_weekly": price_info.get("price_series_weekly", []),
            "revenue_series": rev_s[:5],
            "eps_series": eps_s[:5],
            "fcf_series": fcf_s[:5],
        },
    }


def score_all_stocks(stocks: list[dict[str, Any]], us10y_yield: float = 4.2) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    """全スクリーニング通過銘柄の選定スコア・買い時スコア・業種級・軍分けを算出する。"""
    items = [_compute_raw_metrics(s, us10y_yield) for s in stocks]

    # セクター別 PER・PBR の中央値（対業種比較用）
    by_sector: dict[str, list[dict[str, Any]]] = {}
    for it in items:
        by_sector.setdefault(it["sector_ja"], []).append(it)

    sector_pe_med: dict[str, float] = {}
    sector_pbr_med: dict[str, float] = {}
    for sec, sec_items in by_sector.items():
        pes = [x["metrics"]["trailing_pe"] for x in sec_items if x["metrics"]["trailing_pe"] is not None]
        pbrs = [x["metrics"]["pbr"] for x in sec_items if x["metrics"]["pbr"] is not None]
        if pes:
            sector_pe_med[sec] = median(pes)
        if pbrs:
            sector_pbr_med[sec] = median(pbrs)

    # 買い時スコア（0〜110点）の算出
    for it in items:
        m = it["metrics"]
        g = it["grades"]
        sec = it["sector_ja"]

        # 対業種 PER / PBR 倍率
        per_rel = None
        if m["trailing_pe"] is not None and sec in sector_pe_med and sector_pe_med[sec] > 0:
            per_rel = round(m["trailing_pe"] / sector_pe_med[sec], 2)
        pbr_rel = None
        if m["pbr"] is not None and sec in sector_pbr_med and sector_pbr_med[sec] > 0:
            pbr_rel = round(m["pbr"] / sector_pbr_med[sec], 2)
        m["per_rel"] = per_rel
        m["pbr_rel"] = pbr_rel
        g["per_rel"] = _grade3(per_rel, (per_rel or 99) <= 0.95, (per_rel or 99) <= 1.20, ("割安", "標準", "割高"))
        g["pbr_rel"] = _grade3(pbr_rel, (pbr_rel or 99) <= 1.00, (pbr_rel or 99) <= 1.40, ("割安", "標準", "割高"))

        s_y_pos = _piecewise(m["yield_range_pos"], [(0, 25), (30, 58), (60, 84), (85, 102), (100, 110)])
        s_fy = _piecewise(m["forward_yield"], [(1.5, 45), (2.5, 68), (3.5, 86), (5.0, 100), (7.0, 110)])
        s_chowder = _piecewise(m["chowder"], [(4, 25), (8, 62), (12, 88), (16, 104), (22, 110)])
        s_per_rel = _piecewise(per_rel, [(0.6, 110), (0.85, 95), (1.0, 80), (1.2, 58), (1.6, 25)])
        s_pbr_rel = _piecewise(pbr_rel, [(0.6, 108), (0.9, 92), (1.1, 78), (1.4, 55), (2.0, 25)])
        s_per_pos = _piecewise(m["per_range_pos"], [(0, 25), (30, 58), (60, 84), (85, 102), (100, 110)])

        buy_pairs: list[tuple[float | None, float]] = [
            (s_y_pos, 0.25),
            (s_fy, 0.15),
            (s_chowder, 0.20),
            (s_per_rel, 0.15),
            (s_pbr_rel, 0.10),
            (s_per_pos, 0.15),
        ]
        # 金利敏感セクターは金利スプレッドも採点
        if sec in RATE_SENSITIVE_SECTORS and m["rate_spread"] is not None:
            s_spread = _piecewise(m["rate_spread"], [(-2.5, 25), (-1.0, 55), (0.0, 80), (1.5, 100), (3.0, 110)])
            buy_pairs.append((s_spread, 0.15))

        buy_raw = _weighted_avg(buy_pairs)
        it["buy_score"] = round(min(110.0, max(0.0, buy_raw)), 1) if buy_raw is not None else None

    # 業種級 & 軍分け（GICSセクター内：上位25%=1軍、続く45%=2軍、残り30%=3軍）
    sector_stats: dict[str, dict[str, Any]] = {}
    small_test_mode = len(items) < 40  # --limit 少数テスト時は6銘柄未満でも軍分けして検証しやすくする

    for sec, sec_items in by_sector.items():
        sec_items.sort(key=lambda x: (x["select_score"] if x["select_score"] is not None else -1.0), reverse=True)
        scores = [x["select_score"] for x in sec_items if x["select_score"] is not None]
        med_score = round(median(scores), 1) if scores else 0.0
        sec_grade = "A" if med_score >= 80.0 else ("B" if med_score >= 70.0 else "C")
        n = len(sec_items)
        sector_stats[sec] = {"count": n, "median": med_score, "grade": sec_grade}

        for idx, it in enumerate(sec_items):
            it["sector_grade"] = sec_grade
            if not small_test_mode and n < 6:
                it["tier"] = 0  # 「―」表示
                continue
            rank_ratio = idx / n
            if rank_ratio < 0.25:
                tier = 1
            elif rank_ratio < 0.70:
                tier = 2
            else:
                tier = 3

            # カバレッジ低は最高2軍まで
            if it["coverage"] == "低" and tier == 1:
                tier = 2
            # 選定スコア85以上は最低2軍保証
            if (it["select_score"] or 0.0) >= 85.0 and tier == 3:
                tier = 2

            it["tier"] = tier

    # 全体の並び順（選定スコア降順）
    items.sort(key=lambda x: (x["select_score"] if x["select_score"] is not None else -1.0), reverse=True)
    return items, sector_stats
