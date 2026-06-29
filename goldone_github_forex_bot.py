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

def is_trading_hour():
    now = ist_now()
    wd, h = now.weekday(), now.hour
    if wd >= 5: return False
    if wd == 0 and h < 6: return False
    if wd == 4 and h >= 23: return False
    return True

SL_TP = {
    "XAU/USD": {"sl": 10,     "tp": 20,     "dp": 2, "unit": "pts"},
    "EUR/USD": {"sl": 0.0012, "tp": 0.0024, "dp": 4, "unit": "pips"},
}

def calc_levels(symbol, price, signal):
    cfg = SL_TP[symbol]
    sl_pts, tp_pts, dp, unit = cfg["sl"], cfg["tp"], cfg["dp"], cfg["unit"]
    if signal == "BUY":
        sl, tp = round(price - sl_pts, dp), round(price + tp_pts, dp)
    elif signal == "SELL":
        sl, tp = round(price + sl_pts, dp), round(price - tp_pts, dp)
    else:
        return None
    disp = lambda v: f"{round(v*10000) if unit=='pips' else v} {unit}"
    return {"entry": f"{price:.{dp}f}", "sl": f"{sl:.{dp}f}", "tp": f"{tp:.{dp}f}",
            "sl_d": disp(sl_pts), "tp_d": disp(tp_pts), "rr": f"1:{round(tp_pts/sl_pts,1)}"}

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
        "macd":     round(float(mc["values"][0]["macd"]), 5)        if mc.get("values") else None,
        "macd_sig": round(float(mc["values"][0]["macd_signal"]), 5) if mc.get("values") else None,
        "ema20":    round(float(e2["values"][0]["ema"]), 2)         if e2.get("values") else None,
        "ema50":    round(float(e5["values"][0]["ema"]), 2)         if e5.get("values") else None,
    }

SYS = """Forex/gold signal assistant. Analyse RSI,MACD,EMA20,EMA50 on 1h.
BUY: price>EMA20>EMA50 AND MACD>macd_signal AND RSI 40-65
SELL: price<EMA20<EMA50 AND MACD<macd_signal AND RSI 35-60
WAIT: RSI>70 or RSI<30 or mixed
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

def build_msg(m, sig, lv):
    s  = sig.get("signal","WAIT")
    em = {"BUY":"🟢","SELL":"🔴","HOLD":"🟡","WAIT":"⏳"}.get(s,"⏳")
    ic = "🥇" if "XAU" in m["symbol"] else "💶"
    dp = 2 if "XAU" in m["symbol"] else 4
    msg = f"""{ic} <b>Goldone — {m['symbol']}</b>
━━━━━━━━━━━━━━━
💰 <b>Price:</b> {m['price']:.{dp}f}   📊 <b>RSI:</b> {m['rsi']}
{em} <b>{s}</b>  ({sig.get('confidence','—')}% confidence)
━━━━━━━━━━━━━━━\n"""
    if lv:
        msg += f"🎯 Entry: {lv['entry']}\n🛑 SL: {lv['sl']} ({lv['sl_d']})\n✅ TP: {lv['tp']} ({lv['tp_d']})\n⚖️ R:R {lv['rr']}\n━━━━━━━━━━━━━━━\n"
    msg += f"📝 {sig.get('reason','')}\n⚠️ <i>{sig.get('caution','')}</i>\n🕐 {ist_now().strftime('%d %b %H:%M IST')}"
    return msg

def main():
    log.info(f"Started — {ist_now().strftime('%A %H:%M IST')}")
    if not is_trading_hour():
        log.info("Outside trading hours. Exit.")
        return
    for symbol in ["XAU/USD", "EUR/USD"]:
        try:
            m   = fetch(symbol)
            sig = get_signal(m)
            lv  = calc_levels(symbol, m["price"], sig.get("signal","WAIT"))
            send_tg(build_msg(m, sig, lv))
            log.info(f"{symbol} → {sig.get('signal')} ✓")
            time.sleep(3)
        except Exception as e:
            log.error(f"{symbol}: {e}")
            try: send_tg(f"⚠️ Forex Error ({symbol}): {str(e)[:150]}")
            except: pass

if __name__ == "__main__":
    main()
