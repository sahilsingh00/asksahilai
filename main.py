import os
import re
import requests
import tempfile
from io import BytesIO
from openai import OpenAI
from telegram import Update
from supabase import create_client
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

BOT_TOKEN = os.getenv("BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
SERPER_API_KEY = os.getenv("SERPER_API_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

#GOOGLE_SCRIPT_URL = "https://script.google.com/macros/s/AKfycbym2x02NNp6kGJmXrKwv6dky7p9Qld0__dtfg5FDAF1z60tcNyaDcJz0Pg1aPc1lXPlEQ/exec"

# -------- GROQ AI CLIENT --------
client = OpenAI(
    api_key=GROQ_API_KEY,
    base_url="https://api.groq.com/openai/v1"
)

# -------- USER MEMORY --------
user_memory = {}

# -------- TEXT FORMAT FIX --------
def clean_text(text):
    text = text.replace("```", "")
    text = text.replace("__", "*")
    text = text.replace("**", "*")
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()

# -------- GOOGLE SHEET LOGGER --------
def save_chat(userid, name, role, message):
    try:
        # 1. user find or create
        user = supabase.table("users").select("*").eq("platform_user_id", str(userid)).execute()

        if len(user.data) == 0:
            new_user = supabase.table("users").insert({
                "platform": "telegram",
                "platform_user_id": str(userid)
            }).execute()
            db_user_id = new_user.data[0]["id"]
        else:
            db_user_id = user.data[0]["id"]

        # 2. create conversation
        conv = supabase.table("conversations").insert({
            "user_id": db_user_id
        }).execute()

        conversation_id = conv.data[0]["id"]

        # 3. save message
        supabase.table("messages").insert({
            "conversation_id": conversation_id,
            "role": role,
            "content": message
        }).execute()

    except Exception as e:
        print("Supabase error:", e)

# -------- LIVE INTERNET SEARCH (REAL DATA) --------
def web_search(query):
    if not SERPER_API_KEY:
        return ""

    try:
        url = "https://google.serper.dev/search"
        headers = {"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"}
        res = requests.post(url, headers=headers, json={"q": query}, timeout=8)
        data = res.json()

        results = []
        for item in data.get("organic", [])[:5]:
            title = item.get("title", "")
            snippet = item.get("snippet", "")
            link = item.get("link", "")
            results.append(f"{title}\n{snippet}\nSource: {link}")

        return "\n\n".join(results)

    except:
        return ""

# -------- NEWS DETECTION --------
def is_news_query(text):
    words = ["news","latest","today","update","current affairs","recent","what happened"]
    return any(w in text.lower() for w in words)

# -------- IMAGE DETECTION --------
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

# -------- IMAGE GENERATOR --------
async def send_image(update, prompt):

    user = update.effective_user
    user_id = user.id
    name = user.first_name

    save_chat(user_id, name, "user_image", prompt)

    try:
        url = f"https://image.pollinations.ai/prompt/{prompt.replace(' ','%20')}?width=1024&height=1024&seed=7&enhance=true"
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
                {"role":"system","content":"Explain this topic clearly in short bullet points for a student."},
                {"role":"user","content":prompt}
            ]
        )

        text = clean_text(explanation.choices[0].message.content)
        await update.message.reply_text(text)

        save_chat(user_id, name, "assistant", text)
        return True

    except:
        return False

# -------- AI CORE --------
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

    # NEWS MODE
    if is_news_query(user_text):
        system_prompt = f"""
You must ONLY use the real search results below.
Do NOT invent news.

Real data:
{search_results}

Summarize latest news in bullet points with sources.
"""
    else:
        system_prompt = f"""
You are AskSahilAI created by Sahil Singh.

You act as:
• Personal Tutor
• Maths Solver (step by step)
• Coding Mentor
• Career Advisor

Rules:
- Continue conversation context
- Follow-up questions must continue same topic
- Give structured answers
"""

    try:
        messages = [{"role":"system","content":system_prompt}] + user_memory[user_id]

        chat = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            temperature=0.5,
            messages=messages
        )

        reply = clean_text(chat.choices[0].message.content)
        user_memory[user_id].append({"role":"assistant","content":reply})

    except:
        reply = "AI server busy. Try again."

    save_chat(user_id, name, "assistant", reply)
    await update.message.reply_text(reply, parse_mode="Markdown")

# -------- TEXT HANDLER --------
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    if is_image_request(text):
        if await send_image(update, text):
            return

    await process_ai(update, text)

# -------- VOICE HANDLER (WORKING) --------
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

        await update.message.reply_text(f"🎤 You said:\n{text}")
        await process_ai(update, text)

        os.remove(audio_path)

    except:
        await update.message.reply_text("Voice processing failed. Speak clearly and try again.")

# -------- START --------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Hello!\nI am AskSahilAI — Your Personal AI Assistant.\n\nYou can ask anything or send voice or image request."
    )

# -------- RUN --------
app = ApplicationBuilder().token(BOT_TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.VOICE, handle_voice))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

print("Bot running...")
app.run_polling()



