import os
import asyncio
import aiohttp
import requests
import yfinance as yf
from datetime import date

# ---------------- CONFIG ----------------
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = int(os.getenv("CHAT_ID"))

# Markets
BINANCE_MARKETS = ["BTCUSDT", "XAUUSDT"]  # Realtime via Binance
YF_MARKETS = {
    "US30": "^DJI",
    "NAS100": "^NDX",
    "USDJPY": "JPY=X"
}  # Daily data via Yahoo

INTERVAL = 60  # Loop seconds

# ---------------- STATE ----------------
stats = {"wins":0,"losses":0,"total":0,"rr":0}
active_trades = {}
trade_history = []

# ---------------- TELEGRAM ----------------
async def send(session, msg, buttons=None):
    url=f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload={"chat_id":CHAT_ID,"text":msg}
    if buttons:
        payload["reply_markup"]=buttons
    await session.post(url,json=payload)

def buttons():
    return {"inline_keyboard":[
        [{"text":"📊 Stats","callback_data":"stats"}],
        [{"text":"📈 Active Trades","callback_data":"active"}],
        [{"text":"📉 History","callback_data":"history"}]
    ]}

# ---------------- DASHBOARD ----------------
def dashboard():
    winrate=(stats["wins"]/stats["total"]*100) if stats["total"] else 0
    return f"""
📊 VIP DASHBOARD
📅 {date.today()}
💹 Trades Today: {stats['total']}
✅ Wins: {stats['wins']}
❌ Losses: {stats['losses']}
📈 Win Rate: {round(winrate,2)}%
💰 Total RR: {stats['rr']}
📊 Active: {', '.join(active_trades.keys()) if active_trades else 'None'}
"""

# ---------------- PRICE FETCH ----------------
def get_binance_price(symbol):
    url=f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}"
    data=requests.get(url).json()
    return float(data['price'])

def get_yf_close(symbol):
    data=yf.Ticker(symbol).history(period="2d", interval="1d")
    if data.empty: return None
    return data['Close'].iloc[-1]

# ---------------- TRADE LOGIC ----------------
def simple_signal(price, prev_price):
    if prev_price is None: return None
    change=(price-prev_price)/prev_price
    if change>0.01: return "BUY"
    elif change<-0.01: return "SELL"
    return None

# ---------------- MONITOR ----------------
async def monitor_trade(session, market, trade):
    while True:
        await asyncio.sleep(60)
        try:
            if market in BINANCE_MARKETS:
                price=get_binance_price(market)
            else:
                price=get_yf_close(YF_MARKETS[market])
                if price is None: continue
            if market not in active_trades: return

            # BUY
            if trade["dir"]=="BUY":
                if price>=trade["tp1"] and not trade.get("tp1_hit"):
                    trade["tp1_hit"]=True
                    await send(session,f"💰 {market} TP1 HIT ✅\n🔒 SL moved to BE")
                if price>=trade["tp2"]:
                    stats["wins"]+=1; stats["rr"]+=3; stats["total"]+=1
                    await send(session,f"🎯 {market} TP2 HIT 🚀 WIN")
                    trade_history.append((market,"WIN")); del active_trades[market]; return
                if price<=trade["sl"]:
                    stats["losses"]+=1; stats["total"]+=1
                    await send(session,f"❌ {market} SL HIT")
                    trade_history.append((market,"LOSS")); del active_trades[market]; return

            # SELL
            else:
                if price<=trade["tp1"] and not trade.get("tp1_hit"):
                    trade["tp1_hit"]=True
                    await send(session,f"💰 {market} TP1 HIT ✅\n🔒 SL moved to BE")
                if price<=trade["tp2"]:
                    stats["wins"]+=1; stats["rr"]+=3; stats["total"]+=1
                    await send(session,f"🎯 {market} TP2 HIT 🚀 WIN")
                    trade_history.append((market,"WIN")); del active_trades[market]; return
                if price>=trade["sl"]:
                    stats["losses"]+=1; stats["total"]+=1
                    await send(session,f"❌ {market} SL HIT")
                    trade_history.append((market,"LOSS")); del active_trades[market]; return
        except:
            continue

# ---------------- CALLBACK ----------------
async def handle_callbacks(session):
    offset=None
    while True:
        url=f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates?timeout=60"
        if offset: url+=f"&offset={offset}"
        async with session.get(url) as resp:
            updates=await resp.json()
        for update in updates.get("result",[]):
            offset=update["update_id"]+1
            if "callback_query" in update:
                cmd=update["callback_query"]["data"]
                if cmd=="stats": await send(session,dashboard())
                elif cmd=="active":
                    msg="📈 ACTIVE TRADES\n"
                    for m,t in active_trades.items(): msg+=f"{m}: {t['dir']} @ {round(t['entry'],2)}\n"
                    if not active_trades: msg+="None"
                    await send(session,msg)
                elif cmd=="history":
                    msg="📉 HISTORY\n"
                    for h in trade_history: msg+=f"{h[0]} - {h[1]}\n"
                    if not trade_history: msg+="No trades yet"
                    await send(session,msg)

# ---------------- MAIN ----------------
async def main():
    print("🚀 VIP SIGNAL BOT RUNNING")
    prev_prices={m:None for m in BINANCE_MARKETS+list(YF_MARKETS.keys())}

    async with aiohttp.ClientSession() as session:
        asyncio.create_task(handle_callbacks(session))

        while True:
            for market in BINANCE_MARKETS+list(YF_MARKETS.keys()):
                if market in active_trades: continue
                try:
                    # Get price
                    if market in BINANCE_MARKETS:
                        price=get_binance_price(market)
                    else:
                        price=get_yf_close(YF_MARKETS[market])
                        if price is None: continue

                    signal=simple_signal(price, prev_prices[market])
                    prev_prices[market]=price
                    if signal is None: continue

                    # SL/TP
                    risk=price*0.002
                    if signal=="BUY":
                        trade={"dir":"BUY","entry":price,"sl":price-risk,"tp1":price+risk,"tp2":price+risk*3}
                    else:
                        trade={"dir":"SELL","entry":price,"sl":price+risk,"tp1":price-risk,"tp2":price-risk*3}

                    active_trades[market]=trade
                    analysis=f"""
💹 VIP TRADE - {market}
📊 Direction: {signal}
📍 Entry: {round(price,2)}
🕒 Execution TF: 15m
⚖️ Risk Management: 0.2%
💡 Reason: Simple momentum based on previous price change
💰 TP1/TP2 & SL set
"""
                    await send(session,analysis,buttons())
                    asyncio.create_task(monitor_trade(session,market,trade))

                except Exception as e:
                    print("Error:",e)
            await asyncio.sleep(INTERVAL)

if __name__=="__main__":
    asyncio.run(main())
