import os
import re
import json
import requests
from openai import OpenAI
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

BOT_TOKEN = os.getenv("BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
SERPER_API_KEY = os.getenv("SERPER_API_KEY")

GOOGLE_SCRIPT_URL = "https://script.google.com/macros/s/AKfycbxXXfTQAsWk7BkRvEWkdaLy2Dc45xsbsK7ADhWlNK8Jc06Ley4pME69uDdFaW1BAHm-eA/exec"

# memory cache
user_memory = {}

client = OpenAI(
    api_key=GROQ_API_KEY,
    base_url="https://api.groq.com/openai/v1"
)

# -------- CLEAN RESPONSE ----------
def clean_text(text):
    text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)
    text = text.replace("```", "")
    return text


# -------- WEB SEARCH FUNCTION ----------
def web_search(query):
    try:
        url = "https://google.serper.dev/search"
        headers = {
            "X-API-KEY": SERPER_API_KEY,
            "Content-Type": "application/json"
        }
        payload = json.dumps({"q": query})

        res = requests.post(url, headers=headers, data=payload)
        data = res.json()

        snippets = []
        for item in data.get("organic", [])[:5]:
            snippets.append(item["snippet"])

        return "\n".join(snippets)

    except:
        return ""


# -------- START ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user.first_name
    await update.message.reply_text(
f"""Hello {user},

I am AskSahilAI 🤖

You can talk to me like ChatGPT.
I also use internet search for latest information.

Ask anything:
• Studies
• Coding
• Career
• News
• Life advice
• General knowledge

Command:
/image prompt
"""
)


# -------- IMAGE ----------
async def image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    prompt = " ".join(context.args)

    if not prompt:
        await update.message.reply_text("Usage: /image robot teacher in classroom")
        return

    url = f"https://image.pollinations.ai/prompt/{prompt.replace(' ', '%20')}"
    await update.message.reply_photo(photo=url)


# -------- CHAT ----------
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user_text = update.message.text
    user_id = update.effective_user.id

    # ---------- MEMORY ----------
    if user_id not in user_memory:
        user_memory[user_id] = []

    user_memory[user_id].append({"role": "user", "content": user_text})
    user_memory[user_id] = user_memory[user_id][-15:]

    # ---------- SAVE USER MESSAGE ----------
    try:
        requests.post(GOOGLE_SCRIPT_URL, json={
            "userid": user_id,
            "role": "user",
            "message": user_text
        })
    except:
        pass

    # ---------- INTERNET SEARCH ----------
    search_results = web_search(user_text)

    try:
        messages = [
            {
                "role": "system",
                "content": f"""
You are AskSahilAI, an advanced conversational assistant like ChatGPT.

You remember conversation context and continue the same topic when user asks follow-up questions like:
why, how, explain more, continue, what about that.

If the question needs latest information, use this real-time web data:

{search_results}

You help with:
studies, coding, career guidance, personal advice, motivation, general knowledge, and news.

Be clear, intelligent and helpful.
Never give dangerous or illegal instructions.
"""
            }
        ] + user_memory[user_id]

        chat = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            temperature=0.7,
            messages=messages
        )

        reply = chat.choices[0].message.content
        reply = clean_text(reply)

        # save assistant reply in memory
        user_memory[user_id].append({"role": "assistant", "content": reply})

        # save assistant reply to sheet
        try:
            requests.post(GOOGLE_SCRIPT_URL, json={
                "userid": user_id,
                "role": "assistant",
                "message": reply
            })
        except:
            pass

    except Exception as e:
        print(e)
        reply = "Server busy. Try again in a few seconds."

    await update.message.reply_text(reply)


# -------- RUN ----------
app = ApplicationBuilder().token(BOT_TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("image", image))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

print("Bot running...")
app.run_polling()
