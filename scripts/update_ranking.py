"""
東証プライムの出来高上位20銘柄を ranking.json に書き出す（GitHub Actions から10分おきに実行）

- 出来高と株価: yfinance のスクリーナー（Yahoo Finance、約20分遅れ）
- プライム市場かどうか・日本語の銘柄名・TOPIX500 かどうか: JPX の上場銘柄一覧（data_j.xls）
データが前回と同じなら ranking.json を書き換えない（取引時間外に無駄なコミットをしないため）。
"""

import json
import re
import sys
import unicodedata
import urllib.request
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path

import pandas as pd
import yfinance as yf
from yfinance import EquityQuery

OUT = Path(__file__).resolve().parent.parent / "ranking.json"
JPX_PAGE = "https://www.jpx.co.jp/markets/statistics-equities/misc/01.html"
UA = {"User-Agent": "Mozilla/5.0 (compatible; sl-calc ranking bot)"}
JST = timezone(timedelta(hours=9))
TOP_N = 20


def prime_list():
    html = urllib.request.urlopen(urllib.request.Request(JPX_PAGE, headers=UA), timeout=30).read().decode("utf-8", "ignore")
    link = re.search(r'href="([^"]+data_j\.xlsx?)"', html)
    if not link:
        raise RuntimeError("JPX のページに銘柄一覧が見つかりません")
    raw = urllib.request.urlopen(urllib.request.Request("https://www.jpx.co.jp" + link.group(1), headers=UA), timeout=60).read()
    df = pd.read_excel(BytesIO(raw), dtype=str).fillna("")
    # 列: 日付, コード, 銘柄名, 市場・商品区分, 33業種コード, 33業種区分, 17業種コード, 17業種区分, 規模コード, 規模区分
    # 規模コード 1=Core30, 2=Large70, 4=Mid400 → この3つが TOPIX500
    out = {}
    for _, r in df.iterrows():
        code = r.iloc[1].strip()
        if code and "プライム" in r.iloc[3]:
            out[code] = {"name": unicodedata.normalize("NFKC", r.iloc[2]).strip(),
                         "t500": r.iloc[8].strip() in ("1", "2", "4")}
    if len(out) < 1000:
        raise RuntimeError(f"プライム銘柄が少なすぎます（{len(out)}件）")
    return out


def main():
    prime = prime_list()
    q = EquityQuery("and", [EquityQuery("eq", ["region", "jp"]), EquityQuery("is-in", ["exchange", "JPX"])])
    quotes = yf.screen(q, sortField="dayvolume", sortAsc=False, size=250).get("quotes", [])
    items, latest = [], 0
    for x in quotes:
        sym = x.get("symbol", "")
        p, v = x.get("regularMarketPrice"), x.get("regularMarketVolume")
        code = sym[:-2] if sym.endswith(".T") else None
        if not (code in prime and p and v):
            continue
        latest = max(latest, x.get("regularMarketTime") or 0)
        items.append({"code": code, "name": prime[code]["name"], "price": round(float(p), 1),
                      "changePct": round(float(x.get("regularMarketChangePercent") or 0), 2),
                      "volume": int(v), "t500": prime[code]["t500"]})
    items.sort(key=lambda r: r["volume"], reverse=True)
    items = items[:TOP_N]
    if len(items) < TOP_N:
        raise RuntimeError(f"ランキングが {len(items)} 件しか取れませんでした")
    data = {"asof": datetime.fromtimestamp(latest, JST).isoformat(timespec="minutes") if latest else None,
            "note": "Yahoo Finance のデータ（約20分遅れ）", "items": items}
    text = json.dumps(data, ensure_ascii=False, indent=1) + "\n"
    if OUT.exists() and OUT.read_text(encoding="utf-8") == text:
        print("変化なし")
        return
    OUT.write_text(text, encoding="utf-8", newline="\n")
    print(f"更新: {data['asof']} 1位 {items[0]['name']} {items[0]['volume']:,}株")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("失敗:", e, file=sys.stderr)
        sys.exit(1)
