import os
import asyncio
import aiohttp
import requests
from datetime import datetime, date

# ---------------- CONFIG ----------------
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = int(os.getenv("CHAT_ID"))
ALPHA_API_KEY = os.getenv("ALPHA_VANTAGE_KEY")

BINANCE_MARKETS = ["BTCUSDT","XAUUSDT"]
AV_MARKETS = {
    "US30": "DJI",
    "NAS100": "IXIC",
    "USDJPY": "USDJPY"
}

INTERVAL=60

stats={"wins":0,"losses":0,"total":0,"rr":0}
active_trades={}
trade_history=[]

# ---------------- TELEGRAM ----------------
async def send(session,msg,buttons=None):
    url=f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload={"chat_id":CHAT_ID,"text":msg}
    if buttons: payload["reply_markup"]=buttons
    await session.post(url,json=payload)

def buttons():
    return {
        "inline_keyboard":[
            [{"text":"📊 Stats","callback_data":"stats"}],
            [{"text":"📈 Active Trades","callback_data":"active"}],
            [{"text":"📉 History","callback_data":"history"}]
        ]
    }

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
💰 RR Gained: {stats['rr']}
📊 Active: {', '.join(active_trades.keys()) if active_trades else 'None'}
"""

# ---------------- PRICE FETCH ----------------
def get_binance_price(symbol):
    url=f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}"
    data=requests.get(url).json()
    return float(data['price'])

def get_alpha_intraday(symbol):
    url=(
        "https://www.alphavantage.co/query?"
        f"function=FX_INTRADAY&from_symbol={symbol[:3]}"
        f"&to_symbol={symbol[-3:]}&interval=15min&apikey={ALPHA_API_KEY}"
    )
    r=requests.get(url).json()
    try:
        latest=list(r[f"Time Series FX (15min)"].values())[0]
        return float(latest["4. close"])
    except:
        return None

def get_alpha_index(symbol):
    url=(
        "https://www.alphavantage.co/query?"
        "function=TIME_SERIES_INTRADAY&symbol="+symbol+
        "&interval=15min&apikey="+ALPHA_API_KEY
    )
    r=requests.get(url).json()
    try:
        latest=list(r["Time Series (15min)"].values())[0]
        return float(latest["4. close"])
    except:
        return None

# ---------------- SIMPLE SMC SIGNAL ----------------
def simple_signal(price,prev):
    if prev is None: return None
    ch=(price-prev)/prev
    if ch>=0.01: return "BUY"
    if ch<=-0.01: return "SELL"
    return None

# ---------------- MONITOR TRADE ----------------
async def monitor_trade(session,market,trade):
    while True:
        await asyncio.sleep(60)
        try:
            if market in BINANCE_MARKETS:
                price=get_binance_price(market)
            else:
                if market=="USDJPY":
                    price=get_alpha_intraday("USDJPY")
                else:
                    price=get_alpha_index(AV_MARKETS[market])
            if price is None: continue
            if market not in active_trades: return

            if trade["dir"]=="BUY":
                if price>=trade["tp1"] and not trade.get("tp1_hit"):
                    trade["tp1_hit"]=True
                    await send(session,f"💰 {market} TP1 HIT ✅\n🔒 SL moved to BE")
                if price>=trade["tp2"]:
                    stats["wins"]+=1;stats["rr"]+=3;stats["total"]+=1
                    await send(session,f"🎯 {market} TP2 HIT 🚀 WIN")
                    trade_history.append((market,"WIN"));del active_trades[market];return
                if price<=trade["sl"]:
                    stats["losses"]+=1;stats["total"]+=1
                    await send(session,f"❌ {market} SL HIT")
                    trade_history.append((market,"LOSS"));del active_trades[market];return
