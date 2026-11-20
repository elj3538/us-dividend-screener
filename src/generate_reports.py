"""各銘柄の個別詳細レポート（dist/reports/<TICKER>.html）を生成するモジュール。"""

from __future__ import annotations

import html
from pathlib import Path
from typing import Any


def _fmt(val: float | None, digits: int = 1, suffix: str = "") -> str:
    if val is None:
        return "-"
    return f"{val:.{digits}f}{suffix}"


def _build_price_svg(pts: list[dict[str, Any]]) -> str:
    if len(pts) < 2:
        return '<p style="color:var(--muted);font-size:12px;">株価推移データなし</p>'
    vals = [p["close"] for p in pts]
    v_min, v_max = min(vals), max(vals)
    span = (v_max - v_min) or 1.0
    w, h, pad = 620, 170, 22
    coords = []
    for i, p in enumerate(pts):
        x = pad + (w - pad * 2) * i / (len(pts) - 1)
        y = h - pad - (h - pad * 2) * (p["close"] - v_min) / span
        coords.append(f"{x:.1f},{y:.1f}")
    poly = " ".join(coords)
    first_d, last_d = pts[0]["date"], pts[-1]["date"]
    return f"""<svg viewBox="0 0 {w} {h}" style="width:100%;max-width:{w}px;height:auto;display:block;">
  <line x1="{pad}" y1="{pad}" x2="{w-pad}" y2="{pad}" stroke="var(--border)" stroke-dasharray="3,3"/>
  <line x1="{pad}" y1="{h-pad}" x2="{w-pad}" y2="{h-pad}" stroke="var(--border)"/>
  <polyline fill="none" stroke="var(--accent)" stroke-width="2.2" points="{poly}"/>
  <text x="{pad}" y="14" font-size="11" fill="var(--muted)">高値 ${v_max:.2f}</text>
  <text x="{pad}" y="{h-5}" font-size="11" fill="var(--muted)">{first_d}（安値 ${v_min:.2f}）</text>
  <text x="{w-pad}" y="{h-5}" font-size="11" fill="var(--muted)" text-anchor="end">{last_d}（終値 ${vals[-1]:.2f}）</text>
</svg>"""


def _build_dividend_svg(annual_divs: list[dict[str, Any]]) -> str:
    if not annual_divs:
        return '<p style="color:var(--muted);font-size:12px;">年次配当データなし</p>'
    max_v = max((d["amount"] for d in annual_divs), default=1.0) or 1.0
    w, h = 620, 170
    pad_l, pad_r, pad_t, pad_b = 28, 16, 22, 26
    n = len(annual_divs)
    bar_area = (w - pad_l - pad_r) / max(n, 1)
    bar_w = max(14, bar_area * 0.62)
    bars = []
    for i, d in enumerate(annual_divs):
        bh = (h - pad_t - pad_b) * (d["amount"] / max_v)
        x = pad_l + i * bar_area + (bar_area - bar_w) / 2
        y = h - pad_b - bh
        bars.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w:.1f}" height="{bh:.1f}" rx="3" fill="var(--accent)"/>'
            f'<text x="{x + bar_w/2:.1f}" y="{y - 4:.1f}" font-size="10" fill="var(--text)" text-anchor="middle">${d["amount"]:.2f}</text>'
            f'<text x="{x + bar_w/2:.1f}" y="{h - 8}" font-size="10" fill="var(--muted)" text-anchor="middle">{d["year"]}</text>'
        )
    return f"""<svg viewBox="0 0 {w} {h}" style="width:100%;max-width:{w}px;height:auto;display:block;">
  <line x1="{pad_l}" y1="{h-pad_b}" x2="{w-pad_r}" y2="{h-pad_b}" stroke="var(--border)"/>
  {"".join(bars)}
</svg>"""


def generate_reports(items: list[dict[str, Any]], dist_dir: Path, us10y_yield: float = 4.2) -> int:
    reports_dir = dist_dir / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    for it in items:
        sym = html.escape(it["symbol"])
        name = html.escape(it["name"])
        sec = html.escape(it["sector_ja"])
        sub = html.escape(it.get("sub_industry", ""))
        m = it["metrics"]
        g = it["grades"]
        det = it.get("detail", {})
        an = det.get("analyst", {})
        tier = it["tier"]
        tier_label = f"{tier}軍" if tier in (1, 2, 3) else "―"

        badges = []
        if it.get("is_king"):
            badges.append('<span class="badge-king">👑 配当王</span>')
        elif it.get("is_aristocrat"):
            badges.append('<span class="badge-aris">🏅 配当貴族</span>')
        if it["model"] == "financial":
            badges.append('<span class="badge">金融モデル</span>')
        elif it["model"] == "reit":
            badges.append('<span class="badge">REITモデル</span>')
        for wr in it.get("warn_reasons", []):
            badges.append(f'<span class="badge-warn">⚠ {html.escape(wr)}</span>')

        summary_ja = html.escape(det.get("summary_ja") or "")
        summary_en = html.escape(det.get("summary") or "")
        summary_block = ""
        if summary_ja or summary_en:
            summary_block = f"""
<section class="card">
  <h2>会社概要</h2>
  {f'<p>{summary_ja}</p>' if summary_ja else ''}
  {f'<details style="margin-top:8px;"><summary style="cursor:pointer;color:var(--muted);font-size:12px;">英文原文を表示</summary><p style="font-size:12px;color:var(--muted);margin-top:6px;">{summary_en}</p></details>' if summary_en else ''}
</section>"""

        price_svg = _build_price_svg(det.get("price_series_weekly", []))
        div_svg = _build_dividend_svg(det.get("annual_dividends", []))

        page = f"""<!DOCTYPE html>
<html lang="ja" data-theme="genko" data-mode="light">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{sym} ({name})｜米国株 配当株 軍分けランキング</title>
<style>
:root {{
  --bg: #f8fafc; --surface: #ffffff; --surface2: #f1f5f9; --text: #0f172a; --muted: #475569;
  --border: #e2e8f0; --accent: #1d4ed8; --accent-soft: #dbeafe; --good: #15803d; --good-bg: #dcfce7;
  --warn: #b45309; --warn-bg: #fef3c7; --weak: #b91c1c; --weak-bg: #fee2e2;
}}
[data-mode="dark"] {{
  --bg: #0b1120; --surface: #111827; --surface2: #1e293b; --text: #f1f5f9; --muted: #94a3b8;
  --border: #334155; --accent-soft: #1e3a5f; --good: #4ade80; --good-bg: #14532d;
  --warn: #fbbf24; --warn-bg: #451a03; --weak: #f87171; --weak-bg: #450a0a;
}}
* {{ box-sizing: border-box; }}
body {{ margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Hiragino Kaku Gothic ProN", "Yu Gothic", sans-serif; background: var(--bg); color: var(--text); font-size: 14px; line-height: 1.6; }}
a {{ color: var(--accent); text-decoration: none; }}
header {{ background: var(--surface); border-bottom: 1px solid var(--border); padding: 14px 16px; }}
.wrap {{ max-width: 980px; margin: 0 auto; padding: 16px; }}
.top-nav {{ display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 8px; font-size: 13px; }}
h1 {{ margin: 4px 0; font-size: 22px; }}
.badges {{ display: flex; flex-wrap: wrap; gap: 6px; margin-top: 6px; }}
.badge {{ background: var(--surface2); border: 1px solid var(--border); padding: 2px 8px; border-radius: 6px; font-size: 12px; font-weight: 600; }}
.badge-king {{ background: #fef08a; color: #854d0e; padding: 2px 8px; border-radius: 6px; font-size: 12px; font-weight: 700; }}
.badge-aris {{ background: #e0e7ff; color: #3730a3; padding: 2px 8px; border-radius: 6px; font-size: 12px; font-weight: 700; }}
.badge-warn {{ background: var(--warn-bg); color: var(--warn); padding: 2px 8px; border-radius: 6px; font-size: 12px; font-weight: 700; }}
.score-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; margin-bottom: 16px; }}
.score-box {{ background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 14px; }}
.score-label {{ font-size: 12px; color: var(--muted); font-weight: 600; }}
.score-val {{ font-size: 30px; font-weight: 800; color: var(--accent); }}
.card {{ background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 16px; margin-bottom: 16px; }}
.card h2 {{ margin: 0 0 12px 0; font-size: 16px; border-left: 4px solid var(--accent); padding-left: 8px; }}
table.kv {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
table.kv th, table.kv td {{ padding: 7px 8px; border-bottom: 1px solid var(--border); text-align: left; }}
table.kv th {{ color: var(--muted); width: 42%; font-weight: 600; }}
table.kv td.num {{ text-align: right; font-weight: 700; font-variant-numeric: tabular-nums; }}
.g-tag {{ display: inline-block; padding: 1px 7px; border-radius: 5px; font-size: 11px; font-weight: 700; }}
.g-良好, .g-割安 {{ background: var(--good-bg); color: var(--good); }}
.g-注意, .g-標準 {{ background: var(--warn-bg); color: var(--warn); }}
.g-弱い, .g-割高 {{ background: var(--weak-bg); color: var(--weak); }}
</style>
</head>
<body>
<header>
  <div class="wrap" style="padding:0;">
    <div class="top-nav">
      <a href="../index.html">← ランキング一覧へ戻る</a>
      <a href="../watchlist.html">☆ ウォッチリスト</a>
      <a href="../portfolio.html">💼 ポートフォリオ</a>
      <a href="../guide.html">📖 使い方・見方</a>
    </div>
    <h1>{sym} — {name}</h1>
    <div style="color:var(--muted);font-size:13px;">
      {sec}（{sub}）｜ 業種級 {it.get("sector_grade", "-")} ｜ <strong>{tier_label}</strong> ｜ カバレッジ {it["coverage"]}（{it["coverage_pct"]}%）
      ｜ 終値 <strong>${_fmt(it["close"], 2)}</strong>（{it.get("latest_date") or "-"}）
    </div>
    <div class="badges">{"".join(badges)}</div>
  </div>
</header>

<div class="wrap">
  <div class="score-grid">
    <div class="score-box">
      <div class="score-label">銘柄選定スコア（0〜110）</div>
      <div class="score-val">{_fmt(it["select_score"], 1)}</div>
      <div style="font-size:12px;color:var(--muted);">業績 {_fmt(it["perf_score"], 1)} / 財務 {_fmt(it["fin_score"], 1)} / CF {_fmt(it["cf_score"], 1)} / 配当持続 {_fmt(it["div_score"], 1)}</div>
    </div>
    <div class="score-box">
      <div class="score-label">買い時スコア（0〜110）</div>
      <div class="score-val">{_fmt(it["buy_score"], 1)}</div>
      <div style="font-size:12px;color:var(--muted);">予想利回り {_fmt(m["forward_yield"], 2, "%")} / Chowder {_fmt(m["chowder"], 1, "%")}</div>
    </div>
    <div class="score-box">
      <div class="score-label">配当ハイライト</div>
      <div class="score-val" style="font-size:24px;">{_fmt(m["forward_yield"], 2, "%")}</div>
      <div style="font-size:12px;color:var(--muted);">年間予想配当 ${_fmt(det.get("forward_dividend"), 2)} / 連続増配 {m["consec_growth"]}年 / 非減配 {m["non_cut_years"]}年</div>
    </div>
  </div>

  <section class="card">
    <h2>① 配当の持続力・還元指標</h2>
    <table class="kv">
      <tr><th>予想配当利回り / 直近1年実績利回り</th><td class="num">{_fmt(m["forward_yield"], 2, "%")} / {_fmt(m["ttm_yield"], 2, "%")}</td><td><span class="g-tag g-{g.get('fwd_yield') or ''}">{g.get('fwd_yield') or '-'}</span></td></tr>
      <tr><th>3年平均配当利回り</th><td class="num">{_fmt(m["avg_3y_yield"], 2, "%")}</td><td>-</td></tr>
      <tr><th>5年増配率（CAGR）</th><td class="num">{_fmt(m["div_cagr_5y"], 2, "%")}</td><td><span class="g-tag g-{g.get('div_cagr') or ''}">{g.get('div_cagr') or '-'}</span></td></tr>
      <tr><th>連続増配年数 / 連続非減配年数</th><td class="num">{m["consec_growth"]}年 / {m["non_cut_years"]}年</td><td><span class="g-tag g-{g.get('consec_g') or ''}">{g.get('consec_g') or '-'}</span></td></tr>
      <tr><th>配当性向（純利益ベース）</th><td class="num">{_fmt(m["payout_ratio"], 1, "%")}</td><td><span class="g-tag g-{g.get('payout') or ''}">{g.get('payout') or '-'}</span></td></tr>
      <tr><th>FCF配当性向（配当支払÷FCF）</th><td class="num">{_fmt(m["fcf_payout"], 1, "%")}</td><td><span class="g-tag g-{g.get('fcf_pay') or ''}">{g.get('fcf_pay') or '-'}</span></td></tr>
      <tr><th>自社株買い利回り / 総還元利回り</th><td class="num">{_fmt(m["buyback_yield"], 2, "%")} / {_fmt(m["total_yield"], 2, "%")}</td><td>-</td></tr>
      <tr><th>ROE / ROA（ROAは採点外）</th><td class="num">{_fmt(m["roe"], 1, "%")} / {_fmt(m["roa"], 1, "%")}</td><td><span class="g-tag g-{g.get('roe') or ''}">{g.get('roe') or '-'}</span></td></tr>
    </table>
  </section>

  <section class="card">
    <h2>年次配当推移（1株あたり・分割調整後）</h2>
    {div_svg}
  </section>

  <section class="card">
    <h2>② 買い時・バリュエーション指標</h2>
    <table class="kv">
      <tr><th>配当利回り 過去レンジ内の位置（高いほど割安）</th><td class="num">{_fmt(m["yield_range_pos"], 1, "%")}（過去 {_fmt(det.get("yield_history_min"), 2, "%")}〜{_fmt(det.get("yield_history_max"), 2, "%")}）</td><td><span class="g-tag g-{g.get('yield_pos') or ''}">{g.get('yield_pos') or '-'}</span></td></tr>
      <tr><th>Chowderルール（予想利回り＋5年増配率）</th><td class="num">{_fmt(m["chowder"], 2, "%")}</td><td><span class="g-tag g-{g.get('chowder') or ''}">{g.get('chowder') or '-'}</span></td></tr>
      <tr><th>PER（実績） / 対業種中央値倍率</th><td class="num">{_fmt(m["trailing_pe"], 1, "倍")} / {_fmt(m["per_rel"], 2, "倍")}</td><td><span class="g-tag g-{g.get('per_rel') or ''}">{g.get('per_rel') or '-'}</span></td></tr>
      <tr><th>PER 過去レンジ内の位置（高いほど割安）</th><td class="num">{_fmt(m["per_range_pos"], 1, "%")}</td><td><span class="g-tag g-{g.get('per_pos') or ''}">{g.get('per_pos') or '-'}</span></td></tr>
      <tr><th>PBR（実績） / 対業種中央値倍率</th><td class="num">{_fmt(m["pbr"], 2, "倍")} / {_fmt(m["pbr_rel"], 2, "倍")}</td><td><span class="g-tag g-{g.get('pbr_rel') or ''}">{g.get('pbr_rel') or '-'}</span></td></tr>
      <tr><th>金利スプレッド（予想利回り − 米10年債 {us10y_yield:.2f}%）</th><td class="num">{_fmt(m["rate_spread"], 2, "%")}</td><td>-</td></tr>
    </table>
  </section>

  <section class="card">
    <h2>③ 業績・財務・キャッシュフロー</h2>
    <table class="kv">
      <tr><th>売上高成長率（CAGR） / EPS成長率（CAGR）</th><td class="num">{_fmt(m["rev_cagr"], 1, "%")} / {_fmt(m["eps_cagr"], 1, "%")}</td><td><span class="g-tag g-{g.get('perf') or ''}">{g.get('perf') or '-'}</span></td></tr>
      <tr><th>営業利益率 / 利益安定度</th><td class="num">{_fmt(m["op_margin"], 1, "%")} / {_fmt(m["profit_stability"], 1)}</td><td>-</td></tr>
      <tr><th>直近四半期 売上YoY / 利益YoY</th><td class="num">{_fmt(m["q_rev_yoy"], 1, "%")} / {_fmt(m["q_profit_yoy"], 1, "%")}</td><td>{"⚠急減速" if it.get("rapid_decel") else "正常"}</td></tr>
      <tr><th>D/Eレシオ / ネットD/E</th><td class="num">{_fmt(m["de_ratio"], 2, "倍")} / {_fmt(m["net_de"], 2, "倍")}</td><td><span class="g-tag g-{g.get('fin') or ''}">{g.get('fin') or '-'}</span></td></tr>
      <tr><th>有利子負債÷営業CF / インタレストカバレッジ</th><td class="num">{_fmt(m["debt_to_ocf"], 2, "倍")} / {_fmt(m["icov"], 1, "倍")}</td><td>-</td></tr>
      <tr><th>営業CF / フリーCF</th><td class="num">{"黒字" if m["ocf_positive"] else "赤字/不明"} / {"黒字" if m["fcf_positive"] else "赤字/不明"}</td><td><span class="g-tag g-{g.get('fcf') or ''}">{g.get('fcf') or '-'}</span></td></tr>
    </table>
  </section>

  <section class="card">
    <h2>株価推移（直近約2年）</h2>
    {price_svg}
    <div style="margin-top:8px;font-size:12px;color:var(--muted);">
      RSI(14): {_fmt(m.get("rsi14"), 1)} ｜ MACD: {_fmt(m.get("macd"), 3)} ｜ アナリスト目標株価平均: ${_fmt(an.get("target_mean_price"), 2)}（評価数: {an.get("num_opinions") or "-"}）
    </div>
  </section>

  {summary_block}
</div>
<script>
document.documentElement.setAttribute("data-theme", localStorage.getItem("pp_theme_us_div") || "genko");
document.documentElement.setAttribute("data-mode", localStorage.getItem("pp_mode_us_div") || "light");
</script>
</body>
</html>"""
        (reports_dir / f"{it['symbol']}.html").write_text(page, encoding="utf-8")

    return len(items)
