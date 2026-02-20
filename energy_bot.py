import os
import json
import threading
import requests
from flask import Flask
from groq import Groq
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

BLYNK_TOKEN = os.environ.get("BLYNK_AUTH", "PQQtawp93VKXnQBxMMzEr7wF47fKXe5R")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
BLYNK_TEMPLATE = os.environ.get("BLYNK_TEMPLATE", "TMPL5zvDb_CHW")

BLYNK_BASE = "https://blynk.cloud/external/api/get"
LOADS = ["لمبة", "مروحة", "شفاط", "موتور", "تلاجة"]

groq_client = Groq(api_key=GROQ_API_KEY)
flask_app = Flask(__name__)

@flask_app.route('/')
def home():
    return 'Smart Energy Bot is running!'

def run_flask():
    port = int(os.environ.get('PORT', 8080))
    flask_app.run(host='0.0.0.0', port=port, use_reloader=False)

def fetch_blynk_data():
    data = {}
    for i, name in enumerate(LOADS):
        try:
            w = float(requests.get(f"{BLYNK_BASE}?token={BLYNK_TOKEN}&v{i}", timeout=5).text)
            pf = float(requests.get(f"{BLYNK_BASE}?token={BLYNK_TOKEN}&v{i+5}", timeout=5).text)
            kwh = float(requests.get(f"{BLYNK_BASE}?token={BLYNK_TOKEN}&v{i+10}", timeout=5).text)
            data[name] = {"قدرة_W": round(w, 2), "معامل_القدرة": round(pf, 2), "طاقة_kWh": round(kwh, 4)}
        except Exception as e:
            data[name] = {"خطأ": str(e)}
    return data

SYSTEM_PROMPT = "انت مساعد ذكي متخصص في الكهرباء. بتتكلم عامية مصرية. عندك بيانات حية من عداد ذكي بيراقب 5 احمال كهربية. حلل البيانات وجاوب بشكل عملي وواضح. استخدم ارقام حقيقية من البيانات دايما."

def ask_groq(user_question, energy_data):
    user_content = "دي بيانات العداد دلوقتي:\n" + json.dumps(energy_data, ensure_ascii=False, indent=2) + "\nسؤال المستخدم: " + user_question
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

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = "اهلا! انا بوت العداد الذكي بتاعك\n\nسالني اي حاجة عن الكهرباء، مثلا:\n- ليه النور غالي الشهر ده؟\n- مين اكتر حاجة بتاكل كهرباء؟\n- ايه معامل القدرة بتاع الموتور؟\n\nاو اكتب /status تشوف كل الاحمال دلوقتي"
    await update.message.reply_text(msg)

async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("جاري جلب البيانات من العداد...")
    data = fetch_blynk_data()
    msg = "حالة العداد دلوقتي:\n\n"
    total_w = 0
    for name, vals in data.items():
        if "خطأ" not in vals:
            w = vals["قدرة_W"]
            pf = vals["معامل_القدرة"]
            kwh = vals["طاقة_kWh"]
            icon = "🔴" if pf < 0.85 else "🟢"
            total_w += w
            msg += f"{icon} {name}: {w}W | PF:{pf} | {kwh}kWh\n"
    msg += f"\nالاجمالي: {round(total_w, 1)}W"
    await update.message.reply_text(msg)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_msg = update.message.text
    thinking = await update.message.reply_text("بجيب البيانات من العداد...")
    data = fetch_blynk_data()
    await thinking.edit_text("بحلل البيانات...")
    reply = ask_groq(user_msg, data)
    await thinking.edit_text(reply)

if __name__ == "__main__":
    print("Smart Energy Bot started!")
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("status", status_cmd))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.run_polling(drop_pending_updates=True)
