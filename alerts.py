# -*- coding: utf-8 -*-
"""Coin Takip - GitHub uzerinde 10 dakikada bir calisan fiyat bildirimi (ntfy)."""
import json
import os
import time
import urllib.parse
import urllib.request

TOPIC = os.environ.get("NTFY_TOPIC", "").strip()
TEST = os.environ.get("TEST", "false").lower() == "true"

COINS = ["BTC", "ETH", "SOL", "BNB", "XRP", "AVAX", "DOGE"]
COIN_THRESHOLD = 3.0      # coinlerde ~15 dk icinde %3
COMM_THRESHOLD = 1.5      # doviz/emtiada ~15 dk icinde %1,5
WINDOW_MIN = 15
COOLDOWN_MIN = 60         # ayni varlik icin en fazla saatte bir bildirim
# ad: (Yahoo sembolu, birim)
COMM = {
    "Dolar": ("USDTRY=X", "₺"),
    "Euro": ("EURTRY=X", "₺"),
    "Ons Altın": ("GC=F", "$"),
    "Ons Gümüş": ("SI=F", "$"),
    "Brent Petrol": ("BZ=F", "$"),
    "BIST 100": ("XU100.IS", ""),
}
STATE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "state.json")
UA = {"User-Agent": "Mozilla/5.0 CoinTakip-bildirim/1.0"}


def get(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())


def fmt(x):
    s = f"{x:,.2f}" if abs(x) >= 10 else f"{x:,.4f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def pct(x):
    return f"{x:+.2f}%".replace(".", ",")


def coin_change(coin):
    # GitHub sunuculari ABD'de; api.binance.com ABD'yi engelliyor, herkese acik veri adresi kullaniliyor
    k = get(f"https://data-api.binance.vision/api/v3/klines?symbol={coin}TRY&interval=5m&limit=4")
    start, last = float(k[0][1]), float(k[-1][4])
    return last, (last / start - 1) * 100


def yahoo_change(sym):
    d = get(f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(sym)}?range=1d&interval=5m")
    r = d["chart"]["result"][0]
    pts = [(t, c) for t, c in zip(r.get("timestamp") or [], r["indicators"]["quote"][0].get("close") or [])
           if c is not None]
    if len(pts) < 2:
        return None
    last_t, last = pts[-1]
    if time.time() - last_t > 30 * 60:      # piyasa kapali / veri eski
        return None
    base = next((c for t, c in reversed(pts) if t <= last_t - WINDOW_MIN * 60), None)
    if not base:
        return None
    return last, (last / base - 1) * 100


def send(text, high=True):
    req = urllib.request.Request(
        f"https://ntfy.sh/{urllib.parse.quote(TOPIC)}", data=text.encode("utf-8"), method="POST",
        headers={**UA, "Title": "Coin Takip", "Priority": "high" if high else "default",
                 "Tags": "chart_with_upwards_trend"})
    urllib.request.urlopen(req, timeout=15).read()


def main():
    if not TOPIC:
        raise SystemExit("NTFY_TOPIC secret'i tanimli degil (Settings > Secrets and variables > Actions).")
    if TEST:
        send("Test: GitHub bildirimi çalışıyor ✅", high=False)
        print("test bildirimi gonderildi")
        return
    try:
        with open(STATE_PATH, encoding="utf-8") as f:
            state = json.load(f)
    except Exception:
        state = {}
    now = time.time()
    msgs = []

    def check(key, name, getter, threshold, unit):
        if now - state.get(key, 0) < COOLDOWN_MIN * 60:
            return
        try:
            res = getter()
        except Exception as e:
            print(f"{name}: veri alinamadi ({e})")
            return
        if not res:
            return
        price, ch = res
        print(f"{name}: {fmt(price)} {pct(ch)}")
        if abs(ch) >= threshold:
            yon = "YÜKSELDİ" if ch > 0 else "DÜŞTÜ"
            p = f"$ {fmt(price)}" if unit == "$" else (f"{fmt(price)} ₺" if unit == "₺" else fmt(price))
            msgs.append(f"{name} son ~{WINDOW_MIN} dk'da {pct(ch)} {yon} → {p}")
            state[key] = now

    for c in COINS:
        check("c_" + c, c, lambda c=c: coin_change(c), COIN_THRESHOLD, "₺")
    for name, (sym, unit) in COMM.items():
        check("e_" + sym, name, lambda s=sym: yahoo_change(s), COMM_THRESHOLD, unit)

    if msgs:
        send("\n".join(msgs))
        print("bildirim gonderildi:\n" + "\n".join(msgs))
        with open(STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=1, sort_keys=True)
    else:
        print("buyuk hareket yok")


if __name__ == "__main__":
    main()
