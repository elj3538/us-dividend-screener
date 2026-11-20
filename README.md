# 米国株 配当株 軍分けランキング（`us-dividend-screener`）

S&P Composite 1500（S&P 500 + 400 + 600）から、以下の条件を満たす米国配当株を自動抽出し、「銘柄選定スコア」と「買い時スコア」の2軸（各 0〜110点）で軍分け・可視化する静的サイト生成ツールです。

- **直近1年実績配当利回り**: 1.5% 以上
- **3年平均配当利回り**: 1.2% 以上
- **連続非減配年数**: 直近5年間 減配なし

## ローカル実行方法

```powershell
# 少数テスト（S&P 500の先頭30銘柄で動作確認）
.venv\Scripts\python.exe main.py --sp500-only --limit 30 --no-translate

# 本番フル生成（S&P 1500全銘柄から抽出）
.venv\Scripts\python.exe main.py
```

生成物は `dist/` 配下（`index.html`, `ranking.json`, `reports/<TICKER>.html`, `watchlist.html`, `portfolio.html`, `guide.html`, `terms.html`）に出力されます。
