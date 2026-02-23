import os
import re
import requests
import tempfile
import subprocess
from io import BytesIO
from openai import OpenAI
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from faster_whisper import WhisperModel

BOT_TOKEN = os.getenv("BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
SERPER_API_KEY = os.getenv("SERPER_API_KEY")

GOOGLE_SCRIPT_URL = "https://script.google.com/macros/s/AKfycbym2x02NNp6kGJmXrKwv6dky7p9Qld0__dtfg5FDAF1z60tcNyaDcJz0Pg1aPc1lXPlEQ/exec"

# ---------- AI CLIENT ----------
client = OpenAI(
    api_key=GROQ_API_KEY,
    base_url="https://api.groq.com/openai/v1"
)

# ---------- MEMORY ----------
user_memory = {}

# ---------- LAZY VOICE MODEL ----------
whisper_model = None

# ---------- CLEAN TEXT ----------
def clean_text(text):
    text = text.replace("```", "")
    text = text.replace("__", "*")
    text = text.replace("**", "*")
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()

# ---------- SAVE CHAT ----------
def save_chat(userid, name, role, message):
    try:
        payload = {
            "userid": str(userid),
            "name": str(name),
            "role": role,
            "message": message
        }
        requests.post(GOOGLE_SCRIPT_URL, json=payload, timeout=5)
    except:
        pass

# ---------- LIVE INTERNET SEARCH ----------
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

# ---------- IMAGE REQUEST DETECTION ----------
def is_image_request(text):
    t = text.lower()

    starters = ["draw ", "create ", "generate ", "make ", "show "]
    if any(t.startswith(s) for s in starters):
        return True

    image_words = ["image","picture","photo","diagram","chart","infographic","sketch","poster","wallpaper"]
    if any(w in t for w in image_words):
        return True

    # single word → auto visual
    if len(t.split()) <= 2:
        return True

    return False

# ---------- IMAGE GENERATION ----------
async def send_image(update, prompt):

    user = update.effective_user
    user_id = user.id
    name = user.first_name

    save_chat(user_id, name, "user_image", prompt)

    try:
        url = f"https://image.pollinations.ai/prompt/{prompt.replace(' ','%20')}?width=1024&height=1024&seed=7"
        r = requests.get(url, timeout=60)

        if r.status_code != 200:
            return False

        img = BytesIO(r.content)
        img.name = "ai.png"

        await update.message.reply_photo(photo=img, caption="🖼 Generated Image")

        # explanation
        explanation = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role":"system","content":"Explain this topic in simple student friendly bullet points."},
                {"role":"user","content":prompt}
            ]
        )

        text = clean_text(explanation.choices[0].message.content)
        await update.message.reply_text(text)

        save_chat(user_id, name, "assistant", text)
        return True

    except:
        return False

# ---------- CORE AI ----------
async def process_ai(update, user_text):

    user = update.effective_user
    user_id = user.id
    name = user.first_name

    save_chat(user_id, name, "user", user_text)

    if user_id not in user_memory:
        user_memory[user_id] = []

    user_memory[user_id].append({"role":"user","content":user_text})
    user_memory[user_id] = user_memory[user_id][-12:]

    # internet knowledge
    search_results = web_search(user_text)

    system_prompt = f"""
You are AskSahilAI created by Sahil Singh.

You act as:
• Personal Tutor
• Maths solver (step-by-step)
• Coding mentor
• Career advisor
• News assistant

Use real-time information if needed:
{search_results}

Rules:
- Continue conversation context
- Follow-up questions should continue same topic
- Solve maths step-by-step
- Use bullet points when explaining
- Be clear, professional and accurate
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

# ---------- START ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.effective_user.first_name
    msg = f"""Hello {name} 👋

I am AskSahilAI — your intelligent assistant.

You can:
• Ask study questions
• Solve maths
• Coding help
• Career guidance
• Latest news
• Generate images
• Send voice doubts
"""
    await update.message.reply_text(msg)

# ---------- TEXT ----------
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    if is_image_request(text):
        if await send_image(update, text):
            return

    await process_ai(update, text)

# ---------- VOICE (FINAL FIXED) ----------
async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):

    global whisper_model

    try:
        await update.message.reply_text("🎧 Listening...")

        voice = await update.message.voice.get_file()

        with tempfile.NamedTemporaryFile(delete=False, suffix=".ogg") as temp_ogg:
            await voice.download_to_drive(temp_ogg.name)
            ogg_path = temp_ogg.name

        wav_path = ogg_path + ".wav"

        subprocess.run(
            ["ffmpeg","-y","-i",ogg_path,"-ac","1","-ar","16000",wav_path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )

        if whisper_model is None:
            await update.message.reply_text("🧠 Loading voice AI (first time)...")
            whisper_model = WhisperModel("tiny", compute_type="int8")

        segments, _ = whisper_model.transcribe(wav_path, beam_size=1)

        text = ""
        for seg in segments:
            text += seg.text + " "

        text = text.strip()

        if len(text) < 2:
            await update.message.reply_text("I couldn't understand the voice.")
            return

        await update.message.reply_text(f"🎤 You said:\n{text}")

        await process_ai(update, text)

        os.remove(ogg_path)
        os.remove(wav_path)

    except Exception as e:
        print("VOICE ERROR:", e)
        await update.message.reply_text("Voice processing failed. Send shorter voice.")

# ---------- RUN ----------
app = (
    ApplicationBuilder()
    .token(BOT_TOKEN)
    .concurrent_updates(True)
    .build()
)

app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.VOICE, handle_voice))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

print("Bot running...")
app.run_polling()
