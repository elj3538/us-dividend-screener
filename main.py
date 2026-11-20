"""米国株 配当株 軍分けランキング スクリーナー メイン実行スクリプト。"""

from __future__ import annotations

import argparse
import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from src.fetch_data import fetch_stock_data, fetch_us10y_yield
from src.fetch_sp1500 import fetch_sp1500_constituents
from src.generate_pages import generate_auxiliary_pages
from src.generate_reports import generate_reports
from src.generate_site import generate_site
from src.scoring import score_all_stocks
from src.translate import translate_summaries

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="米国株 配当株 軍分けランキング 静的サイト生成ツール")
    parser.add_argument("--limit", type=int, default=None, help="取得対象銘柄数の上限（テスト用）")
    parser.add_argument("--sp500-only", action="store_true", help="S&P 500 のみを母集団にする（高速テスト用）")
    parser.add_argument("--rescreen", action="store_true", help="S&P 1500全銘柄を再スキャンして data/universe.json を更新")
    parser.add_argument("--no-cache", action="store_true", help="ローカルキャッシュを無視して再取得")
    parser.add_argument("--no-translate", action="store_true", help="会社概要の日本語訳API呼び出しをスキップ")
    parser.add_argument("--workers", type=int, default=3, help="並列取得ワーカー数（デフォルト: 3）")
    args = parser.parse_args()

    t0 = time.time()
    base_dir = Path(__file__).resolve().parent
    cache_dir = base_dir / "cache"
    data_dir = base_dir / "data"
    dist_dir = base_dir / "dist"
    universe_file = data_dir / "universe.json"
    use_cache = not args.no_cache

    logger.info("=== 米国株 配当株 軍分けランキング 生成開始 ===")
    us10y_yield = fetch_us10y_yield(cache_dir=cache_dir)
    logger.info("米10年国債利回り: %.2f%%", us10y_yield)

    use_universe = (
        not args.rescreen
        and not args.sp500_only
        and args.limit is None
        and universe_file.exists()
    )
    saved_excluded_kings: list[dict] = []
    saved_excluded_aris: list[dict] = []

    if use_universe:
        u_data = json.loads(universe_file.read_text(encoding="utf-8"))
        constituents = u_data.get("constituents", [])
        saved_excluded_kings = u_data.get("excluded_kings", [])
        saved_excluded_aris = u_data.get("excluded_aristocrats", [])
        logger.info("data/universe.json から %d 銘柄を読み込みました（日次更新モード）", len(constituents))
    else:
        constituents = fetch_sp1500_constituents(
            cache_dir=cache_dir,
            use_cache=use_cache,
            limit=args.limit,
            sp500_only=args.sp500_only,
        )
        logger.info("母集団取得完了: %d 銘柄（フルスクリーニングモード）", len(constituents))

    passed_stocks: list[dict] = []
    excluded_kings: list[dict] = list(saved_excluded_kings)
    excluded_aristocrats: list[dict] = list(saved_excluded_aris)
    done_cnt = 0

    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        future_map = {
            pool.submit(
                fetch_stock_data,
                c,
                cache_dir,
                use_cache=use_cache,
                sleep_sec=0.25,
                skip_non_dividend=not use_universe,
            ): c
            for c in constituents
        }
        for fut in as_completed(future_map):
            done_cnt += 1
            res = fut.result()
            if res is not None:
                if res.get("screen_passed") or use_universe:
                    # 日次更新モードでは既存universe銘柄を維持（軽微な利回り変動で即除外しない）
                    if res.get("price"):
                        passed_stocks.append(res)
                else:
                    if res.get("is_king"):
                        excluded_kings.append(res)
                    if res.get("is_aristocrat"):
                        excluded_aristocrats.append(res)
            if done_cnt % 100 == 0 or done_cnt == len(constituents):
                logger.info(
                    "進捗: %d / %d 銘柄処理済み（対象: %d 銘柄）",
                    done_cnt,
                    len(constituents),
                    len(passed_stocks),
                )

    logger.info("スクリーニング完了: %d 銘柄が条件を通過", len(passed_stocks))
    if not passed_stocks:
        logger.error("通過銘柄が0件のため終了します。")
        return

    # フルスクリーニング完了時は data/universe.json を保存（次回からの日次更新を高速・安定化）
    if not use_universe and not args.sp500_only and args.limit is None:
        data_dir.mkdir(parents=True, exist_ok=True)
        u_payload = {
            "constituents": [
                {
                    "symbol": s["symbol"],
                    "yf_symbol": s["yf_symbol"],
                    "name": s["name"],
                    "sector_en": s["sector_en"],
                    "sector_ja": s["sector_ja"],
                    "sub_industry": s.get("sub_industry", ""),
                    "index_group": s.get("index_group", "S&P 500"),
                    "is_king": bool(s.get("is_king", False)),
                    "is_aristocrat": bool(s.get("is_aristocrat", False)),
                }
                for s in passed_stocks
            ],
            "excluded_kings": [
                {"symbol": x["symbol"], "name": x["name"], "screen_reason": x.get("screen_reason", "")}
                for x in excluded_kings
            ],
            "excluded_aristocrats": [
                {"symbol": x["symbol"], "name": x["name"], "screen_reason": x.get("screen_reason", "")}
                for x in excluded_aristocrats
            ],
        }
        universe_file.write_text(json.dumps(u_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info("data/universe.json を保存しました（%d 銘柄）", len(passed_stocks))

    items, sector_stats = score_all_stocks(passed_stocks, us10y_yield=us10y_yield)
    logger.info("採点・軍分け完了（対象セクター数: %d）", len(sector_stats))

    translate_summaries(items, data_dir=data_dir, enable_network=not args.no_translate)

    index_path = generate_site(
        items,
        sector_stats,
        dist_dir=dist_dir,
        us10y_yield=us10y_yield,
        excluded_kings=excluded_kings,
        excluded_aristocrats=excluded_aristocrats,
    )
    report_cnt = generate_reports(items, dist_dir=dist_dir, us10y_yield=us10y_yield)
    generate_auxiliary_pages(dist_dir=dist_dir, us10y_yield=us10y_yield)

    elapsed = time.time() - t0
    logger.info(
        "=== 完了（%.1f秒）: %s / 個別レポート %d 件 / 補助ページ4件 ===",
        elapsed,
        index_path,
        report_cnt,
    )


if __name__ == "__main__":
    main()
