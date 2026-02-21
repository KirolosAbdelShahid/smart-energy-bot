import os
import json
import time
import threading
import requests
from flask import Flask
from groq import Groq
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# ===== Config =====
BLYNK_TOKEN = os.environ.get("BLYNK_AUTH", "PQQtawp93VKXnQBxMMzEr7wF47fKXe5R")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
BLYNK_BASE = "https://blynk.cloud/external/api/get"
LOADS = ["Lomba", "Marwaha", "Shaffat", "Motor", "Tala9a"]
LOADS_AR = ["لمبة", "مروحة", "شفاط", "موتور", "تلاجة"]

print(f"GROQ_API_KEY set: {bool(GROQ_API_KEY)} (len={len(GROQ_API_KEY)})")
print(f"TELEGRAM_TOKEN set: {bool(TELEGRAM_TOKEN)}")

# Build Groq client only if key is set
groq_client = None
if GROQ_API_KEY:
    groq_client = Groq(api_key=GROQ_API_KEY)
    print("Groq client initialized successfully")
else:
    print("WARNING: GROQ_API_KEY is empty!")

flask_app = Flask(__name__)

@flask_app.route('/')
def home():
    return 'Smart Energy Bot is running!'

@flask_app.route('/health')
def health():
    return json.dumps({"status": "ok", "groq": bool(groq_client)})

def run_flask():
    port = int(os.environ.get('PORT', 8080))
    flask_app.run(host='0.0.0.0', port=port, use_reloader=False)

def fetch_blynk_data():
    data = {}
    for i, name in enumerate(LOADS_AR):
        try:
            w = float(requests.get(f"{BLYNK_BASE}?token={BLYNK_TOKEN}&pin=V{i}", timeout=5).text)
            pf = float(requests.get(f"{BLYNK_BASE}?token={BLYNK_TOKEN}&pin=V{i+5}", timeout=5).text)
            kwh = float(requests.get(f"{BLYNK_BASE}?token={BLYNK_TOKEN}&pin=V{i+10}",timeout=5).text)
            va = float(requests.get(f"{BLYNK_BASE}?token={BLYNK_TOKEN}&pin=V{i+15}",timeout=5).text)
            data[name] = {
                "W": round(w, 2),
                "PF": round(pf, 2),
                "kWh": round(kwh, 4),
                "VA": round(va, 2)
            }
        except Exception as e:
            data[name] = {"error": str(e)}
    return data

SYSTEM_PROMPT = (
    "You are a smart electrical assistant. "
    "Speak in Egyptian Arabic (3amiya). "
    "You have live data from a smart energy meter monitoring 5 electrical loads. "
    "Analyze data and answer practically using real numbers from the data."
)

def ask_groq(user_question, energy_data):
    if not groq_client:
        return "GROQ_API_KEY missing - AI not available"
    user_content = "Energy meter data now:\n" + json.dumps(energy_data, ensure_ascii=False, indent=2) + "\nUser question: " + user_question
    try:
        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_content}
            ],
            temperature=0.7,
            max_tokens=1024,
            stream=False
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"Groq error: {str(e)}"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "اهلا! انا بوت العداد الذكي\n\n"
        "سالني اي حاجة عن الكهرباء:\n"
        "- ليه النور غالي الشهر ده?\n"
        "- مين اكتر حاجة بتاكل كهرباء?\n"
        "- /status تشوف كل الاحمال دلوقتي"
    )
    await update.message.reply_text(msg)

async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("جاري جلب البيانات من العداد...")
    data = fetch_blynk_data()
    msg = "حالة العداد دلوقتي:\n\n"
    total_w = 0
    for name, vals in data.items():
        if "error" not in vals:
            w = vals["W"]
            pf = vals["PF"]
            kwh = vals["kWh"]
            icon = "\U0001f534" if pf < 0.85 else "\U0001f7e2"
            total_w += w
            msg += f"{icon} {name}: {w}W | PF:{pf} | {kwh}kWh\n"
        else:
            msg += f"\u26a0\ufe0f {name}: {vals['error']}\n"
    msg += f"\n\u26a1 Total: {round(total_w,1)}W"
    await update.message.reply_text(msg)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_msg = update.message.text
    thinking = await update.message.reply_text("بجيب البيانات من العداد...")
    data = fetch_blynk_data()
    await thinking.edit_text("بحلل البيانات...")
    reply = ask_groq(user_msg, data)
    await thinking.edit_text(reply)

if __name__ == "__main__":
    print("Smart Energy Bot starting...")
    # Wait for old instance to release Telegram polling
    time.sleep(15)
    print("Smart Energy Bot started!")

    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()

    if not TELEGRAM_TOKEN:
        print("ERROR: TELEGRAM_TOKEN not set!")
        import sys
        sys.exit(1)

    application = (
        ApplicationBuilder()
        .token(TELEGRAM_TOKEN)
        .connect_timeout(30)
        .get_updates_read_timeout(45)
        .get_updates_connect_timeout(30)
        .read_timeout(30)
        .build()
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("status", status_cmd))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    application.run_polling(
        drop_pending_updates=True,
        allowed_updates=Update.ALL_TYPES,
        close_loop=False
    )
