import os
import re
import requests
import tempfile
from io import BytesIO
from openai import OpenAI
from telegram import Update
from supabase import create_client
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# ---------------- ENV ----------------
BOT_TOKEN = os.getenv("BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
SERPER_API_KEY = os.getenv("SERPER_API_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# ---------------- GROQ CLIENT ----------------
client = OpenAI(
    api_key=GROQ_API_KEY,
    base_url="https://api.groq.com/openai/v1"
)

# ---------------- MEMORY ----------------
user_memory = {}
active_conversations = {}

# ---------------- CLEAN TEXT ----------------
def clean_text(text):
    text = text.replace("```", "")
    text = text.replace("__", "*")
    text = text.replace("**", "*")
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()

# ---------------- SAVE CHAT (SUPABASE) ----------------
def save_chat(userid, name, role, message):
    try:

        # ---- USER ----
        user = supabase.table("users").select("*").eq("platform_user_id", str(userid)).execute()

        if not user.data:
            new_user = supabase.table("users").insert({
                "platform": "telegram",
                "platform_user_id": str(userid)
            }).execute()
            db_user_id = new_user.data[0]["id"]
        else:
            db_user_id = user.data[0]["id"]

        # ---- CONVERSATION ----
        if userid not in active_conversations:
            conv = supabase.table("conversations").insert({
                "user_id": db_user_id
            }).execute()
            conversation_id = conv.data[0]["id"]
            active_conversations[userid] = conversation_id
        else:
            conversation_id = active_conversations[userid]

        # ---- SAVE MESSAGE ----
        supabase.table("messages").insert({
            "conversation_id": conversation_id,
            "role": role,
            "content": message
        }).execute()

    except Exception as e:
        print("Supabase error:", e)

# ---------------- LOAD MEMORY FROM DB ----------------
def load_memory(user_id):
    conv_id = active_conversations.get(user_id)
    if not conv_id:
        return []

    old_msgs = supabase.table("messages") \
        .select("*") \
        .eq("conversation_id", conv_id) \
        .order("id", desc=True) \
        .limit(6) \
        .execute()

    history = []
    for m in reversed(old_msgs.data):
        history.append({"role": m["role"], "content": m["content"]})
    return history

# ---------------- WEB SEARCH ----------------
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
            results.append(f"{item.get('title')}\n{item.get('snippet')}\nSource: {item.get('link')}")

        return "\n\n".join(results)
    except:
        return ""

# ---------------- IMAGE DETECTION ----------------
def is_image_request(text):
    t = text.lower()
    starters = ["draw ","create ","generate ","make ","show "]
    if any(t.startswith(s) for s in starters):
        return True
    image_words = ["image","picture","photo","diagram","chart","infographic","sketch","poster","wallpaper"]
    if any(w in t for w in image_words):
        return True
    return False

# ---------------- IMAGE ----------------
async def send_image(update, prompt):
    user = update.effective_user
    user_id = user.id

    save_chat(user_id, user.first_name, "user", prompt)

    try:
        url = f"https://image.pollinations.ai/prompt/{prompt.replace(' ','%20')}"
        r = requests.get(url, timeout=60)

        img = BytesIO(r.content)
        img.name = "ai.png"
        await update.message.reply_photo(photo=img, caption="🖼 Generated Image")

        explanation = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role":"system","content":"Explain this topic in short bullet points."},
                {"role":"user","content":prompt}
            ]
        )

        text = clean_text(explanation.choices[0].message.content)
        await update.message.reply_text(text)

        save_chat(user_id, user.first_name, "assistant", text)
        return True

    except:
        return False

# ---------------- AI ----------------
async def process_ai(update, user_text):

    user = update.effective_user
    user_id = user.id
    name = user.first_name

    save_chat(user_id, name, "user", user_text)

    # memory load after restart
    if user_id not in user_memory:
        user_memory[user_id] = load_memory(user_id)

    user_memory[user_id].append({"role":"user","content":user_text})
    user_memory[user_id] = user_memory[user_id][-12:]

    system_prompt = """
You are AskSahilAI created by Sahil Singh.
You act as a tutor, coding mentor and career guide.
Give clear structured answers.
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
    await update.message.reply_text(reply)

# ---------------- HANDLERS ----------------
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if is_image_request(text):
        if await send_image(update, text):
            return
    await process_ai(update, text)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Hello! I am AskSahilAI.\nSend message or voice."
    )

# ---------------- RUN ----------------
app = ApplicationBuilder().token(BOT_TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

print("Bot running...")
app.run_polling()
