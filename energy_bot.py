import os
import json
import threading
import requests
from flask import Flask
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# ===== Config =====
BLYNK_TOKEN = os.environ.get("BLYNK_AUTH", "PQQtawp93VKXnQBxMMzEr7wF47fKXe5R")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
BLYNK_BASE = "https://blynk.cloud/external/api/get"
LOADS_AR = ["\u0644\u0645\u0628\u0629", "\u0645\u0631\u0648\u062d\u0629", "\u0634\u0641\u0627\u0637", "\u0645\u0648\u062a\u0648\u0631", "\u062a\u0644\u0627\u062c\u0629"]

print(f"GEMINI_API_KEY set: {bool(GEMINI_API_KEY)}")
print(f"TELEGRAM_TOKEN set: {bool(TELEGRAM_TOKEN)}")

flask_app = Flask(__name__)

@flask_app.route('/')
def home():
    return 'Smart Energy Bot is running with Gemini!'

@flask_app.route('/health')
def health():
    return json.dumps({"status": "ok", "gemini_key": bool(GEMINI_API_KEY)})

def run_flask():
    port = int(os.environ.get('PORT', 8080))
    flask_app.run(host='0.0.0.0', port=port, use_reloader=False)

def fetch_blynk_data():
    data = {}
    for i, name in enumerate(LOADS_AR):
        try:
            w   = float(requests.get(f"{BLYNK_BASE}?token={BLYNK_TOKEN}&pin=V{i}",    timeout=5).text)
            pf  = float(requests.get(f"{BLYNK_BASE}?token={BLYNK_TOKEN}&pin=V{i+5}",  timeout=5).text)
            kwh = float(requests.get(f"{BLYNK_BASE}?token={BLYNK_TOKEN}&pin=V{i+10}", timeout=5).text)
            va  = float(requests.get(f"{BLYNK_BASE}?token={BLYNK_TOKEN}&pin=V{i+15}", timeout=5).text)
            data[name] = {"W": round(w,2), "PF": round(pf,2), "kWh": round(kwh,4), "VA": round(va,2)}
        except Exception as e:
            data[name] = {"error": str(e)}
    return data

SYSTEM_PROMPT = (
    "\u0627\u0646\u062a \"\u0639\u062f\u0627\u062f\u064a\" - \u0627\u0644\u0645\u0633\u0627\u0639\u062f \u0627\u0644\u0630\u0643\u064a \u0644\u0644\u0628\u064a\u062a \u0627\u0644\u0645\u0635\u0631\u064a.\n"
    "\u0628\u062a\u062a\u0643\u0644\u0645 \u0639\u0627\u0645\u064a\u0629 \u0645\u0635\u0631\u064a\u0629 \u0637\u0628\u064a\u0639\u064a\u0629 \u062c\u062f\u0627\u064b.\n"
    "\u0645\u0647\u0645\u062a\u0643:\n"
    "1. \u062a\u062d\u0644\u064a\u0644 \u0628\u064a\u0627\u0646\u0627\u062a \u0639\u062f\u0627\u062f \u0627\u0644\u0643\u0647\u0631\u0628\u0627\u0621 (\u0644\u0645\u0628\u0629 \u060c \u0645\u0631\u0648\u062d\u0629 \u060c \u0634\u0641\u0627\u0637 \u060c \u0645\u0648\u062a\u0648\u0631 \u060c \u062a\u0644\u0627\u062c\u0629).\n"
    "2. \u0644\u0648 PF \u0623\u0642\u0644 \u0645\u0646 0.85 \u0642\u0648\u0644 \u0625\u0646 \u0627\u0644\u062c\u0647\u0627\u0632 \u0628\u064a\u0647\u062f\u0631 \u0643\u0647\u0631\u0628\u0627\u0621.\n"
    "3. \u062a\u0643\u0644\u0641\u0629 \u0627\u0644\u0643\u064a\u0644\u0648 \u0648\u0627\u062a \u0633\u0627\u0639\u0629 1.35 \u062c\u0646\u064a\u0647.\n"
    "4. \u0642\u0627\u0631\u0646 \u0628\u064a\u0646 \u0627\u0644\u0623\u062d\u0645\u0627\u0644 \u0648\u0642\u0648\u0644 \u0645\u064a\u0646 \u0623\u0643\u062a\u0631 \u0648\u0627\u062d\u062f \u0628\u064a\u0633\u062d\u0628.\n"
    "5. \u0627\u062f\u064a \u0646\u0635\u0627\u064a\u062d \u0639\u0645\u0644\u064a\u0629 \u0644\u062a\u0648\u0641\u064a\u0631 \u0627\u0644\u0643\u0647\u0631\u0628\u0627\u0621.\n"
    "\u062e\u0644\u064a\u0643 \u0648\u062f\u0648\u062f \u0648\u0645\u062e\u062a\u0635\u0631 \u0648\u0645\u0641\u064a\u062f."
)

def ask_gemini(user_question, energy_data):
    if not GEMINI_API_KEY:
        return "\u064a\u0627 \u0635\u0627\u062d\u0628\u064a \u0645\u0641\u064a\u0634 \u0645\u0641\u062a\u0627\u062d Gemini API.. \u0634\u063a\u0644\u0646\u064a \u0627\u0644\u0623\u0648\u0644!"

    data_text = json.dumps(energy_data, ensure_ascii=False, indent=2)
    prompt = SYSTEM_PROMPT + "\n\n" + data_text + "\n\n" + user_question

    payload = {
        "contents": [{
            "parts": [{"text": prompt}]
        }],
        "generationConfig": {
            "temperature": 0.7,
            "maxOutputTokens": 1000,
        }
    }

    try:
        url = f"https://generativelanguage.googleapis.com/v1/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
        r = requests.post(url, json=payload, timeout=30)
        if r.status_code == 200:
            return r.json()['candidates'][0]['content']['parts'][0]['text']
        else:
            return f"\u062d\u0635\u0644\u062a \u0645\u0634\u0643\u0644\u0629 \u0641\u064a Gemini (\u0643\u0648\u062f {r.status_code}): {r.text[:200]}"
    except Exception as e:
        return f"\u064a\u0627 \u0633\u0627\u062a\u0631! \u062d\u0635\u0644 \u062e\u0637\u0623: {str(e)}"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = "\u064a\u0627 \u0623\u0647\u0644\u0627\u064b \u0628\u064a\u0643! \u0623\u0646\u0627 \u0639\u062f\u0627\u062f\u064a \u0627\u0633\u0623\u0644\u0646\u064a \u0639\u0646 \u0643\u0647\u0631\u0628\u0627\u0621 \u0628\u064a\u062a\u0643. /status \u0644\u0634\u0648\u0641 \u0627\u0644\u062d\u0627\u0644\u0629 | /tips \u0644\u0646\u0635\u0627\u064a\u062d \u0627\u0644\u062a\u0648\u0641\u064a\u0631"
    await update.message.reply_text(msg)

async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("\u0628\u0634\u0648\u0641\u0644\u0643 \u0627\u0644\u0639\u062f\u0627\u062f.. \u062b\u0627\u0646\u064a\u0629 \u0648\u0627\u062d\u062f\u0629")
    data = fetch_blynk_data()
    msg = "\u062d\u0627\u0644\u0629 \u0627\u0644\u0639\u062f\u0627\u062f \u062f\u0644\u0648\u0642\u062a\u064a:\n"
    total_w = 0
    for name, vals in data.items():
        if "error" not in vals:
            w = vals["W"]; pf = vals["PF"]; kwh = vals["kWh"]
            total_w += w
            icon = "R" if pf < 0.85 else "G"
            cost_month = round(kwh * 24 * 30 * 1.35, 2)
            msg += f"{icon} {name}: {w}W | PF:{pf} | {kwh}kWh | {cost_month} EGP/month\n"
        else:
            msg += f"? {name}: \u0642\u0631\u0627\u0621\u0629 \u063a\u0644\u0637\n"
    msg += f"\n\u0627\u0644\u0633\u062d\u0628 \u0627\u0644\u0625\u062c\u0645\u0627\u0644\u064a: {round(total_w,1)}W"
    await update.message.reply_text(msg)

async def tips_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    thinking = await update.message.reply_text("\u0628\u062d\u0644\u0644 \u0627\u0644\u0623\u062d\u0645\u0627\u0644..")
    data = fetch_blynk_data()
    reply = ask_gemini("\u0627\u062f\u064a\u0646\u064a \u0646\u0635\u0627\u064a\u062d \u062a\u0648\u0641\u064a\u0631 \u0628\u0646\u0627\u0621 \u0639\u0644\u0649 \u0627\u0644\u0628\u064a\u0627\u0646\u0627\u062a \u062f\u064a \u0648\u0642\u0648\u0644\u064a \u0645\u064a\u0646 \u0623\u0643\u062a\u0631 \u062d\u0645\u0644 \u0628\u064a\u0633\u062d\u0628", data)
    await thinking.edit_text(reply)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_msg = update.message.text
    thinking = await update.message.reply_text("\u062b\u0648\u0627\u0646\u064a \u0623\u0634\u0648\u0641\u0644\u0643 \u0627\u0644\u062f\u0646\u064a\u0627..")
    data = fetch_blynk_data()
    reply = ask_gemini(user_msg, data)
    await thinking.edit_text(reply)

if __name__ == "__main__":
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    if not TELEGRAM_TOKEN:
        print("TELEGRAM_TOKEN is missing!")
    else:
        app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("status", status_cmd))
        app.add_handler(CommandHandler("tips", tips_cmd))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        print("Bot is polling...")
        app.run_polling()
