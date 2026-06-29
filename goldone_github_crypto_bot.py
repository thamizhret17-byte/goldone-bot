import os, requests, json, logging, time
from datetime import datetime, timezone, timedelta

TELEGRAM_TOKEN   = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "8526718482")
TWELVE_DATA_KEY  = os.environ["TWELVE_DATA_KEY"]
GROQ_KEY         = os.environ["GROQ_KEY"]

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger()

def ist_now():
    return datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)

def is_weekend():
    return ist_now().weekday() >= 5

SL_TP = {
    "BTC/USD": {"sl": 250, "tp": 500},
    "ETH/USD": {"sl": 15,  "tp": 30},
    "BNB/USD": {"sl": 4,   "tp": 8},
}

def calc_levels(symbol, price, signal):
    cfg = SL_TP[symbol]
    sl_pts, tp_pts = cfg["sl"], cfg["tp"]
    if signal == "BUY":
        sl, tp = round(price - sl_pts, 2), round(price + tp_pts, 2)
    elif signal == "SELL":
        sl, tp = round(price + sl_pts, 2), round(price - tp_pts, 2)
    else:
        return None
    return {"entry": f"{price:,.2f}", "sl": f"{sl:,.2f}", "tp": f"{tp:,.2f}",
            "sl_pts": str(sl_pts), "tp_pts": str(tp_pts), "rr": f"1:{round(tp_pts/sl_pts,1)}"}

def td(ep, params):
    params["apikey"] = TWELVE_DATA_KEY
    r = requests.get(f"https://api.twelvedata.com/{ep}", params=params, timeout=15)
    d = r.json()
    if d.get("status") == "error": raise Exception(d.get("message"))
    return d

def fetch(symbol):
    p  = td("price", {"symbol": symbol})
    rs = td("rsi",   {"symbol": symbol, "interval": "1h", "time_period": 14, "outputsize": 1})
    mc = td("macd",  {"symbol": symbol, "interval": "1h", "outputsize": 1})
    e2 = td("ema",   {"symbol": symbol, "interval": "1h", "time_period": 20, "outputsize": 1})
    e5 = td("ema",   {"symbol": symbol, "interval": "1h", "time_period": 50, "outputsize": 1})
    return {
        "symbol": symbol, "price": float(p["price"]),
        "rsi":      round(float(rs["values"][0]["rsi"]), 1)         if rs.get("values") else None,
        "macd":     round(float(mc["values"][0]["macd"]), 4)        if mc.get("values") else None,
        "macd_sig": round(float(mc["values"][0]["macd_signal"]), 4) if mc.get("values") else None,
        "ema20":    round(float(e2["values"][0]["ema"]), 2)         if e2.get("values") else None,
        "ema50":    round(float(e5["values"][0]["ema"]), 2)         if e5.get("values") else None,
    }

SYS = """Crypto signal assistant for beginner trader.
BUY: price>EMA20>EMA50 AND MACD>macd_signal AND RSI 40-65
SELL: price<EMA20<EMA50 AND MACD<macd_signal AND RSI 35-60
WAIT: RSI>75 or RSI<28 or mixed
HOLD: partial alignment
Do NOT mention SL TP levels.
JSON only: {"signal":"BUY|SELL|HOLD|WAIT","confidence":55-88,"reason":"2 sentences","caution":"1 sentence"}"""

def get_signal(data):
    r = requests.post("https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {GROQ_KEY}", "Content-Type": "application/json"},
        json={"model": "llama-3.3-70b-versatile", "max_tokens": 150, "temperature": 0.1,
              "messages": [{"role":"system","content":SYS},{"role":"user","content":json.dumps(data)}]},
        timeout=20)
    r.raise_for_status()
    txt = r.json()["choices"][0]["message"]["content"].strip().replace("```json","").replace("```","").strip()
    return json.loads(txt)

def send_tg(msg):
    requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        json={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "HTML"}, timeout=10).raise_for_status()

ICON = {"BTC/USD":"₿","ETH/USD":"⟠","BNB/USD":"🔶"}
NAME = {"BTC/USD":"Bitcoin","ETH/USD":"Ethereum","BNB/USD":"BNB"}

def build_msg(m, sig, lv):
    s  = sig.get("signal","WAIT")
    em = {"BUY":"🟢","SELL":"🔴","HOLD":"🟡","WAIT":"⏳"}.get(s,"⏳")
    msg = f"""{ICON.get(m['symbol'],'🪙')} <b>Crypto — {NAME.get(m['symbol'],m['symbol'])}</b>
━━━━━━━━━━━━━━━
💰 <b>Price:</b> ${m['price']:,.2f}   📊 <b>RSI:</b> {m['rsi']}
{em} <b>{s}</b>  ({sig.get('confidence','—')}% confidence)
━━━━━━━━━━━━━━━\n"""
    if lv:
        msg += f"🎯 Entry: ${lv['entry']}\n🛑 SL: ${lv['sl']} (-{lv['sl_pts']} pts)\n✅ TP: ${lv['tp']} (+{lv['tp_pts']} pts)\n⚖️ R:R {lv['rr']}\n━━━━━━━━━━━━━━━\n"
    msg += f"📝 {sig.get('reason','')}\n⚠️ <i>{sig.get('caution','')}</i>\n🕐 {ist_now().strftime('%d %b %H:%M IST')} | Weekend"
    return msg

def main():
    log.info(f"Started — {ist_now().strftime('%A %H:%M IST')}")
    if not is_weekend():
        log.info("Weekday. Exit.")
        return
    for coin in ["BTC/USD", "ETH/USD", "BNB/USD"]:
        try:
            m   = fetch(coin)
            sig = get_signal(m)
            lv  = calc_levels(coin, m["price"], sig.get("signal","WAIT"))
            send_tg(build_msg(m, sig, lv))
            log.info(f"{coin} → {sig.get('signal')} ✓")
            time.sleep(4)
        except Exception as e:
            log.error(f"{coin}: {e}")
            try: send_tg(f"⚠️ Crypto Error ({coin}): {str(e)[:150]}")
            except: pass

if __name__ == "__main__":
    main()
