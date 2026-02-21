import os
import json
import time
import threading
import requests
from flask import Flask
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# ===== Config =====
BLYNK_TOKEN = os.environ.get("BLYNK_AUTH", "PQQtawp93VKXnQBxMMzEr7wF47fKXe5R")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "").strip()
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
BLYNK_BASE = "https://blynk.cloud/external/api/get"
OPENAI_URL = "https://api.openai.com/v1/chat/completions"
MODEL = "gpt-4o-mini"

LOADS_AR = ["لمبة", "مروحة", "شفاط", "موتور", "تلاجة"]

print(f"OPENAI_API_KEY set: {bool(OPENAI_API_KEY)} (len={len(OPENAI_API_KEY)})")
print(f"TELEGRAM_TOKEN set: {bool(TELEGRAM_TOKEN)}")

flask_app = Flask(__name__)

@flask_app.route('/')
def home():
    return 'Smart Energy Bot is running!'

@flask_app.route('/health')
def health():
    return json.dumps({"status": "ok", "openai_key": bool(OPENAI_API_KEY), "model": MODEL})

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

SYSTEM_PROMPT = """انت مساعد كهربي ذكي اسمك عدادي.
بتتكلم بالعامية المصرية بشكل طبيعي وودود.
عندك بيانات من عداد كهرباء ذكي بيراقب 5 احمال كهربية في البيت:
- لمبة، مروحة، شفاط، موتور، تلاجة

لما حد يسألك:
- اديه ارقام حقيقية من البيانات
- وضح ايه اللي بياكل كهرباء اكتر
- اقترح حلول عملية توفر فلوس
- لو PF اقل من 0.85 قوله في مشكلة في الحمل ده
- اشرح بطريقة بسيطة يفهمها اي حد
- خليك مختصر ومفيد"""

def ask_openai(user_question, energy_data):
    if not OPENAI_API_KEY:
        return "مفيش OPENAI_API_KEY - الذكاء الاصطناعي مش شغال"
    
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }
    
    data_summary = ""
    total_w = 0
    for name, vals in energy_data.items():
        if "error" not in vals:
            total_w += vals.get("W", 0)
            pf_status = "(مشكلة في الحمل!)" if vals.get("PF", 1) < 0.85 else ""
            data_summary += f"- {name}: {vals['W']}W | PF:{vals['PF']} {pf_status} | {vals['kWh']}kWh | {vals['VA']}VA\n"
        else:
            data_summary += f"- {name}: خطأ في القراءة\n"
    
    user_content = f"بيانات العداد دلوقتي:\n{data_summary}\nالاجمالي: {round(total_w,1)}W\n\nسؤال المستخدم: {user_question}"
    
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": user_content}
        ],
        "temperature": 0.7,
        "max_tokens": 800
    }
    
    try:
        r = requests.post(OPENAI_URL, headers=headers, json=payload, timeout=30)
        if r.status_code == 200:
            return r.json()["choices"][0]["message"]["content"]
        elif r.status_code == 429:
            return "البوت وصل للحد المسموح، جرب تاني بعد شوية!"
        elif r.status_code == 401:
            return "مشكلة في مفتاح OpenAI - كلم المسؤول!"
        else:
            return f"خطأ {r.status_code}: {r.text[:200]}"
    except Exception as e:
        return f"خطأ في الاتصال: {str(e)}"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "اهلا! انا عدادي - بوت العداد الذكي \U0001f4a1\n\n"
        "بقدر اساعدك في:\n"
        "\U0001f50d ليه الفاتورة غالية الشهر ده?\n"
        "\U0001f4ca مين اكتر حاجة بتاكل كهرباء?\n"
        "\U0001f4b0 ازاي توفر في الكهرباء?\n\n"
        "الاوامر:\n"
        "/status - شوف كل الاحمال دلوقتي\n"
        "/tips - نصايح التوفير\n"
        "/help - المساعدة\n\n"
        "او اسالني اي سؤال بالعربي!"
    )
    await update.message.reply_text(msg)

async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("\U0001f504 جاري جلب البيانات من العداد...")
    data = fetch_blynk_data()
    msg = "\u26a1 حالة العداد دلوقتي:\n\n"
    total_w = 0
    for name, vals in data.items():
        if "error" not in vals:
            w   = vals["W"]
            pf  = vals["PF"]
            kwh = vals["kWh"]
            va  = vals["VA"]
            if pf < 0.85:
                icon = "\U0001f534"
                pf_note = " \u26a0\ufe0f PF منخفض!"
            else:
                icon = "\U0001f7e2"
                pf_note = ""
            total_w += w
            msg += f"{icon} {name}: {w}W | PF:{pf}{pf_note} | {kwh}kWh\n"
        else:
            msg += f"\u26a0\ufe0f {name}: خطأ في القراءة\n"
    msg += f"\n\u26a1 الاجمالي: {round(total_w,1)}W\n"
    cost_per_day = round(total_w * 24 / 1000 * 1.35, 2)
    msg += f"\U0001f4b0 تكلفة تقريبية/يوم: {cost_per_day} جنيه"
    await update.message.reply_text(msg)

async def tips_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("\U0001f504 بحلل البيانات واديك نصايح...")
    data = fetch_blynk_data()
    question = "اديني نصايح عملية لتوفير الكهرباء بناءا على البيانات دي"
    reply = ask_openai(question, data)
    await update.message.reply_text(reply)

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "\U0001f4cb الاوامر المتاحة:\n\n"
        "/start - الترحيب\n"
        "/status - حالة كل الاحمال دلوقتي\n"
        "/tips - نصايح توفير الكهرباء\n"
        "/help - الاوامر\n\n"
        "\U0001f4ac او اسالني بالعربي مثلاً:\n"
        "- ليه الفاتورة غالية?\n"
        "- مين اكتر حاجة بتاكل?\n"
        "- التلاجة بتاخد كام?"
    )
    await update.message.reply_text(msg)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_msg = update.message.text
    thinking = await update.message.reply_text("\U0001f504 بجيب البيانات من العداد...")
    data = fetch_blynk_data()
    await thinking.edit_text("\U0001f9e0 بحلل البيانات...")
    reply = ask_openai(user_msg, data)
    await thinking.edit_text(reply)

if __name__ == "__main__":
    print("Smart Energy Bot starting...")
    time.sleep(10)
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
    application.add_handler(CommandHandler("tips", tips_cmd))
    application.add_handler(CommandHandler("help", help_cmd))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    application.run_polling(
        drop_pending_updates=True,
        allowed_updates=Update.ALL_TYPES
    )
