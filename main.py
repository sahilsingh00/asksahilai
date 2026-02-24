import os
import re
import tempfile
from io import BytesIO
from openai import OpenAI
from telegram import Update
from supabase import create_client
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# -------- ENV --------
BOT_TOKEN = os.getenv("BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# -------- GROQ --------
client = OpenAI(
    api_key=GROQ_API_KEY,
    base_url="https://api.groq.com/openai/v1"
)

# -------- CLEAN TEXT --------
def clean_text(text):
    text = text.replace("```", "")
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()

# -------- GET USER + CONVERSATION --------
def get_conversation_id(user_id):

    user = supabase.table("users").select("*").eq("platform_user_id", str(user_id)).execute()

    if not user.data:
        new_user = supabase.table("users").insert({
            "platform": "telegram",
            "platform_user_id": str(user_id)
        }).execute()
        db_user_id = new_user.data[0]["id"]
    else:
        db_user_id = user.data[0]["id"]

    conv = supabase.table("conversations") \
        .select("*") \
        .eq("user_id", db_user_id) \
        .order("created_at", desc=True) \
        .limit(1) \
        .execute()

    if conv.data:
        return conv.data[0]["id"]

    new_conv = supabase.table("conversations").insert({
        "user_id": db_user_id
    }).execute()

    return new_conv.data[0]["id"]

# -------- SAVE MESSAGE --------
def save_message(conversation_id, role, content):
    supabase.table("messages").insert({
        "conversation_id": conversation_id,
        "role": role,
        "content": content
    }).execute()

# -------- LOAD MEMORY --------
def load_history(conversation_id):
    msgs = supabase.table("messages") \
        .select("*") \
        .eq("conversation_id", conversation_id) \
        .order("id", desc=True) \
        .limit(8) \
        .execute()

    history = []
    for m in reversed(msgs.data):
        history.append({"role": m["role"], "content": m["content"]})
    return history

# -------- AI --------
async def process_ai(chat_id, user_text, context):

    user_id = chat_id

    conversation_id = get_conversation_id(user_id)

    # save user
    save_message(conversation_id, "user", user_text)

    history = load_history(conversation_id)[-5:]

    system_prompt = """
You are AskSahilAI created by Sahil Singh.
You are a tutor and coding mentor.
Explain clearly in structured points.
Use simple language.
"""

    messages = [{"role":"system","content":system_prompt}] + history

    try:
        chat = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            temperature=0.5,
            messages=messages
        )
        reply = clean_text(chat.choices[0].message.content)

    except Exception as e:
        reply = "AI server busy. Try again."

    # save assistant
    save_message(conversation_id, "assistant", reply)

    await context.bot.send_message(chat_id=chat_id, text=reply, parse_mode="Markdown")

# -------- VOICE HANDLER --------
async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):

    try:
        await update.message.reply_text("🎧 Listening...")

        voice = await update.message.voice.get_file()

        with tempfile.NamedTemporaryFile(delete=False, suffix=".ogg") as temp_audio:
            await voice.download_to_drive(temp_audio.name)
            audio_path = temp_audio.name

        # speech to text
        with open(audio_path, "rb") as audio_file:
            transcript = client.audio.transcriptions.create(
                model="whisper-large-v3",
                file=audio_file
            )

        user_text = transcript.text.strip()
        os.remove(audio_path)

        # show transcript
        await update.message.reply_text(f"🗣 You said: {user_text}")

        # VERY IMPORTANT — background AI call
        await update.message.reply_text("🤖 Thinking...")

        chat_id = update.effective_chat.id
        context.application.create_task(process_ai(chat_id, user_text, context))

    except Exception as e:
        await update.message.reply_text("❌ Voice samajh nahi aaya. Thoda clear bolkar try karo.")

# -------- TEXT HANDLER --------
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    await update.message.reply_text("🤔 Thinking...")
    chat_id = update.effective_chat.id
    context.application.create_task(process_ai(chat_id, text, context))

# -------- START --------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Hello! I am AskSahilAI.\nText ya voice dono bhej sakte ho."
    )

# -------- RUN --------
app = ApplicationBuilder().token(BOT_TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.VOICE, handle_voice))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

print("Bot running...")
app.run_polling()


