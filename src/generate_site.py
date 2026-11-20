"""採点済み配当株データから ranking.json と静的HTML（index.html）を生成するモジュール。"""

from __future__ import annotations

import html
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .fetch_sp1500 import SECTOR_ORDER

JST = timezone(timedelta(hours=9))


def _fmt_num(val: float | None, digits: int = 1, suffix: str = "") -> str:
    if val is None:
        return "-"
    return f"{val:.{digits}f}{suffix}"


def _fmt_pct(val: float | None, digits: int = 1, plus: bool = True) -> str:
    if val is None:
        return "-"
    sign = "+" if (plus and val > 0) else ""
    return f"{sign}{val:.{digits}f}%"


def _score_cls(val: float | None, high: float = 80.0, mid: float = 65.0) -> str:
    if val is None:
        return ""
    if val >= high:
        return "sc-good"
    if val >= mid:
        return "sc-warn"
    return "sc-weak"


def _ret_cls(val: float | None) -> str:
    if val is None:
        return ""
    if val > 0:
        return "pos"
    if val < 0:
        return "neg"
    return ""


def _tier_badge(tier: int) -> str:
    if tier in (1, 2, 3):
        return f'<span class="tier t{tier}">{tier}軍</span>'
    return '<span class="tier t0">―</span>'


def _build_row_html(
    item: dict[str, Any],
    rank_num: int | None = None,
    include_sector_col: bool = False,
    expand_returns: bool = False,
) -> str:
    m = item["metrics"]
    g = item["grades"]
    r = item.get("returns", {})
    tier = item["tier"]
    sym = html.escape(item["symbol"])
    name = html.escape(item["name"])
    sec_ja = html.escape(item["sector_ja"])

    badges: list[str] = []
    if item.get("is_king"):
        badges.append('<span class="badge-king" title="配当王（50年以上連続増配）">👑王</span>')
    elif item.get("is_aristocrat"):
        badges.append('<span class="badge-aris" title="配当貴族（S&P500 25年以上連続増配）">🏅貴族</span>')
    if item["model"] == "financial":
        badges.append('<span class="badge-model" title="金融専用モデルで採点">金融</span>')
    elif item["model"] == "reit":
        badges.append('<span class="badge-model" title="REIT専用(FFO)モデルで採点">REIT</span>')
    if item.get("warn_reasons"):
        tip = html.escape(" / ".join(item["warn_reasons"]))
        badges.append(f'<span class="badge-warn" title="{tip}">⚠</span>')
    badge_html = " ".join(badges)

    attrs = {
        "data-sym": sym,
        "data-name": name,
        "data-sec": sec_ja,
        "data-tier": str(tier),
        "data-model": item["model"],
        "data-secgrade": item.get("sector_grade", "B"),
        "data-cov": item.get("coverage", "中"),
        "data-decel": "1" if item.get("rapid_decel") else "0",
        "data-king": "1" if item.get("is_king") else "0",
        "data-aris": "1" if item.get("is_aristocrat") else "0",
        "data-s": "" if item["select_score"] is None else str(item["select_score"]),
        "data-b": "" if item["buy_score"] is None else str(item["buy_score"]),
        "data-close": "" if item["close"] is None else str(item["close"]),
        "data-mcap": "" if item["market_cap_m"] is None else str(item["market_cap_m"]),
        "data-fy": "" if m["forward_yield"] is None else str(m["forward_yield"]),
        "data-dcagr": "" if m["div_cagr_5y"] is None else str(m["div_cagr_5y"]),
        "data-cg": str(m.get("consec_growth", 0)),
        "data-nc": str(m.get("non_cut_years", 0)),
        "data-pay": "" if m["payout_ratio"] is None else str(m["payout_ratio"]),
        "data-chowder": "" if m["chowder"] is None else str(m["chowder"]),
        "data-ypos": "" if m["yield_range_pos"] is None else str(m["yield_range_pos"]),
        "data-roe": "" if m["roe"] is None else str(m["roe"]),
        "data-roa": "" if m["roa"] is None else str(m["roa"]),
        "data-ocfpos": "1" if m["ocf_positive"] else "0",
        "data-g-perf": g.get("perf") or "",
        "data-g-fin": g.get("fin") or "",
        "data-g-fcf": g.get("fcf") or "",
        "data-g-fcfpay": g.get("fcf_pay") or "",
        "data-g-dcagr": g.get("div_cagr") or "",
        "data-g-cg": g.get("consec_g") or "",
        "data-g-nc": g.get("non_cut") or "",
        "data-g-pay": g.get("payout") or "",
        "data-g-roe": g.get("roe") or "",
        "data-g-roa": g.get("roa") or "",
        "data-g-ypos": g.get("yield_pos") or "",
        "data-g-fy": g.get("fwd_yield") or "",
        "data-g-chowder": g.get("chowder") or "",
        "data-g-perrel": g.get("per_rel") or "",
        "data-g-pbrrel": g.get("pbr_rel") or "",
        "data-g-perpos": g.get("per_pos") or "",
    }
    attr_str = " ".join(f'{k}="{html.escape(v)}"' for k, v in attrs.items())

    rank_td = f'<td class="num">{rank_num}</td>' if rank_num is not None else ""
    sec_td = f'<td class="sec-cell">{sec_ja}</td>' if include_sector_col else ""

    if expand_returns:
        ret_tds = "".join(
            f'<td class="num {_ret_cls(r.get(k))}">{_fmt_pct(r.get(k), 1)}</td>'
            for k in ("D", "W", "M", "3M", "6M", "9M", "Y")
        )
    else:
        ret_tds = (
            f'<td class="num ret-summary {_ret_cls(r.get("Y"))}">{_fmt_pct(r.get("Y"), 1)}</td>'
            + "".join(
                f'<td class="num ret-col {_ret_cls(r.get(k))}">{_fmt_pct(r.get(k), 1)}</td>'
                for k in ("D", "W", "M", "3M", "6M", "9M", "Y")
            )
        )

    return f"""<tr class="stock-row" {attr_str}>
  <td class="chk-cell"><input type="checkbox" class="wl-chk" data-sym="{sym}" aria-label="{sym} ウォッチリスト"></td>
  <td class="chk-cell"><input type="checkbox" class="pf-chk" data-sym="{sym}" aria-label="{sym} ポートフォリオ"></td>
  {rank_td}
  <td class="tier-cell">{_tier_badge(tier)}</td>
  <td class="sym-cell"><a href="reports/{sym}.html" class="sym-link">{sym}</a></td>
  <td class="name-cell"><a href="reports/{sym}.html" class="name-link">{name}</a> {badge_html}</td>
  {sec_td}
  <td class="num">{_fmt_num(item["close"], 2, "$")}</td>
  {ret_tds}
  <td class="num score-cell {_score_cls(item["select_score"], 85, 68)}">{_fmt_num(item["select_score"], 1)}</td>
  <td class="num score-cell {_score_cls(item["buy_score"], 90, 70)}">{_fmt_num(item["buy_score"], 1)}</td>
  <td class="num">{_fmt_num(m["forward_yield"], 2, "%")}</td>
  <td class="num {_ret_cls(m["div_cagr_5y"])}">{_fmt_pct(m["div_cagr_5y"], 1)}</td>
  <td class="num">{_fmt_num(m["roe"], 1, "%")}</td>
  <td class="num">{_fmt_num(m["roa"], 1, "%")}</td>
  <td class="cov-cell"><span class="cov cov-{item["coverage"]}">{item["coverage"]}</span></td>
</tr>"""


def _build_special_table(items: list[dict[str, Any]], table_id: str) -> str:
    rows = "\n".join(_build_row_html(it, rank_num=i + 1, include_sector_col=True, expand_returns=True) for i, it in enumerate(items))
    return f"""<div class="table-wrap">
<table class="rank-table special-table" id="{table_id}">
<thead>
<tr>
  <th class="chk-col">☆</th>
  <th class="chk-col">💼</th>
  <th class="num">#</th>
  <th>軍</th>
  <th>ティッカー</th>
  <th>銘柄</th>
  <th>業種</th>
  <th class="num">終値</th>
  <th class="num">D</th><th class="num">W</th><th class="num">M</th><th class="num">3M</th><th class="num">6M</th><th class="num">9M</th><th class="num">Y</th>
  <th class="num">選定</th>
  <th class="num">買い時</th>
  <th class="num">利回り</th>
  <th class="num">増配</th>
  <th class="num">ROE</th>
  <th class="num">ROA</th>
  <th>カバレッジ</th>
</tr>
</thead>
<tbody>
{rows}
</tbody>
</table>
</div>"""


def generate_site(
    items: list[dict[str, Any]],
    sector_stats: dict[str, dict[str, Any]],
    dist_dir: Path,
    us10y_yield: float = 4.2,
    excluded_kings: list[dict[str, Any]] | None = None,
    excluded_aristocrats: list[dict[str, Any]] | None = None,
) -> Path:
    """dist/ranking.json と dist/index.html を生成する。"""
    dist_dir.mkdir(parents=True, exist_ok=True)
    now_jst = datetime.now(JST)
    generated_at = now_jst.strftime("%Y-%m-%d %H:%M JST")
    latest_dates = [it["latest_date"] for it in items if it.get("latest_date")]
    latest_price_date = max(latest_dates) if latest_dates else "-"

    excluded_kings = excluded_kings or []
    excluded_aristocrats = excluded_aristocrats or []

    # 1. ranking.json 保存
    ranking_payload = {
        "generated_at": generated_at,
        "latest_price_date": latest_price_date,
        "us10y_yield": us10y_yield,
        "count": len(items),
        "sector_stats": sector_stats,
        "items": [
            {
                "symbol": it["symbol"],
                "name": it["name"],
                "sector_ja": it["sector_ja"],
                "sector_grade": it.get("sector_grade", "B"),
                "tier": it["tier"],
                "model": it["model"],
                "is_king": it.get("is_king", False),
                "is_aristocrat": it.get("is_aristocrat", False),
                "close": it["close"],
                "market_cap_m": it["market_cap_m"],
                "select_score": it["select_score"],
                "buy_score": it["buy_score"],
                "coverage": it["coverage"],
                "forward_yield": it["metrics"]["forward_yield"],
                "forward_dividend": it["detail"].get("forward_dividend"),
                "div_cagr_5y": it["metrics"]["div_cagr_5y"],
                "consec_growth": it["metrics"]["consec_growth"],
                "non_cut_years": it["metrics"]["non_cut_years"],
                "chowder": it["metrics"]["chowder"],
                "roe": it["metrics"]["roe"],
                "roa": it["metrics"]["roa"],
                "warn_reasons": it.get("warn_reasons", []),
            }
            for it in items
        ],
    }
    (dist_dir / "ranking.json").write_text(
        json.dumps(ranking_payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # 集計
    t1_cnt = sum(1 for it in items if it["tier"] == 1)
    t2_cnt = sum(1 for it in items if it["tier"] == 2)
    t3_cnt = sum(1 for it in items if it["tier"] == 3)
    t0_cnt = sum(1 for it in items if it["tier"] == 0)

    top50 = items[:50]
    kings = [it for it in items if it.get("is_king")]
    aristocrats = [it for it in items if it.get("is_aristocrat")]

    # 業種別セクション構築
    by_sector: dict[str, list[dict[str, Any]]] = {}
    for it in items:
        by_sector.setdefault(it["sector_ja"], []).append(it)

    ordered_sectors = [s for s in SECTOR_ORDER if s in by_sector] + [s for s in by_sector if s not in SECTOR_ORDER]
    sector_sections_html: list[str] = []
    for sec in ordered_sectors:
        sec_items = sorted(by_sector[sec], key=lambda x: (x["select_score"] if x["select_score"] is not None else -1.0), reverse=True)
        st = sector_stats.get(sec, {"count": len(sec_items), "median": 0.0, "grade": "B"})
        rows_html = "\n".join(_build_row_html(it, include_sector_col=False, expand_returns=False) for it in sec_items)
        sec_esc = html.escape(sec)
        sector_sections_html.append(f"""
<section class="sector-block" data-sector="{sec_esc}">
  <div class="sector-head">
    <h2>{sec_esc}</h2>
    <div class="sector-meta">
      <span class="sec-grade sg-{st['grade']}">業種級 {st['grade']}</span>
      <span>中央値 {st['median']:.1f}</span>
      <span class="sec-count">{len(sec_items)} 銘柄</span>
    </div>
  </div>
  <div class="table-wrap">
  <table class="rank-table sector-table">
    <thead>
      <tr>
        <th class="chk-col">☆</th>
        <th class="chk-col">💼</th>
        <th class="sortable" data-sort="tier">軍</th>
        <th class="sortable" data-sort="sym">ティッカー</th>
        <th class="sortable" data-sort="name">銘柄</th>
        <th class="num sortable" data-sort="close">終値</th>
        <th class="num ret-toggle-th"><button type="button" class="ret-toggle-btn">騰落率(展開)</button></th>
        <th class="num ret-col">D</th><th class="num ret-col">W</th><th class="num ret-col">M</th><th class="num ret-col">3M</th><th class="num ret-col">6M</th><th class="num ret-col">9M</th><th class="num ret-col">Y</th>
        <th class="num sortable" data-sort="s">選定 ▼</th>
        <th class="num sortable" data-sort="b">買い時</th>
        <th class="num sortable" data-sort="fy">利回り</th>
        <th class="num sortable" data-sort="dcagr">増配</th>
        <th class="num sortable" data-sort="roe">ROE</th>
        <th class="num sortable" data-sort="roa">ROA</th>
        <th class="sortable" data-sort="cov">カバレッジ</th>
      </tr>
    </thead>
    <tbody>
      {rows_html}
    </tbody>
  </table>
  </div>
</section>""")

    sector_options = "".join(f'<option value="{html.escape(s)}">{html.escape(s)}</option>' for s in ordered_sectors)

    def _excluded_list_html(ex_list: list[dict[str, Any]]) -> str:
        if not ex_list:
            return ""
        lis = "".join(
            f'<li><strong>{html.escape(x["symbol"])}</strong> ({html.escape(x["name"])}) — {html.escape(x.get("screen_reason", "条件外"))}</li>'
            for x in ex_list
        )
        return f'<details class="sub-details"><summary>条件対象外となった銘柄（{len(ex_list)}件）</summary><ul class="ex-list">{lis}</ul></details>'

    html_doc = f"""<!DOCTYPE html>
<html lang="ja" data-theme="genko" data-mode="light">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>米国株 配当株 軍分けランキング</title>
<style>
:root {{
  --bg: #f8fafc; --surface: #ffffff; --surface2: #f1f5f9; --text: #0f172a; --muted: #475569;
  --border: #e2e8f0; --accent: #1d4ed8; --accent-soft: #dbeafe; --good: #15803d; --good-bg: #dcfce7;
  --warn: #b45309; --warn-bg: #fef3c7; --weak: #b91c1c; --weak-bg: #fee2e2;
}}
[data-theme="blueplus"] {{ --accent: #0284c7; --accent-soft: #e0f2fe; }}
[data-theme="teal"] {{ --accent: #0f766e; --accent-soft: #ccfbf1; }}
[data-theme="slate"] {{ --accent: #334155; --accent-soft: #e2e8f0; }}
[data-theme="sand"] {{ --accent: #b45309; --accent-soft: #fef3c7; }}
[data-theme="violet"] {{ --accent: #6d28d9; --accent-soft: #ede9fe; }}
[data-theme="rose"] {{ --accent: #be123c; --accent-soft: #ffe4e6; }}
[data-mode="dark"] {{
  --bg: #0b1120; --surface: #111827; --surface2: #1e293b; --text: #f1f5f9; --muted: #94a3b8;
  --border: #334155; --accent-soft: #1e3a5f; --good: #4ade80; --good-bg: #14532d;
  --warn: #fbbf24; --warn-bg: #451a03; --weak: #f87171; --weak-bg: #450a0a;
}}
* {{ box-sizing: border-box; }}
body {{ margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Hiragino Kaku Gothic ProN", "Yu Gothic", sans-serif; background: var(--bg); color: var(--text); font-size: 14px; line-height: 1.5; padding-bottom: 70px; }}
a {{ color: var(--accent); text-decoration: none; }}
a:hover {{ text-decoration: underline; }}

#theme-bar {{ display: flex; flex-wrap: wrap; align-items: center; gap: 6px; padding: 6px 16px; background: var(--surface2); border-bottom: 1px solid var(--border); font-size: 12px; }}
.theme-btn {{ border: 1px solid var(--border); background: var(--surface); color: var(--text); border-radius: 999px; padding: 2px 10px; cursor: pointer; font-size: 12px; }}
.theme-btn.active {{ background: var(--accent); color: #fff; border-color: var(--accent); }}

header {{ background: var(--surface); border-bottom: 1px solid var(--border); padding: 16px; }}
.header-inner {{ max-width: 1380px; margin: 0 auto; }}
.header-top {{ display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: 12px; }}
h1 {{ margin: 0; font-size: 22px; }}
.nav-links {{ display: flex; flex-wrap: wrap; gap: 8px; }}
.nav-btn {{ display: inline-flex; align-items: center; gap: 4px; padding: 6px 12px; border-radius: 8px; border: 1px solid var(--border); background: var(--surface2); color: var(--text); font-size: 13px; font-weight: 600; }}
.nav-btn:hover {{ background: var(--accent-soft); text-decoration: none; }}
.meta-bar {{ margin-top: 8px; color: var(--muted); font-size: 12px; display: flex; flex-wrap: wrap; gap: 14px; }}

main {{ max-width: 1380px; margin: 0 auto; padding: 16px; }}

.tier-bar {{ display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 12px; }}
.tier-filter {{ border: 1px solid var(--border); background: var(--surface); color: var(--text); padding: 7px 14px; border-radius: 10px; cursor: pointer; font-weight: 700; font-size: 13px; }}
.tier-filter.active {{ background: var(--accent); color: #fff; border-color: var(--accent); }}

.toolbar {{ display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-bottom: 12px; background: var(--surface); padding: 10px 12px; border: 1px solid var(--border); border-radius: 10px; }}
.toolbar input[type="search"] {{ flex: 1; min-width: 220px; padding: 7px 10px; border: 1px solid var(--border); border-radius: 8px; background: var(--bg); color: var(--text); }}
.btn {{ border: 1px solid var(--border); background: var(--surface2); color: var(--text); padding: 7px 12px; border-radius: 8px; cursor: pointer; font-size: 13px; font-weight: 600; }}
.btn:hover {{ background: var(--accent-soft); }}
.btn-primary {{ background: var(--accent); color: #fff; border-color: var(--accent); }}
.hit-count {{ font-weight: 700; color: var(--accent); margin-left: auto; }}

details.panel {{ background: var(--surface); border: 1px solid var(--border); border-radius: 10px; margin-bottom: 12px; padding: 10px 14px; }}
details.panel > summary {{ cursor: pointer; font-weight: 700; font-size: 14px; list-style: none; display: flex; align-items: center; gap: 8px; }}
details.panel > summary::before {{ content: "▶"; font-size: 11px; transition: transform .15s; }}
details.panel[open] > summary::before {{ transform: rotate(90deg); }}
.sub-details {{ margin-top: 10px; padding: 8px 10px; background: var(--surface2); border-radius: 8px; }}
.sub-details > summary {{ cursor: pointer; font-weight: 600; font-size: 13px; }}
.ex-list {{ margin: 8px 0 0 18px; font-size: 12px; color: var(--muted); columns: 2; }}

.filter-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(210px, 1fr)); gap: 10px; margin-top: 10px; }}
.f-item {{ display: flex; flex-direction: column; gap: 4px; font-size: 12px; }}
.f-item label {{ font-weight: 600; color: var(--muted); }}
.f-item input, .f-item select {{ padding: 6px 8px; border: 1px solid var(--border); border-radius: 6px; background: var(--bg); color: var(--text); }}
.f-checks {{ display: flex; flex-wrap: wrap; gap: 12px; margin-top: 10px; font-size: 13px; }}

.sector-block {{ background: var(--surface); border: 1px solid var(--border); border-radius: 10px; margin-bottom: 16px; overflow: hidden; }}
.sector-head {{ display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; padding: 10px 14px; background: var(--surface2); border-bottom: 1px solid var(--border); }}
.sector-head h2 {{ margin: 0; font-size: 16px; }}
.sector-meta {{ display: flex; gap: 10px; align-items: center; font-size: 12px; color: var(--muted); font-weight: 600; }}
.sec-grade {{ padding: 2px 8px; border-radius: 6px; font-weight: 700; }}
.sg-A {{ background: var(--good-bg); color: var(--good); }}
.sg-B {{ background: var(--accent-soft); color: var(--accent); }}
.sg-C {{ background: var(--warn-bg); color: var(--warn); }}

.table-wrap {{ overflow-x: auto; }}
table.rank-table {{ width: 100%; border-collapse: collapse; font-size: 13px; white-space: nowrap; }}
table.rank-table th, table.rank-table td {{ padding: 7px 8px; border-bottom: 1px solid var(--border); text-align: left; }}
table.rank-table th {{ background: var(--surface2); font-size: 12px; color: var(--muted); position: sticky; top: 0; z-index: 1; }}
table.rank-table th.sortable {{ cursor: pointer; }}
table.rank-table th.sortable:hover {{ color: var(--accent); }}
table.rank-table tbody tr:hover {{ background: var(--surface2); }}
.num {{ text-align: right !important; font-variant-numeric: tabular-nums; }}
.chk-col, .chk-cell {{ width: 32px; text-align: center !important; }}
.sym-link {{ font-weight: 700; }}
.name-link {{ color: var(--text); }}
.tier {{ display: inline-block; padding: 2px 7px; border-radius: 6px; font-weight: 700; font-size: 12px; }}
.t1 {{ background: var(--good-bg); color: var(--good); }}
.t2 {{ background: var(--accent-soft); color: var(--accent); }}
.t3 {{ background: var(--surface2); color: var(--muted); }}
.t0 {{ background: var(--surface2); color: var(--muted); }}
.score-cell {{ font-weight: 700; }}
.sc-good {{ color: var(--good); }}
.sc-warn {{ color: var(--warn); }}
.sc-weak {{ color: var(--weak); }}
.pos {{ color: var(--good); }}
.neg {{ color: var(--weak); }}
.badge-king {{ background: #fef08a; color: #854d0e; font-size: 11px; padding: 1px 5px; border-radius: 4px; font-weight: 700; }}
.badge-aris {{ background: #e0e7ff; color: #3730a3; font-size: 11px; padding: 1px 5px; border-radius: 4px; font-weight: 700; }}
.badge-model {{ background: var(--surface2); color: var(--muted); font-size: 11px; padding: 1px 5px; border-radius: 4px; border: 1px solid var(--border); }}
.badge-warn {{ background: var(--warn-bg); color: var(--warn); font-size: 11px; padding: 1px 5px; border-radius: 4px; font-weight: 700; }}
.cov {{ font-size: 11px; padding: 1px 6px; border-radius: 4px; font-weight: 700; }}
.cov-高 {{ background: var(--good-bg); color: var(--good); }}
.cov-中 {{ background: var(--accent-soft); color: var(--accent); }}
.cov-低 {{ background: var(--warn-bg); color: var(--warn); }}

.ret-col {{ display: none; }}
.returns-expanded .ret-col {{ display: table-cell; }}
.returns-expanded .ret-summary {{ display: none; }}
.ret-toggle-btn {{ border: 1px solid var(--border); background: var(--surface); color: var(--accent); border-radius: 5px; padding: 2px 6px; font-size: 11px; cursor: pointer; }}

#wlbar {{ position: fixed; bottom: 0; left: 0; right: 0; background: var(--surface); border-top: 2px solid var(--accent); padding: 10px 16px; display: none; align-items: center; gap: 12px; justify-content: center; z-index: 50; box-shadow: 0 -4px 12px rgba(0,0,0,.1); }}
#wlbar.show {{ display: flex; }}
@media (max-width: 768px) {{
  .ex-list {{ columns: 1; }}
  h1 {{ font-size: 18px; }}
}}
</style>
</head>
<body>
<div id="hub-portal-bar" style="background:#0f172a;color:#e2e8f0;padding:7px 14px;display:flex;flex-wrap:wrap;align-items:center;gap:6px;font-size:12px;border-bottom:1px solid #1e293b;"><a href="https://elj3538.github.io/" style="color:#cbd5e1;background:transparent;padding:4px 10px;border-radius:6px;text-decoration:none;font-weight:600;white-space:nowrap;">🏠 ポータル</a><a href="https://elj3538.github.io/us-long-screener/" style="color:#cbd5e1;background:transparent;padding:4px 10px;border-radius:6px;text-decoration:none;font-weight:600;white-space:nowrap;">🇺🇸 米国10年保有</a><a href="https://elj3538.github.io/us-dividend-screener/" style="color:#ffffff;background:#2563eb;padding:4px 10px;border-radius:6px;text-decoration:none;font-weight:600;white-space:nowrap;">🇺🇸 米国配当株</a><a href="https://elj3538.github.io/jp-long-screener/" style="color:#cbd5e1;background:transparent;padding:4px 10px;border-radius:6px;text-decoration:none;font-weight:600;white-space:nowrap;">🇯🇵 日本10年保有</a><a href="https://elj3538.github.io/jp-dividend-screener/" style="color:#cbd5e1;background:transparent;padding:4px 10px;border-radius:6px;text-decoration:none;font-weight:600;white-space:nowrap;">🇯🇵 日本配当株</a></div>
<div id="theme-bar">
  <span>テーマ:</span>
  <button class="theme-btn" data-set-theme="genko">標準</button>
  <button class="theme-btn" data-set-theme="blueplus">ブルー</button>
  <button class="theme-btn" data-set-theme="teal">ティール</button>
  <button class="theme-btn" data-set-theme="slate">スレート</button>
  <button class="theme-btn" data-set-theme="sand">サンド</button>
  <button class="theme-btn" data-set-theme="violet">バイオレット</button>
  <button class="theme-btn" data-set-theme="rose">ローズ</button>
  <button class="theme-btn" id="mode-toggle" style="margin-left:auto;">🌙 ダーク切替</button>
</div>

<header>
  <div class="header-inner">
    <div class="header-top">
      <h1>米国株 配当株 軍分けランキング</h1>
      <nav class="nav-links">
        <a class="nav-btn" href="guide.html">📖 使い方・見方</a>
        <a class="nav-btn" href="watchlist.html">☆ ウォッチリスト</a>
        <a class="nav-btn" href="portfolio.html">💼 ポートフォリオ</a>
        <a class="nav-btn" href="terms.html">📜 利用規約・免責</a>
      </nav>
    </div>
    <div class="meta-bar">
      <span>更新: {generated_at}</span>
      <span>株価基準日: {latest_price_date}</span>
      <span>対象: S&amp;P 1500（実績利回り ≥ 1.5%・3年平均 ≥ 1.2%・直近5年減配なし）</span>
      <span>米10年国債利回り: {us10y_yield:.2f}%</span>
    </div>
  </div>
</header>

<main>
  <div class="tier-bar">
    <button class="tier-filter active" data-tier="all">{len(items)} 全銘柄</button>
    <button class="tier-filter" data-tier="1">{t1_cnt} 1軍</button>
    <button class="tier-filter" data-tier="2">{t2_cnt} 2軍</button>
    <button class="tier-filter" data-tier="3">{t3_cnt} 3軍</button>
    {f'<button class="tier-filter" data-tier="0">{t0_cnt} 軍分けなし</button>' if t0_cnt else ''}
  </div>

  <div class="toolbar">
    <input type="search" id="search-input" placeholder="ティッカー・銘柄名・業種で検索 (例: JNJ, KO, 生活必需品)">
    <button class="btn" id="clear-btn">クリア</button>
    <button class="btn" id="csv-btn">📥 CSV出力</button>
    <button class="btn" id="tsv-btn">📋 コピー</button>
    <span class="hit-count" id="hit-count">{len(items)} 件表示</span>
  </div>

  <details class="panel" id="screener-panel">
    <summary>🔍 詳しい条件で絞り込む（詳細スクリーナー）</summary>
    <div class="filter-grid">
      <div class="f-item"><label>選定スコア 以上</label><input type="number" id="f-s-min" placeholder="例: 80" step="1"></div>
      <div class="f-item"><label>買い時スコア 以上</label><input type="number" id="f-b-min" placeholder="例: 75" step="1"></div>
      <div class="f-item"><label>予想配当利回り(%) 以上</label><input type="number" id="f-fy-min" placeholder="例: 3.0" step="0.1"></div>
      <div class="f-item"><label>5年増配率(%) 以上</label><input type="number" id="f-dcagr-min" placeholder="例: 5.0" step="0.5"></div>
      <div class="f-item"><label>連続増配年数 以上</label><input type="number" id="f-cg-min" placeholder="例: 10" step="1"></div>
      <div class="f-item"><label>連続非減配年数 以上</label><input type="number" id="f-nc-min" placeholder="例: 15" step="1"></div>
      <div class="f-item"><label>配当性向(%) 以下</label><input type="number" id="f-pay-max" placeholder="例: 70" step="5"></div>
      <div class="f-item"><label>Chowderルール(%) 以上</label><input type="number" id="f-chowder-min" placeholder="例: 12" step="1"></div>
      <div class="f-item"><label>利回りレンジ位置(%) 以上</label><input type="number" id="f-ypos-min" placeholder="例: 60" step="5"></div>
      <div class="f-item"><label>ROE(%) 以上</label><input type="number" id="f-roe-min" placeholder="例: 12" step="1"></div>
      <div class="f-item"><label>ROA(%) 以上 (採点外)</label><input type="number" id="f-roa-min" placeholder="例: 5" step="1"></div>
      <div class="f-item"><label>時価総額(百万$) 以上</label><input type="number" id="f-mcap-min" placeholder="例: 10000" step="1000"></div>
      <div class="f-item"><label>終値($) 以下</label><input type="number" id="f-close-max" placeholder="例: 150" step="10"></div>
      <div class="f-item"><label>業種</label><select id="f-sec"><option value="">すべて</option>{sector_options}</select></div>
      <div class="f-item"><label>業種級</label><select id="f-secgrade"><option value="">すべて</option><option value="A">A</option><option value="B">B</option><option value="C">C</option></select></div>
      <div class="f-item"><label>カバレッジ</label><select id="f-cov"><option value="">すべて</option><option value="高">高</option><option value="中">中</option><option value="低">低</option></select></div>
      <div class="f-item"><label>業種区分</label><select id="f-model"><option value="">すべて</option><option value="general">一般企業のみ</option><option value="special">金融・REITのみ</option></select></div>
    </div>
    <div class="f-checks">
      <label><input type="checkbox" id="f-no-decel"> 直近四半期の急減速なしのみ</label>
      <label><input type="checkbox" id="f-ocf-pos"> 営業CFプラスのみ</label>
      <label><input type="checkbox" id="f-king-only"> 👑 配当王のみ</label>
      <label><input type="checkbox" id="f-aris-only"> 🏅 配当貴族のみ</label>
      <button class="btn" id="reset-filters" style="margin-left:auto;">条件をリセット</button>
    </div>
  </details>

  <details class="panel">
    <summary>💾 バックアップ（CSV）— ウォッチリスト・ポートフォリオ保存/復元</summary>
    <div style="margin-top:10px; display:flex; flex-wrap:wrap; gap:10px; align-items:center;">
      <button class="btn" id="backup-export">バックアップをJSON保存</button>
      <label class="btn" style="cursor:pointer;">JSONから復元 <input type="file" id="backup-import" accept=".json" style="display:none;"></label>
    </div>
  </details>

  <details class="panel">
    <summary>🏆 全体 選定スコア 上位50（業種横断）</summary>
    <div style="margin-top:10px;">{_build_special_table(top50, "top50-table")}</div>
  </details>

  <details class="panel">
    <summary>👑 配当王（50年以上連続増配・{len(kings)}銘柄）</summary>
    <div style="margin-top:10px;">
      {_build_special_table(kings, "kings-table") if kings else '<p style="color:var(--muted);">該当銘柄なし</p>'}
      {_excluded_list_html(excluded_kings)}
    </div>
  </details>

  <details class="panel">
    <summary>🏅 配当貴族（S&amp;P 500 25年以上連続増配・{len(aristocrats)}銘柄）</summary>
    <div style="margin-top:10px;">
      {_build_special_table(aristocrats, "aris-table") if aristocrats else '<p style="color:var(--muted);">該当銘柄なし</p>'}
      {_excluded_list_html(excluded_aristocrats)}
    </div>
  </details>

  <div id="sectors-container">
    {"".join(sector_sections_html)}
  </div>
</main>

<div id="wlbar">
  <span id="wlbar-count">0 銘柄選択中</span>
  <button class="btn btn-primary" id="wlbar-save">選択を保存</button>
  <a class="btn" href="watchlist.html">☆ ウォッチリストを見る</a>
  <a class="btn" href="portfolio.html">💼 ポートフォリオを見る</a>
</div>

<script>
(function() {{
  const LS_THEME = "pp_theme_us_div";
  const LS_MODE = "pp_mode_us_div";
  const LS_WL = "pp_watchlist_us_div";
  const LS_PF = "pp_portfolio_us_div";

  // テーマ・ダークモード
  function applyTheme(t) {{
    document.documentElement.setAttribute("data-theme", t);
    localStorage.setItem(LS_THEME, t);
    document.querySelectorAll("[data-set-theme]").forEach(b => b.classList.toggle("active", b.dataset.setTheme === t));
  }}
  function applyMode(m) {{
    document.documentElement.setAttribute("data-mode", m);
    localStorage.setItem(LS_MODE, m);
  }}
  applyTheme(localStorage.getItem(LS_THEME) || "genko");
  applyMode(localStorage.getItem(LS_MODE) || "light");
  document.querySelectorAll("[data-set-theme]").forEach(b => b.addEventListener("click", () => applyTheme(b.dataset.setTheme)));
  document.getElementById("mode-toggle").addEventListener("click", () => {{
    applyMode(document.documentElement.getAttribute("data-mode") === "dark" ? "light" : "dark");
  }});

  // ウォッチリスト・ポートフォリオ同期
  let wlSet = new Set(JSON.parse(localStorage.getItem(LS_WL) || "[]"));
  let pfObj = JSON.parse(localStorage.getItem(LS_PF) || "{{}}");

  function syncChecks() {{
    document.querySelectorAll(".wl-chk").forEach(cb => cb.checked = wlSet.has(cb.dataset.sym));
    document.querySelectorAll(".pf-chk").forEach(cb => cb.checked = Boolean(pfObj[cb.dataset.sym]));
    const total = wlSet.size + Object.keys(pfObj).length;
    document.getElementById("wlbar-count").textContent = `☆ ${{wlSet.size}}件 / 💼 ${{Object.keys(pfObj).length}}件 登録中`;
    document.getElementById("wlbar").classList.toggle("show", total > 0);
  }}
  document.addEventListener("change", (e) => {{
    if (e.target.classList.contains("wl-chk")) {{
      const s = e.target.dataset.sym;
      if (e.target.checked) wlSet.add(s); else wlSet.delete(s);
      localStorage.setItem(LS_WL, JSON.stringify([...wlSet]));
      syncChecks();
    }} else if (e.target.classList.contains("pf-chk")) {{
      const s = e.target.dataset.sym;
      if (e.target.checked) {{ if (!pfObj[s]) pfObj[s] = {{ shares: 10 }}; }}
      else {{ delete pfObj[s]; }}
      localStorage.setItem(LS_PF, JSON.stringify(pfObj));
      syncChecks();
    }}
  }});
  document.getElementById("wlbar-save").addEventListener("click", () => {{
    localStorage.setItem(LS_WL, JSON.stringify([...wlSet]));
    localStorage.setItem(LS_PF, JSON.stringify(pfObj));
    alert("ブラウザに保存しました！");
  }});
  syncChecks();

  // バックアップ
  document.getElementById("backup-export").addEventListener("click", () => {{
    const blob = new Blob([JSON.stringify({{ watchlist: [...wlSet], portfolio: pfObj }}, null, 2)], {{ type: "application/json" }});
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "us_dividend_backup.json";
    a.click();
  }});
  document.getElementById("backup-import").addEventListener("change", (e) => {{
    const file = e.target.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {{
      try {{
        const data = JSON.parse(reader.result);
        if (Array.isArray(data.watchlist)) wlSet = new Set(data.watchlist);
        if (data.portfolio && typeof data.portfolio === "object") pfObj = data.portfolio;
        localStorage.setItem(LS_WL, JSON.stringify([...wlSet]));
        localStorage.setItem(LS_PF, JSON.stringify(pfObj));
        syncChecks();
        alert("バックアップを復元しました！");
      }} catch (err) {{ alert("読み込みに失敗しました: " + err); }}
    }};
    reader.readAsText(file);
  }});

  // 騰落率展開トグル
  document.querySelectorAll(".ret-toggle-btn").forEach(btn => {{
    btn.addEventListener("click", () => {{
      const tbl = btn.closest("table");
      tbl.classList.toggle("returns-expanded");
      btn.textContent = tbl.classList.contains("returns-expanded") ? "騰落率(閉じる)" : "騰落率(展開)";
    }});
  }});

  // フィルタリング
  let currentTier = "all";
  const numVal = (id) => {{ const v = document.getElementById(id).value; return v === "" ? null : parseFloat(v); }};

  function applyFilters() {{
    const q = document.getElementById("search-input").value.trim().toLowerCase();
    const sMin = numVal("f-s-min"), bMin = numVal("f-b-min"), fyMin = numVal("f-fy-min");
    const dcMin = numVal("f-dcagr-min"), cgMin = numVal("f-cg-min"), ncMin = numVal("f-nc-min");
    const payMax = numVal("f-pay-max"), chMin = numVal("f-chowder-min"), ypMin = numVal("f-ypos-min");
    const roeMin = numVal("f-roe-min"), roaMin = numVal("f-roa-min"), mcMin = numVal("f-mcap-min"), clMax = numVal("f-close-max");
    const fSec = document.getElementById("f-sec").value;
    const fSg = document.getElementById("f-secgrade").value;
    const fCov = document.getElementById("f-cov").value;
    const fMod = document.getElementById("f-model").value;
    const noDecel = document.getElementById("f-no-decel").checked;
    const ocfPos = document.getElementById("f-ocf-pos").checked;
    const kingOnly = document.getElementById("f-king-only").checked;
    const arisOnly = document.getElementById("f-aris-only").checked;

    let visibleCount = 0;
    document.querySelectorAll(".sector-block").forEach(secBlock => {{
      let secVis = 0;
      secBlock.querySelectorAll("tbody tr.stock-row").forEach(tr => {{
        const d = tr.dataset;
        let ok = true;
        if (currentTier !== "all" && d.tier !== currentTier) ok = false;
        if (ok && q && !(d.sym.toLowerCase().includes(q) || d.name.toLowerCase().includes(q) || d.sec.toLowerCase().includes(q))) ok = false;
        if (ok && sMin !== null && (d.s === "" || parseFloat(d.s) < sMin)) ok = false;
        if (ok && bMin !== null && (d.b === "" || parseFloat(d.b) < bMin)) ok = false;
        if (ok && fyMin !== null && (d.fy === "" || parseFloat(d.fy) < fyMin)) ok = false;
        if (ok && dcMin !== null && (d.dcagr === "" || parseFloat(d.dcagr) < dcMin)) ok = false;
        if (ok && cgMin !== null && parseFloat(d.cg) < cgMin) ok = false;
        if (ok && ncMin !== null && parseFloat(d.nc) < ncMin) ok = false;
        if (ok && payMax !== null && (d.pay === "" || parseFloat(d.pay) > payMax)) ok = false;
        if (ok && chMin !== null && (d.chowder === "" || parseFloat(d.chowder) < chMin)) ok = false;
        if (ok && ypMin !== null && (d.ypos === "" || parseFloat(d.ypos) < ypMin)) ok = false;
        if (ok && roeMin !== null && (d.roe === "" || parseFloat(d.roe) < roeMin)) ok = false;
        if (ok && roaMin !== null && (d.roa === "" || parseFloat(d.roa) < roaMin)) ok = false;
        if (ok && mcMin !== null && (d.mcap === "" || parseFloat(d.mcap) < mcMin)) ok = false;
        if (ok && clMax !== null && (d.close === "" || parseFloat(d.close) > clMax)) ok = false;
        if (ok && fSec && d.sec !== fSec) ok = false;
        if (ok && fSg && d.secgrade !== fSg) ok = false;
        if (ok && fCov && d.cov !== fCov) ok = false;
        if (ok && fMod === "general" && d.model !== "general") ok = false;
        if (ok && fMod === "special" && d.model === "general") ok = false;
        if (ok && noDecel && d.decel === "1") ok = false;
        if (ok && ocfPos && d.ocfpos !== "1") ok = false;
        if (ok && kingOnly && d.king !== "1") ok = false;
        if (ok && arisOnly && d.aris !== "1") ok = false;

        tr.style.display = ok ? "" : "none";
        if (ok) {{ secVis++; visibleCount++; }}
      }});
      secBlock.style.display = secVis > 0 ? "" : "none";
      const cntEl = secBlock.querySelector(".sec-count");
      if (cntEl) cntEl.textContent = `${{secVis}} 銘柄`;
    }});
    document.getElementById("hit-count").textContent = `${{visibleCount}} 件表示`;
  }}

  document.querySelectorAll(".tier-filter").forEach(b => {{
    b.addEventListener("click", () => {{
      currentTier = b.dataset.tier;
      document.querySelectorAll(".tier-filter").forEach(x => x.classList.toggle("active", x === b));
      applyFilters();
    }});
  }});
  document.getElementById("search-input").addEventListener("input", applyFilters);
  document.querySelectorAll("#screener-panel input, #screener-panel select").forEach(el => el.addEventListener("input", applyFilters));
  document.getElementById("clear-btn").addEventListener("click", () => {{ document.getElementById("search-input").value = ""; applyFilters(); }});
  document.getElementById("reset-filters").addEventListener("click", () => {{
    document.querySelectorAll("#screener-panel input[type=number], #screener-panel select").forEach(el => el.value = "");
    document.querySelectorAll("#screener-panel input[type=checkbox]").forEach(el => el.checked = false);
    applyFilters();
  }});

  // テーブルソート
  document.querySelectorAll(".sector-table th.sortable").forEach(th => {{
    let asc = false;
    th.addEventListener("click", () => {{
      const key = th.dataset.sort;
      asc = !asc;
      const tbody = th.closest("table").querySelector("tbody");
      const rows = Array.from(tbody.querySelectorAll("tr.stock-row"));
      rows.sort((a, b) => {{
        const va = a.dataset[key] || "", vb = b.dataset[key] || "";
        const na = parseFloat(va), nb = parseFloat(vb);
        if (!isNaN(na) && !isNaN(nb)) return asc ? na - nb : nb - na;
        return asc ? va.localeCompare(vb) : vb.localeCompare(va);
      }});
      rows.forEach(r => tbody.appendChild(r));
    }});
  }});

  // CSV / TSV 出力
  function collectVisibleRows() {{
    const header = ["軍", "ティッカー", "銘柄", "業種", "終値", "選定スコア", "買い時スコア", "予想利回り%", "5年増配率%", "連続増配年", "ROE%", "ROA%", "カバレッジ"];
    const out = [header];
    document.querySelectorAll(".sector-block tbody tr.stock-row").forEach(tr => {{
      if (tr.style.display === "none") return;
      const d = tr.dataset;
      out.push([d.tier === "0" ? "-" : d.tier + "軍", d.sym, d.name, d.sec, d.close, d.s, d.b, d.fy, d.dcagr, d.cg, d.roe, d.roa, d.cov]);
    }});
    return out;
  }}
  document.getElementById("csv-btn").addEventListener("click", () => {{
    const csv = "\\uFEFF" + collectVisibleRows().map(r => r.map(v => `"${{String(v).replace(/"/g, '""')}}"`).join(",")).join("\\n");
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([csv], {{ type: "text/csv;charset=utf-8;" }}));
    a.download = "us_dividend_ranking.csv";
    a.click();
  }});
  document.getElementById("tsv-btn").addEventListener("click", () => {{
    const tsv = collectVisibleRows().map(r => r.join("\\t")).join("\\n");
    navigator.clipboard.writeText(tsv).then(() => alert("表示中の銘柄一覧をクリップボードにコピーしました！"));
  }});
}})();
</script>
</body>
</html>
"""
    out_path = dist_dir / "index.html"
    out_path.write_text(html_doc, encoding="utf-8")
    return out_path
