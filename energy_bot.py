import os
import json
import threading
import requests
import asyncio
from flask import Flask
from groq import Groq
from telegram import Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler,
    MessageHandler, filters, ContextTypes
)

# ============================================================
# Smart Energy Monitor - Telegram Bot
# ESP32 -> Blynk -> Groq AI (gpt-oss-120b) -> Telegram
# ============================================================

BLYNK_TOKEN    = os.environ.get("BLYNK_AUTH", "PQQtawp93VKXnQBxMMzEr7wF47fKXe5R")
GROQ_API_KEY   = os.environ.get("GROQ_API_KEY", "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")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "8406915756:AAGuyczfATvATa_HKGBSRlrl5MLqY5JyVxE")

BLYNK_BASE = "https://blynk.cloud/external/api/get"
LOADS = ["لمبة", "مروحة", "شفاط", "موتور", "تلاجة"]

groq_client = Groq(api_key=GROQ_API_KEY)

# Flask app for Railway health check
flask_app = Flask(__name__)

@flask_app.route('/')
def home():
    return 'Smart Energy Bot is running!'

def run_flask():
    port = int(os.environ.get('PORT', 8080))
    flask_app.run(host='0.0.0.0', port=port)

# ============================================================
# جيب بيانات من Blynk
# ============================================================
def fetch_blynk_data():
    data = {}
    for i, name in enumerate(LOADS):
        try:
            w   = float(requests.get(f"{BLYNK_BASE}?token={BLYNK_TOKEN}&v{i}",    timeout=5).text)
            pf  = float(requests.get(f"{BLYNK_BASE}?token={BLYNK_TOKEN}&v{i+5}",  timeout=5).text)
            kwh = float(requests.get(f"{BLYNK_BASE}?token={BLYNK_TOKEN}&v{i+10}", timeout=5).text)
            data[name] = {
                "قدرة_فعلية_W": round(w,   2),
                "معامل_القدرة": round(pf,  2),
                "طاقة_kWh"    : round(kwh, 4)
            }
        except Exception as e:
            data[name] = {"خطأ": str(e)}
    return data

# ============================================================
# اسأل Groq AI
# ============================================================
def ask_groq(user_question: str, energy_data: dict) -> str:
    response = groq_client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=[
            {
                "role": "system",
                "content": (
                    "انت مساعد ذكي متخصص في متابعة استهلاك الكهرباء في البيت.
"
                    "بتتكلم بالعامية المصرية بطريقة بسيطة ومفهومة.
"
                    "عندك بيانات حية من عداد ذكي بيراقب 5 احمال كهربية.
"
                    "لما حد يسالك عن سبب غلا الكهرباء او الاستهلاك، حلل البيانات وجاوبه بشكل عملي وواضح.
"
                    "استخدم ارقام حقيقية من البيانات في ردودك دايما."
                )
            },
            {
                "role": "user",
                "content": (
                    f"دي بيانات العداد الذكي دلوقتي:

"
                    f"{json.dumps(energy_data, ensure_ascii=False, indent=2)}

"
                    f"سؤال المستخدم: {user_question}"
                )
            }
        ],
        temperature=0.7,
        max_completion_tokens=1024,
        stream=False
    )
    return response.choices[0].message.content

# ============================================================
# Telegram Handlers
# ============================================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "اهلا! انا بوت العداد الذكي بتاعك

"
        "سالني اي حاجة عن الكهرباء، مثلا:

"
        "ليه النور غالي الشهر ده؟
"
        "مين اكتر حاجة بتاكل كهرباء؟
"
        "ايه معامل القدرة بتاع الموتور؟
"
        "اعمل ايه عشان اوفر في الفاتورة؟

"
        "او اكتب /status تشوف كل الاحمال دلوقتي"
    )

async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("جاري جلب البيانات من العداد...")
    data = fetch_blynk_data()
    msg = "حالة العداد دلوقتي:

"
    total_w = 0
    for name, vals in data.items():
        if "خطأ" not in vals:
            w   = vals["قدرة_فعلية_W"]
            pf  = vals["معامل_القدرة"]
            kwh = vals["طاقة_kWh"]
            icon = "🔴" if pf < 0.85 else "🟢"
            total_w += w
            msg += f"{icon} {name}
  {w}W | PF: {pf} | {kwh} kWh

"
    msg += f"الاجمالي: {round(total_w, 1)}W"
    await update.message.reply_text(msg)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_msg = update.message.text
    thinking = await update.message.reply_text("بجيب البيانات من العداد...")
    data = fetch_blynk_data()
    await thinking.edit_text("بحلل البيانات...")
    reply = ask_groq(user_msg, data)
    await thinking.edit_text(reply)

# ============================================================
# تشغيل البوت
# ============================================================
async def main():
    print("Smart Energy Bot started!")
    
    # Start Flask in a separate thread
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()

    # Build and start Telegram Bot
    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("status", status_cmd))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Run polling correctly for modern PTB
    async with application:
        await application.initialize()
        await application.start()
        await application.updater.start_polling()
        
        # Keep running until the app is stopped
        while True:
            await asyncio.sleep(1)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
