"""
テクニカル指標とルールベースの判定（株チャートアプリ app.py の technical_analysis と同じ考え方）
5分足では VWAP の上下も判定に加える。
"""

import math

import pandas as pd


def add_indicators(df):
    c = df["Close"]
    for n in (5, 25, 75):
        df[f"sma{n}"] = c.rolling(n).mean()
    mid = c.rolling(20).mean()
    sd = c.rolling(20).std()
    df["bb_up"], df["bb_low"] = mid + 2 * sd, mid - 2 * sd
    delta = c.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
    df["rsi"] = 100 - 100 / (1 + gain / loss)
    ema12 = c.ewm(span=12, adjust=False).mean()
    ema26 = c.ewm(span=26, adjust=False).mean()
    df["macd"] = ema12 - ema26
    df["macd_signal"] = df["macd"].ewm(span=9, adjust=False).mean()
    df["vol_ma20"] = df["Volume"].rolling(20).mean()
    return df


def add_vwap(df):
    """日ごとにリセットする VWAP（5分足用）"""
    tp = (df["High"] + df["Low"] + df["Close"]) / 3
    day = df.index.date
    pv = (tp * df["Volume"]).groupby(day).cumsum()
    vv = df["Volume"].groupby(day).cumsum()
    df["vwap"] = pv / vv.where(vv > 0)
    return df


def crossed(fast, slow, n):
    """直近 n 本以内のクロス。(+1=上抜け / -1=下抜け / 0=なし, 何本前か)"""
    diff = (fast - slow).dropna().tail(n + 1)
    sign = diff.apply(lambda x: 1 if x > 0 else -1)
    for i in range(len(sign) - 1, 0, -1):
        if sign.iloc[i] != sign.iloc[i - 1]:
            return sign.iloc[i], len(sign) - 1 - i
    return 0, None


def analyze(df, u):
    """u: 日足なら「日」、5分足なら「本」"""
    last = df.iloc[-1]
    price = last["Close"]
    sig = []  # (点数, 見出し, 説明)

    s5, s25, s75 = last["sma5"], last["sma25"], last["sma75"]
    if pd.notna(s75):
        if s5 > s25 > s75 and price > s5:
            sig.append((2, "パーフェクトオーダー（上昇）", f"株価＞5{u}線＞25{u}線＞75{u}線。強い上昇トレンド"))
        elif s5 < s25 < s75 and price < s5:
            sig.append((-2, "パーフェクトオーダー（下落）", f"株価＜5{u}線＜25{u}線＜75{u}線。強い下落トレンド"))
        elif price > s75:
            sig.append((1, f"75{u}線の上", "やや長めの流れは上向きの位置"))
        else:
            sig.append((-1, f"75{u}線の下", "やや長めの流れは下向きの位置"))

    x, ago = crossed(df["sma25"], df["sma75"], 10)
    if x == 1:
        sig.append((2, "ゴールデンクロス", f"{ago}{u}前に25{u}線が75{u}線を上抜け"))
    elif x == -1:
        sig.append((-2, "デッドクロス", f"{ago}{u}前に25{u}線が75{u}線を下抜け"))

    th = 10 if u == "日" else 2
    if pd.notna(s25):
        dev = (price / s25 - 1) * 100
        if dev >= th:
            sig.append((-1, f"25{u}線乖離 +{dev:.1f}%", "上がりすぎ。短期的な反落に注意"))
        elif dev <= -th:
            sig.append((1, f"25{u}線乖離 {dev:.1f}%", "下がりすぎ。自律反発の可能性"))

    if "vwap" in df and pd.notna(last["vwap"]):
        if price > last["vwap"]:
            sig.append((1, "VWAPの上", "今日買った人の平均より上。買い方が優勢"))
        elif price < last["vwap"]:
            sig.append((-1, "VWAPの下", "今日買った人の平均より下。売り方が優勢"))

    rsi = last["rsi"]
    if pd.notna(rsi):
        if rsi >= 70:
            sig.append((-1, f"RSI {rsi:.0f}（買われすぎ）", "70以上。過熱感あり"))
        elif rsi <= 30:
            sig.append((1, f"RSI {rsi:.0f}（売られすぎ）", "30以下。反発しやすい水準"))

    x, ago = crossed(df["macd"], df["macd_signal"], 5)
    if x == 1:
        sig.append((1, "MACD 買いシグナル", f"{ago}{u}前にMACDがシグナルを上抜け"))
    elif x == -1:
        sig.append((-1, "MACD 売りシグナル", f"{ago}{u}前にMACDがシグナルを下抜け"))

    if pd.notna(last["bb_up"]):
        if price >= last["bb_up"]:
            sig.append((0, "ボリンジャー +2σ 超え", "強い勢い。ただし行き過ぎの可能性も"))
        elif price <= last["bb_low"]:
            sig.append((0, "ボリンジャー −2σ 割れ", "強い売り圧力。ただし売られすぎの可能性も"))

    if pd.notna(last["vol_ma20"]) and last["vol_ma20"] > 0 and len(df) >= 2:
        ratio = last["Volume"] / last["vol_ma20"]
        if ratio >= 2:
            up = price >= df["Close"].iloc[-2]
            sig.append((1 if up else -1, f"出来高急増（20{u}平均の{ratio:.1f}倍）",
                        "大商いで上昇。資金流入のサイン" if up else "大商いで下落。資金流出のサイン"))

    score = sum(s[0] for s in sig)
    verdict = ("強気" if score >= 3 else "やや強気" if score >= 1 else
               "弱気" if score <= -3 else "やや弱気" if score <= -1 else "中立")
    return {"score": score, "verdict": verdict, "rsi": num(rsi, 1),
            "signals": [{"point": p, "title": t, "detail": d} for p, t, d in sig]}


def num(v, nd=1):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(v) or math.isinf(v) else round(v, nd)


def series(df, cols):
    return {k: [num(v, 2 if k in ("rsi",) else 1) for v in df[col]] for k, col in cols.items()}


def build(daily, m5):
    """daily / m5: yfinance の DataFrame（Open/High/Low/Close/Volume、index は日時）"""
    out = {}
    d = add_indicators(daily.dropna(subset=["Close"]).copy())
    if len(d) >= 30:
        tail = d.tail(60)
        out["d"] = {"t": [i.strftime("%Y-%m-%d") for i in tail.index],
                    **series(tail, {"o": "Open", "h": "High", "l": "Low", "c": "Close",
                                    "sma5": "sma5", "sma25": "sma25", "sma75": "sma75"}),
                    "analysis": analyze(d, "日")}
    m = m5.dropna(subset=["Close"]).copy()
    if len(m) >= 30:
        m = add_vwap(add_indicators(m))
        days = sorted(set(m.index.date))
        tail = m[m.index.date >= days[-2]] if len(days) >= 2 else m
        today = m[m.index.date == days[-1]]
        prev = m[m.index.date == days[-2]] if len(days) >= 2 else None
        levels = {"dayHigh": num(today["High"].max()), "dayLow": num(today["Low"].min()),
                  "vwap": num(today["vwap"].iloc[-1])}
        if prev is not None and len(prev):
            levels.update({"prevClose": num(prev["Close"].iloc[-1]), "prevHigh": num(prev["High"].max()),
                           "prevLow": num(prev["Low"].min())})
        out["m5"] = {"t": [int(i.timestamp()) for i in tail.index],
                     **series(tail, {"o": "Open", "h": "High", "l": "Low", "c": "Close",
                                     "vwap": "vwap", "sma5": "sma5", "sma25": "sma25"}),
                     "levels": levels, "analysis": analyze(m, "本")}
    return out
