import os
import re
import requests
import tempfile
from io import BytesIO
from openai import OpenAI
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

BOT_TOKEN = os.getenv("BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
SERPER_API_KEY = os.getenv("SERPER_API_KEY")

GOOGLE_SCRIPT_URL = "https://script.google.com/macros/s/AKfycbym2x02NNp6kGJmXrKwv6dky7p9Qld0__dtfg5FDAF1z60tcNyaDcJz0Pg1aPc1lXPlEQ/exec"

# ---------- GROQ CLIENT ----------
client = OpenAI(
    api_key=GROQ_API_KEY,
    base_url="https://api.groq.com/openai/v1"
)

# ---------- MEMORY ----------
user_memory = {}

# ---------- CLEAN ----------
def clean_text(text):
    text = text.replace("```", "")
    text = text.replace("__", "*")
    text = text.replace("**", "*")
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()

# ---------- SAVE CHAT ----------
def save_chat(userid, name, role, message):
    try:
        requests.post(GOOGLE_SCRIPT_URL, json={
            "userid": str(userid),
            "name": str(name),
            "role": role,
            "message": message
        }, timeout=5)
    except:
        pass

# ---------- WEB SEARCH ----------
def web_search(query):
    if not SERPER_API_KEY:
        return ""

    try:
        url = "https://google.serper.dev/search"
        headers = {"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"}
        response = requests.post(url, headers=headers, json={"q": query}, timeout=8)
        data = response.json()

        snippets = []
        for item in data.get("organic", [])[:5]:
            snippets.append(item.get("snippet", ""))

        return "\n".join(snippets)

    except:
        return ""

# ---------- IMAGE DETECTION ----------
def is_image_request(text):
    t = text.lower()

    starters = ["draw ","create ","generate ","make ","show "]
    if any(t.startswith(s) for s in starters):
        return True

    image_words = ["image","picture","photo","diagram","chart","infographic","sketch","poster","wallpaper"]
    if any(w in t for w in image_words):
        return True

    if len(t.split()) <= 2:
        return True

    return False

# ---------- IMAGE ----------
async def send_image(update, prompt):
    try:
        url = f"https://image.pollinations.ai/prompt/{prompt.replace(' ','%20')}?width=1024&height=1024"
        r = requests.get(url, timeout=60)

        if r.status_code != 200:
            return False

        img = BytesIO(r.content)
        img.name = "ai.png"

        await update.message.reply_photo(photo=img, caption="🖼 Generated Image")
        return True
    except:
        return False

# ---------- AI BRAIN ----------
async def process_ai(update, user_text):

    user = update.effective_user
    user_id = user.id
    name = user.first_name

    save_chat(user_id, name, "user", user_text)

    if user_id not in user_memory:
        user_memory[user_id] = []

    user_memory[user_id].append({"role":"user","content":user_text})
    user_memory[user_id] = user_memory[user_id][-12:]

    search_results = web_search(user_text)

    system_prompt = f"""
You are AskSahilAI created by Sahil Singh.

Roles:
• Personal tutor
• Maths solver (step by step)
• Coding mentor
• Career advisor
• News assistant

Use real-time info:
{search_results}

Rules:
Continue conversation context.
Answer professionally.
Use bullet points.
"""

    try:
        messages = [{"role":"system","content":system_prompt}] + user_memory[user_id]

        chat = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            temperature=0.6,
            messages=messages
        )

        reply = clean_text(chat.choices[0].message.content)
        user_memory[user_id].append({"role":"assistant","content":reply})

    except Exception as e:
        print("AI ERROR:", e)
        reply = "AI server busy. Please try again."

    save_chat(user_id, name, "assistant", reply)
    await update.message.reply_text(reply, parse_mode="Markdown")

# ---------- TEXT ----------
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    if is_image_request(text):
        if await send_image(update, text):
            return

    await process_ai(update, text)

# ---------- VOICE (FINAL WORKING) ----------
async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):

    try:
        await update.message.reply_text("🎧 Listening...")

        voice = await update.message.voice.get_file()

        with tempfile.NamedTemporaryFile(delete=False, suffix=".ogg") as temp_audio:
            await voice.download_to_drive(temp_audio.name)
            audio_path = temp_audio.name

        # GROQ Whisper
        with open(audio_path, "rb") as audio_file:
            transcript = client.audio.transcriptions.create(
                model="whisper-large-v3",
                file=audio_file
            )

        text = transcript.text.strip()

        if not text:
            await update.message.reply_text("I couldn't understand the voice.")
            return

        await update.message.reply_text(f"🎤 You said:\n{text}")

        await process_ai(update, text)

        os.remove(audio_path)

    except Exception as e:
        print("VOICE ERROR:", e)
        await update.message.reply_text("Voice processing failed. Please try again.")

# ---------- START ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Hello 👋\n\nI am AskSahilAI — your AI assistant.\nSend text, image prompt or voice message."
    )

# ---------- RUN ----------
app = ApplicationBuilder().token(BOT_TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.VOICE, handle_voice))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

print("Bot running...")
app.run_polling()
