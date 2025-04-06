# Aladdin AI Trader - Telegram Alert + Smart Market Scanner + Entry Execution
# =======================================================
# This script sends Telegram alerts, scans the market, and places trades via Alpaca.

import requests
import json
import datetime
import pytz
from alpaca_trade_api.rest import REST, TimeFrame
import time
import sys
from flask import Flask, request
from threading import Thread
from openai import OpenAI

# Load credentials from config
with open("config.json") as config_file:
    config = json.load(config_file)

BOT_TOKEN = config["TELEGRAM_BOT_TOKEN"]
USER_ID = config["TELEGRAM_USER_ID"]
ALPACA_API_KEY = config["ALPACA_API_KEY"]
ALPACA_SECRET_KEY = config["ALPACA_SECRET_KEY"]
OPENAI_API_KEY = config["OPENAI_API_KEY"]

# Initialize APIs
api = REST(ALPACA_API_KEY, ALPACA_SECRET_KEY, base_url="https://paper-api.alpaca.markets")
client = OpenAI(api_key=OPENAI_API_KEY)

# Flask server for webhook listener
app = Flask(__name__)

# Global vars to hold session state (temporary)
session_target = None
session_risk = None

# Telegram send
def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": USER_ID,
        "text": message
    }
    requests.post(url, json=payload)

# Genie logic

def genie_trade_strategy_from_goal(target_profit, risk_tolerance, capital):
    prompt = f"""
The user wants to make ${target_profit} today and is willing to risk ${risk_tolerance}.\n
Their Alpaca capital is currently ${capital}.\n
Reply in 2 lines MAXIMUM, in simple language.\nEstimate if it's possible and what a realistic profit target is based on their capital and risk.
"""
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are the Genie from Aladdin. Give simple, non-technical advice to traders."},
                {"role": "user", "content": prompt}
            ]
        )
        strategy = response.choices[0].message.content.strip()
        send_telegram_message(f"🧞 Your Genie’s Trading Plan:\n{strategy}")
        return strategy
    except Exception as e:
        error_msg = f"❌ Genie strategy error: {e}"
        send_telegram_message(error_msg)
        return None

# Scanner

def smart_premarket_scan():
    message = "🧞‍♂️ Aladdin AI Scanner Activated\nTracking premarket volume and gainers...\n"
    try:
        tickers = ["TSLA", "AMD", "NVDA", "AAPL", "BFRG"]
        selected = []
        for symbol in tickers:
            snapshot = api.get_snapshot(symbol)
            try:
                bar = snapshot.daily_bar
                if not bar:
                    continue
                volume = bar.v
                price = bar.c
                if volume > 150000 and 1 < price < 100:
                    selected.append((symbol, price, volume))
            except:
                continue

        if selected:
            selected.sort(key=lambda x: x[2], reverse=True)
            for s in selected[:3]:
                message += f"{s[0]}: Price ${s[1]:.2f} | Vol: {s[2]}\n"
            top_pick = selected[0][0]
            message += f"\n🎯 Executing trade for top pick: {top_pick}"
            execute_trade(top_pick)
        else:
            message += "🤖 No high-probability premarket setups found."

        send_telegram_message(message)

    except Exception as e:
        send_telegram_message(f"❌ Scanner error: {e}")

# Telegram webhook handler
@app.route(f"/webhook", methods=["POST"])
def telegram_webhook():
    global session_target, session_risk
    data = request.get_json()
    if "message" in data:
        text = data["message"].get("text", "")
        chat_id = data["message"]["chat"]["id"]

        if text.lower().startswith("/goal"):
            try:
                session_target = float(text.split()[1])
                send_telegram_message("✅ Noted! Now tell me how much you're willing to risk using /risk <amount> 💸")
            except:
                send_telegram_message("❌ Please enter your goal like this: /goal 500")

        elif text.lower().startswith("/risk"):
            try:
                session_risk = float(text.split()[1])
                capital = float(api.get_account().cash)
                genie_trade_strategy_from_goal(session_target, session_risk, capital)
            except:
                send_telegram_message("❌ Please enter your risk like this: /risk 200")

        elif text.lower() == "/start":
            send_telegram_message("🧞 Welcome back, Aladdin. Set your daily trading goal using /goal <amount>")

    return {"ok": True}

# Trade executor

def execute_trade(symbol, qty=100):
    try:
        api.submit_order(symbol=symbol, qty=qty, side="buy", type="market", time_in_force="gtc")
        send_telegram_message(f"🚀 TRADE EXECUTED: Bought {qty} shares of {symbol} (Market Order)")
    except Exception as e:
        send_telegram_message(f"❌ Trade execution failed: {e}")

# MAIN (local test)
if __name__ == "__main__":
    def run_flask():
        app.run(port=5001)

    flask_thread = Thread(target=run_flask)
    flask_thread.start()

    force = "--test" in sys.argv
    dubai_now = datetime.datetime.now(pytz.timezone("Asia/Dubai"))
    if force or (16 <= dubai_now.hour < 17 or (dubai_now.hour == 17 and dubai_now.minute < 30)):
        smart_premarket_scan()
    else:
        print("⏱️ Outside of premarket scan hours. Use --test to force.")
