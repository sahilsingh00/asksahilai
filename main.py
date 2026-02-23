import os
import re
import requests
import tempfile
import ffmpeg
import tempfile
import subprocess
from io import BytesIO
from openai import OpenAI
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

BOT_TOKEN = os.getenv("BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
SERPER_API_KEY = os.getenv("SERPER_API_KEY")

GOOGLE_SCRIPT_URL = "https://script.google.com/macros/s/AKfycbym2x02NNp6kGJmXrKwv6dky7p9Qld0__dtfg5FDAF1z60tcNyaDcJz0Pg1aPc1lXPlEQ/exec"

# ---------------- AI CLIENT ----------------
client = OpenAI(
    api_key=GROQ_API_KEY,
    base_url="https://api.groq.com/openai/v1"
)

# ---------------- MEMORY ----------------
user_memory = {}

# ---------------- CLEAN TEXT ----------------
def clean_text(text):
    text = text.replace("```", "")
    text = text.replace("__", "*")
    text = text.replace("**", "*")
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()

# ---------------- SAVE CHAT ----------------
def save_chat(userid, name, role, message):
    try:
        payload = {
            "userid": str(userid),
            "name": str(name),
            "role": role,
            "message": message
        }
        requests.post(GOOGLE_SCRIPT_URL, json=payload, timeout=6)
    except Exception as e:
        print("Sheet Error:", e)

# ---------------- WEB SEARCH ----------------
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

# ---------------- SPEECH TO TEXT ----------------
def speech_to_text(file_path):
    try:
        with open(file_path, "rb") as audio:
            transcript = client.audio.transcriptions.create(
                model="whisper-large-v3",
                file=audio
            )
        return transcript.text
    except Exception as e:
        print("STT ERROR:", e)
        return None

# ---------------- IMAGE PROMPT ENGINE ----------------
def generate_image_prompt(user_text):
    try:
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            temperature=0.3,
            messages=[
                {"role":"system","content":"Convert into a professional image prompt. Diagram=educational labeled, career=infographic, object=realistic 4k photo. Only output prompt."},
                {"role":"user","content":user_text}
            ]
        )
        return response.choices[0].message.content.strip()
    except:
        return user_text

# ---------------- IMAGE REQUEST DETECTION ----------------
def is_image_request(text):
    t = text.lower()

    starters = ["draw ","create ","generate ","make ","show "]
    if any(t.startswith(s) for s in starters):
        return True

    image_words = ["image","picture","photo","diagram","chart","infographic","sketch","poster"]
    if any(w in t for w in image_words):
        return True

    if len(t.split()) <= 2:
        return True

    return False

# ---------------- IMAGE GENERATION ----------------
async def send_image(update, prompt):

    user_id = update.effective_user.id
    name = update.effective_user.first_name

    save_chat(user_id, name, "user_image", prompt)

    try:
        final_prompt = generate_image_prompt(prompt)

        url = f"https://image.pollinations.ai/prompt/{final_prompt.replace(' ','%20')}?width=1024&height=1024&seed=7"
        r = requests.get(url, timeout=60)

        if r.status_code != 200:
            return False

        img = BytesIO(r.content)
        img.name = "ai.png"

        await update.message.reply_photo(photo=img, caption="Generated Visual")

        explanation = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role":"system","content":"Explain the topic simply in short student-friendly points."},
                {"role":"user","content":prompt}
            ]
        )

        text = clean_text(explanation.choices[0].message.content)
        await update.message.reply_text(text)

        save_chat(user_id, name, "assistant", text)
        return True

    except Exception as e:
        print("IMAGE ERROR:", e)
        return False

# ---------------- START ----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.effective_user.first_name
    user_id = update.effective_user.id

    msg = f"""Hello {name} 👋

I am AskSahilAI — your AI learning & personal assistant.

You can:
• Solve maths
• Coding help
• Career guidance
• Latest news
• Generate images
• Voice doubts
"""

    save_chat(user_id, name, "assistant", msg)
    await update.message.reply_text(msg)

# ---------------- VOICE HANDLER ----------------
async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = update.effective_user
    user_id = user.id
    name = user.first_name

    try:
        # download telegram voice
        voice = await update.message.voice.get_file()

        with tempfile.NamedTemporaryFile(delete=False, suffix=".ogg") as temp_ogg:
            await voice.download_to_drive(temp_ogg.name)
            ogg_path = temp_ogg.name

        # convert to wav properly
        wav_path = ogg_path.replace(".ogg", ".wav")

        import subprocess
        subprocess.run([
            "ffmpeg",
            "-i", ogg_path,
            "-ar", "16000",
            "-ac", "1",
            wav_path
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        # speech recognition
        with open(wav_path, "rb") as audio:
            transcript = client.audio.transcriptions.create(
                model="whisper-large-v3",
                file=audio
            )

        text = transcript.text

        if not text:
            await update.message.reply_text("I could not understand the voice.")
            return

        # show recognized text
        await update.message.reply_text(f"🧠 I understood:\n{text}")

        # send to AI chat
        update.message.text = text
        await handle_message(update, context)

    except Exception as e:
        print("VOICE ERROR:", e)
        await update.message.reply_text("Voice processing failed. Please try again.")

# ---------------- CHAT ----------------
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user_text = update.message.text
    user_id = update.effective_user.id
    name = update.effective_user.first_name

    if is_image_request(user_text):
        if await send_image(update, user_text):
            return

    save_chat(user_id, name, "user", user_text)

    if user_id not in user_memory:
        user_memory[user_id] = []

    user_memory[user_id].append({"role":"user","content":user_text})
    user_memory[user_id] = user_memory[user_id][-12:]

    search_results = web_search(user_text)

    system_prompt = f"""
You are AskSahilAI created by Sahil Singh.

Roles:
- Personal tutor
- Maths solver (step-by-step)
- Coding mentor
- Career advisor
- News assistant

Use real-time internet info if useful:
{search_results}

Continue context. Be clear and professional.
"""

    try:
        messages = [{"role":"system","content":system_prompt}] + user_memory[user_id]

        chat = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            temperature=0.7,
            messages=messages
        )

        reply = clean_text(chat.choices[0].message.content)

        user_memory[user_id].append({"role":"assistant","content":reply})

    except Exception as e:
        print("AI ERROR:", e)
        reply = "Server busy. Try again."

    save_chat(user_id, name, "assistant", reply)
    await update.message.reply_text(reply)

# ---------------- RUN ----------------
app = ApplicationBuilder().token(BOT_TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.VOICE, handle_voice))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

print("Bot running...")
app.run_polling()

