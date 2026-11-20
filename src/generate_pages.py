"""補助ページ（watchlist.html, portfolio.html, guide.html, terms.html）を生成するモジュール。"""

from __future__ import annotations

from pathlib import Path

_COMMON_CSS = """
:root {
  --bg: #f8fafc; --surface: #ffffff; --surface2: #f1f5f9; --text: #0f172a; --muted: #475569;
  --border: #e2e8f0; --accent: #1d4ed8; --accent-soft: #dbeafe; --good: #15803d; --good-bg: #dcfce7;
  --warn: #b45309; --warn-bg: #fef3c7; --weak: #b91c1c; --weak-bg: #fee2e2;
}
[data-mode="dark"] {
  --bg: #0b1120; --surface: #111827; --surface2: #1e293b; --text: #f1f5f9; --muted: #94a3b8;
  --border: #334155; --accent-soft: #1e3a5f; --good: #4ade80; --good-bg: #14532d;
  --warn: #fbbf24; --warn-bg: #451a03; --weak: #f87171; --weak-bg: #450a0a;
}
* { box-sizing: border-box; }
body { margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Hiragino Kaku Gothic ProN", "Yu Gothic", sans-serif; background: var(--bg); color: var(--text); font-size: 14px; line-height: 1.65; }
a { color: var(--accent); text-decoration: none; }
a:hover { text-decoration: underline; }
header { background: var(--surface); border-bottom: 1px solid var(--border); padding: 14px 16px; }
.wrap { max-width: 1120px; margin: 0 auto; padding: 16px; }
.nav { display: flex; flex-wrap: wrap; gap: 10px; margin-bottom: 8px; font-size: 13px; }
.card { background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 16px; margin-bottom: 16px; }
.card h2 { margin: 0 0 10px 0; font-size: 17px; border-left: 4px solid var(--accent); padding-left: 8px; }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th, td { padding: 8px; border-bottom: 1px solid var(--border); text-align: left; }
th { background: var(--surface2); color: var(--muted); font-size: 12px; }
.num { text-align: right; font-variant-numeric: tabular-nums; }
.btn { border: 1px solid var(--border); background: var(--surface2); color: var(--text); padding: 6px 12px; border-radius: 7px; cursor: pointer; font-size: 12px; font-weight: 600; }
.kpi-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 12px; margin-bottom: 16px; }
.kpi { background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 14px; }
.kpi .label { font-size: 12px; color: var(--muted); font-weight: 600; }
.kpi .val { font-size: 26px; font-weight: 800; color: var(--accent); }
"""

_THEME_SCRIPT = """<script>
document.documentElement.setAttribute("data-theme", localStorage.getItem("pp_theme_us_div") || "genko");
document.documentElement.setAttribute("data-mode", localStorage.getItem("pp_mode_us_div") || "light");
</script>"""


def _shell(title: str, h1: str, body_html: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="ja" data-theme="genko" data-mode="light">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}｜米国株 配当株 軍分けランキング</title>
<style>{_COMMON_CSS}</style>
</head>
<body>
<header>
  <div class="wrap" style="padding:0;">
    <div class="nav">
      <a href="index.html">🏠 ランキング</a>
      <a href="guide.html">📖 使い方・見方</a>
      <a href="watchlist.html">☆ ウォッチリスト</a>
      <a href="portfolio.html">💼 ポートフォリオ</a>
      <a href="terms.html">📜 利用規約・免責</a>
    </div>
    <h1 style="margin:4px 0;font-size:21px;">{h1}</h1>
  </div>
</header>
<div class="wrap">
{body_html}
</div>
{_THEME_SCRIPT}
</body>
</html>"""


def generate_auxiliary_pages(dist_dir: Path, us10y_yield: float = 4.2) -> None:
    dist_dir.mkdir(parents=True, exist_ok=True)

    # 1. watchlist.html
    wl_body = """
<div class="card">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">
    <h2 style="margin:0;">☆ 登録銘柄一覧</h2>
    <button class="btn" id="clear-wl">すべて解除</button>
  </div>
  <div style="overflow-x:auto;">
    <table>
      <thead><tr><th>ティッカー</th><th>銘柄</th><th>業種</th><th>軍</th><th class="num">終値</th><th class="num">選定</th><th class="num">買い時</th><th class="num">利回り</th><th class="num">5年増配率</th><th>操作</th></tr></thead>
      <tbody id="wl-tbody"><tr><td colspan="10">読み込み中...</td></tr></tbody>
    </table>
  </div>
</div>
<script>
(async function() {
  const LS_WL = "pp_watchlist_us_div";
  const res = await fetch("ranking.json");
  const data = await res.json();
  const bySym = Object.fromEntries(data.items.map(x => [x.symbol, x]));
  function render() {
    const syms = JSON.parse(localStorage.getItem(LS_WL) || "[]");
    const tb = document.getElementById("wl-tbody");
    if (!syms.length) { tb.innerHTML = '<tr><td colspan="10" style="color:var(--muted);">ウォッチリストに銘柄がありません。ランキング一覧の「☆」にチェックを入れて登録してください。</td></tr>'; return; }
    tb.innerHTML = syms.map(s => {
      const it = bySym[s];
      if (!it) return `<tr><td>${s}</td><td colspan="8">対象外</td><td><button class="btn rm" data-s="${s}">削除</button></td></tr>`;
      return `<tr>
        <td><a href="reports/${it.symbol}.html"><strong>${it.symbol}</strong></a></td>
        <td>${it.name}</td><td>${it.sector_ja}</td><td>${it.tier ? it.tier + "軍" : "―"}</td>
        <td class="num">$${it.close ?? "-"}</td><td class="num"><strong>${it.select_score ?? "-"}</strong></td>
        <td class="num">${it.buy_score ?? "-"}</td><td class="num">${it.forward_yield ?? "-"}%</td>
        <td class="num">${it.div_cagr_5y ?? "-"}%</td>
        <td><button class="btn rm" data-s="${s}">削除</button></td>
      </tr>`;
    }).join("");
    tb.querySelectorAll(".rm").forEach(b => b.addEventListener("click", () => {
      const next = syms.filter(x => x !== b.dataset.s);
      localStorage.setItem(LS_WL, JSON.stringify(next));
      render();
    }));
  }
  document.getElementById("clear-wl").addEventListener("click", () => {
    if (confirm("ウォッチリストを空にしますか？")) { localStorage.setItem(LS_WL, "[]"); render(); }
  });
  render();
})();
</script>"""
    (dist_dir / "watchlist.html").write_text(_shell("ウォッチリスト", "☆ ウォッチリスト", wl_body), encoding="utf-8")

    # 2. portfolio.html（年間予想配当金シミュレーター付き）
    pf_body = """
<div class="kpi-grid">
  <div class="kpi"><div class="label">ポートフォリオ評価額</div><div class="val" id="pf-total-val">$0</div></div>
  <div class="kpi"><div class="label">年間予想配当金（税引前）</div><div class="val" id="pf-total-div">$0</div></div>
  <div class="kpi"><div class="label">加重平均 配当利回り</div><div class="val" id="pf-avg-yield">0.00%</div></div>
  <div class="kpi"><div class="label">登録銘柄数</div><div class="val" id="pf-cnt">0</div></div>
</div>
<div class="card">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">
    <h2 style="margin:0;">💼 保有銘柄・年間配当シミュレーション</h2>
    <button class="btn" id="clear-pf">すべて解除</button>
  </div>
  <div style="overflow-x:auto;">
    <table>
      <thead><tr><th>ティッカー</th><th>銘柄</th><th>業種</th><th class="num">終値</th><th class="num">保有株数</th><th class="num">評価額</th><th class="num">予想利回り</th><th class="num">年間予想配当</th><th>操作</th></tr></thead>
      <tbody id="pf-tbody"><tr><td colspan="9">読み込み中...</td></tr></tbody>
    </table>
  </div>
</div>
<script>
(async function() {
  const LS_PF = "pp_portfolio_us_div";
  const res = await fetch("ranking.json");
  const data = await res.json();
  const bySym = Object.fromEntries(data.items.map(x => [x.symbol, x]));
  function render() {
    const pf = JSON.parse(localStorage.getItem(LS_PF) || "{}");
    const syms = Object.keys(pf);
    const tb = document.getElementById("pf-tbody");
    let totalVal = 0, totalDiv = 0;
    if (!syms.length) {
      tb.innerHTML = '<tr><td colspan="9" style="color:var(--muted);">ポートフォリオに銘柄がありません。ランキング一覧の「💼」にチェックを入れて登録してください。</td></tr>';
    } else {
      tb.innerHTML = syms.map(s => {
        const it = bySym[s];
        const shares = Number(pf[s]?.shares || 0);
        if (!it) return `<tr><td>${s}</td><td colspan="7">対象外</td><td><button class="btn rm" data-s="${s}">削除</button></td></tr>`;
        const val = (it.close || 0) * shares;
        const annDiv = (it.forward_dividend || ((it.close || 0) * (it.forward_yield || 0) / 100)) * shares;
        totalVal += val; totalDiv += annDiv;
        return `<tr>
          <td><a href="reports/${it.symbol}.html"><strong>${it.symbol}</strong></a></td>
          <td>${it.name}</td><td>${it.sector_ja}</td>
          <td class="num">$${it.close?.toFixed(2) ?? "-"}</td>
          <td class="num"><input type="number" class="sh-inp" data-s="${s}" value="${shares}" min="0" step="1" style="width:76px;padding:3px 6px;text-align:right;"></td>
          <td class="num">$${val.toFixed(0)}</td>
          <td class="num">${it.forward_yield?.toFixed(2) ?? "-"}%</td>
          <td class="num"><strong>$${annDiv.toFixed(2)}</strong></td>
          <td><button class="btn rm" data-s="${s}">削除</button></td>
        </tr>`;
      }).join("");
    }
    document.getElementById("pf-total-val").textContent = "$" + totalVal.toLocaleString("en-US", { maximumFractionDigits: 0 });
    document.getElementById("pf-total-div").textContent = "$" + totalDiv.toLocaleString("en-US", { maximumFractionDigits: 2 });
    document.getElementById("pf-avg-yield").textContent = (totalVal > 0 ? (totalDiv / totalVal * 100).toFixed(2) : "0.00") + "%";
    document.getElementById("pf-cnt").textContent = syms.length;

    tb.querySelectorAll(".sh-inp").forEach(inp => inp.addEventListener("change", () => {
      pf[inp.dataset.s] = { shares: Math.max(0, Number(inp.value || 0)) };
      localStorage.setItem(LS_PF, JSON.stringify(pf));
      render();
    }));
    tb.querySelectorAll(".rm").forEach(b => b.addEventListener("click", () => {
      delete pf[b.dataset.s];
      localStorage.setItem(LS_PF, JSON.stringify(pf));
      render();
    }));
  }
  document.getElementById("clear-pf").addEventListener("click", () => {
    if (confirm("ポートフォリオを空にしますか？")) { localStorage.setItem(LS_PF, "{}"); render(); }
  });
  render();
})();
</script>"""
    (dist_dir / "portfolio.html").write_text(_shell("ポートフォリオ", "💼 ポートフォリオ（配当シミュレーター）", pf_body), encoding="utf-8")

    # 3. guide.html
    guide_body = f"""
<div class="card">
  <h2>このサイトのコンセプト</h2>
  <p>「良い配当企業か（<strong>銘柄選定スコア</strong>）」と「今買う値段か（<strong>買い時スコア</strong>）」を混ぜず、2つのスコア（各 0〜110点）で別々に評価します。</p>
</div>
<div class="card">
  <h2>対象銘柄の抽出条件（スクリーン）</h2>
  <ul>
    <li><strong>母集団</strong>: S&amp;P Composite 1500（S&amp;P 500 + S&amp;P 400 + S&amp;P 600）</li>
    <li><strong>直近1年実績配当利回り</strong>: 1.5% 以上</li>
    <li><strong>3年平均配当利回り</strong>: 1.2% 以上</li>
    <li><strong>連続非減配年数</strong>: 直近5年間 減配なし（配当履歴から自前計算）</li>
  </ul>
</div>
<div class="card">
  <h2>スコアの構成と軍分けルール</h2>
  <ul>
    <li><strong>選定スコア（0〜110点）</strong>: 業績（直近四半期急減速ペナルティ含む）・財務・キャッシュフロー・配当の持続力（5年増配率・連続増配年数・非減配年数・配当性向・ROE・総還元利回り）の4グループで採点。銀行・保険・証券は金融専用モデル、REITはFFOベースの専用モデルで採点します。</li>
    <li><strong>買い時スコア（0〜110点）</strong>: 配当利回りの過去レンジ位置・予想配当利回り・Chowderルール（予想利回り＋5年増配率）・PER/PBRの対業種比較・金利スプレッド（予想利回り − 米10年国債利回り {us10y_yield:.2f}%、金利敏感セクター対象）で採点します。</li>
    <li><strong>軍分け</strong>: 各GICSセクター内で選定スコア順に <strong>上位25%＝1軍 / 続く45%＝2軍 / 残り30%＝3軍</strong>。カバレッジ「低」は最高2軍まで、選定スコア85点以上は最低2軍を保証、6銘柄未満のセクターは「―」表示となります。</li>
    <li><strong>ROA・⚠注意マーク</strong>: 表示・絞り込み専用であり、選定スコア・買い時スコア・軍分けの計算には使用しません。</li>
  </ul>
</div>"""
    (dist_dir / "guide.html").write_text(_shell("使い方・見方", "📖 使い方・見方", guide_body), encoding="utf-8")

    # 4. terms.html
    terms_body = """
<div class="card">
  <h2>利用規約・免責事項</h2>
  <p>本サイトは個人の投資研究・情報整理を目的として自動生成されたものであり、特定の有価証券の売買を推奨・勧誘するものではありません。</p>
  <p>掲載されている株価・財務・配当データは公開情報（Wikipedia / Yahoo Finance 等）をもとに機械的に取得・算出しており、その正確性・完全性・最新性を保証するものではありません。投資に関する最終決定は、必ずご自身の判断と責任において行ってください。</p>
</div>"""
    (dist_dir / "terms.html").write_text(_shell("利用規約・免責事項", "📜 利用規約・免責事項", terms_body), encoding="utf-8")
