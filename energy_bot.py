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
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
BLYNK_BASE = "https://blynk.cloud/external/api/get"
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"

LOADS_AR = ["لمبة", "مروحة", "شفاط", "موتور", "تلاجة"]

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

SYSTEM_PROMPT = """انت "عدادي" - المساعد الذكي للبيت المصري.
بتتكلم عامية مصرية "صايعة" وفاهمة، كأنك واحد صاحبه قاعد معاه.
مهمتك تحلل بيانات عداد الكهرباء وتقول للناس الحقيقة بذكاء.

القواعد:
1. اتكلم مصري طبيعي جداً (مثلاً: "يا سيدي النور غالي عشان التلاجة دي واكلة حقنا"، "فكك من الموتور ده دلوقتي").
2. لما تحسب التكلفة: سعر الكيلو وات ساعة (kWh) في مصر حالياً حوالي 1.35 جنيه (شريحة متوسطة). احسب اليومي والشهري.
3. اشرح الأرقام: يعني إيه PF (معامل القدرة)؟ لو أقل من 0.85 قوله إن الجهاز ده "بيهدر كهرباء" ومحتاج صيانة أو مكثف.
4. قارن الأحمال: قول مين أكتر واحد "مفترى" في سحب الكهرباء.
5. ادِ نصايح عملية: "اقفل الشفاط ده وانت مش محتاجه"، "الموتور شغال كتير ليه؟".

بيانات العداد اللي معاك دلوقتي هبعتهالك في كل رسالة."""

def ask_gemini(user_question, energy_data):
    if not GEMINI_API_KEY:
        return "يا صاحبي مفيش مفتاح Gemini API.. شغلني الأول!"
    
    data_text = json.dumps(energy_data, ensure_ascii=False, indent=2)
    prompt = f"{SYSTEM_PROMPT}

بيانات العداد الحالية:
{data_text}

سؤال المستخدم: {user_question}"
    
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
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
        r = requests.post(url, json=payload, timeout=30)
        if r.status_code == 200:
            return r.json()['candidates'][0]['content']['parts'][0]['text']
        else:
            return f"حصلت مشكلة في Gemini (كود {r.status_code}): {r.text[:200]}"
    except Exception as e:
        return f"يا ساتر! حصل خطأ وأنا بكلم جوجل: {str(e)}"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "يا أهلاً بيك! أنا 'عدادي' 💡
"
        "أنا المساعد المصري بتاعك عشان نفهم الكهرباء دي بتروح فين.

"
        "اسألني أي حاجة:
"
        "• مين أكتر واحد بياكل كهرباء دلوقتي؟
"
        "• الكهرباء هتكلفني كام الشهر ده؟
"
        "• في حاجة خطر في العداد؟

"
        "التحكم:
"
        "/status - شوف الحالة بالتفصيل
"
        "/tips - نصايح توفير الكهرباء
"
    )
    await update.message.reply_text(msg)

async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("بشوفلك العداد.. ثانية واحدة 🧐")
    data = fetch_blynk_data()
    msg = "⚡ حالة العداد دلوقتي:

"
    total_w = 0
    for name, vals in data.items():
        if "error" not in vals:
            w = vals["W"]; pf = vals["PF"]; kwh = vals["kWh"]
            total_w += w
            icon = "🔴" if pf < 0.85 else "🟢"
            msg += f"{icon} {name}: {w}W | PF:{pf} | {kwh}kWh
"
        else:
            msg += f"⚠️ {name}: قراءة غلط
"
    msg += f"
🔥 السحب الإجمالي: {round(total_w,1)}W"
    await update.message.reply_text(msg)

async def tips_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    thinking = await update.message.reply_text("بحلل الأحمال وهديك الزتونة..")
    data = fetch_blynk_data()
    reply = ask_gemini("اديني نصايح توفير بناء على البيانات دي وقولي مين أكتر حمل بيسحب", data)
    await thinking.edit_text(reply)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_msg = update.message.text
    thinking = await update.message.reply_text("ثواني أشوفلك الدنيا..")
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
