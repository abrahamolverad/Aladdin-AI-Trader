# main.py - Aladdin AI Trader - Conversational ChatGPT-like Version 🌐
# ----------------------------------------------------------------------
# Telegram-connected trading assistant that responds to all messages like ChatGPT

import requests
import os
import datetime
import pytz
from alpaca_trade_api.rest import REST
from flask import Flask, request
from threading import Thread
from openai import OpenAI

# Load credentials from environment variables
BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
USER_ID = os.environ["TELEGRAM_USER_ID"]
ALPACA_API_KEY = os.environ["ALPACA_API_KEY"]
ALPACA_SECRET_KEY = os.environ["ALPACA_SECRET_KEY"]
OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]

# Initialize APIs
api = REST(ALPACA_API_KEY, ALPACA_SECRET_KEY, base_url="https://paper-api.alpaca.markets")
client = OpenAI(api_key=OPENAI_API_KEY)

# Flask app
app = Flask(__name__)

# Bot state
state = {
    "capital": 0,
    "target": None,
    "risk": None,
    "mode": None,
    "strategy_summary": None,
    "override": False
}

# Send message to Telegram

def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": USER_ID, "text": message}
    requests.post(url, json=payload)

# Main Genie function — full GPT reply like ChatGPT

def genie_chat(user_message):
    capital = float(api.get_account().cash)
    state["capital"] = capital

    context = f"""
You are Genie, a friendly trading assistant with access to the user's capital (${capital:.2f}).
You respond to *all messages* like ChatGPT — casual, trading, questions, anything.
If the user mentions a profit target or risk (even casually like 'wanna make 100 and risk 10'), try to extract it and remember it.
Only execute trades when they say something like 'auto', 'automatically', or 'go'.
Suggest stock picks if they say 'solo' or want ideas.
Answer everything naturally.
"""

    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",  # using 3.5 for now
            messages=[
                {"role": "system", "content": context},
                {"role": "user", "content": user_message}
            ]
        )

        reply = response.choices[0].message.content.strip()
        send_telegram_message(reply)

        # Try to extract trading intent manually from GPT follow-ups
        if any(kw in user_message.lower() for kw in ["auto", "automatically", "go"]):
            send_telegram_message("🎯 Auto-trading enabled. Executing now...")
            scan_and_trade()
        elif "solo" in user_message.lower():
            send_telegram_message("📋 Solo mode: Genie will suggest stocks, but not trade.")
            scan_and_trade(execute=False)

    except Exception as e:
        send_telegram_message(f"❌ Genie error: {e}")
        print("🔥 Exception:", e)

# Telegram webhook
@app.route("/webhook", methods=["POST"])
def telegram_webhook():
    data = request.get_json()
    if "message" in data:
        text = data["message"].get("text", "")
        genie_chat(text)
    return {"ok": True}

# Stock scanner & trade logic

def scan_and_trade(execute=True):
    tickers = ["TSLA", "AMD", "NVDA", "AAPL"]
    message = "🦞 Genie Scan Results:\n"
    try:
        selected = []
        for symbol in tickers:
            snapshot = api.get_snapshot(symbol)
            bar = snapshot.daily_bar
            if not bar:
                continue
            volume = bar.v
            price = bar.c
            if volume > 150000 and 1 < price < 100:
                selected.append((symbol, price, volume))

        if selected:
            selected.sort(key=lambda x: x[2], reverse=True)
            for sym, prc, vol in selected[:3]:
                message += f"{sym}: ${prc:.2f} | Vol: {vol}\n"

            top = selected[0]
            qty = int(state["risk"] // top[1]) if state["risk"] else 0
            if execute and qty > 0:
                api.submit_order(symbol=top[0], qty=qty, side="buy", type="market", time_in_force="gtc")
                message += f"🚀 Executed trade for {top[0]} with {qty} shares"
            elif not execute:
                message += f"🔍 Recommendation only: {top[0]} looks best"
            else:
                message += "⚠️ Risk too low to trade"
        else:
            message += "🤖 No high-probability picks today."

        send_telegram_message(message)

    except Exception as e:
        send_telegram_message(f"❌ Scanner error: {e}")

# Start Flask server
if __name__ == "__main__":
    def run_flask():
        app.run(host="0.0.0.0", port=8080)

    Thread(target=run_flask).start()
    print("✅ Genie Flask app running and listening for Telegram messages...")
