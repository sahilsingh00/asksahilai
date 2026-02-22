import os
import re
import json
import requests
from io import BytesIO
from openai import OpenAI
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

BOT_TOKEN = os.getenv("BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
SERPER_API_KEY = os.getenv("SERPER_API_KEY")

GOOGLE_SCRIPT_URL = "https://script.google.com/macros/s/AKfycbxXXfTQAsWk7BkRvEWkdaLy2Dc45xsbsK7ADhWlNK8Jc06Ley4pME69uDdFaW1BAHm-eA/exec"

# conversation memory
user_memory = {}

client = OpenAI(
    api_key=GROQ_API_KEY,
    base_url="https://api.groq.com/openai/v1"
)

# ---------- CLEAN TEXT ----------
def clean_text(text):
    text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)
    text = text.replace("```", "")
    return text


# ---------- WEB SEARCH ----------
def web_search(query):
    if not SERPER_API_KEY:
        return ""

    try:
        url = "https://google.serper.dev/search"
        headers = {
            "X-API-KEY": SERPER_API_KEY,
            "Content-Type": "application/json"
        }
        payload = json.dumps({"q": query})

        res = requests.post(url, headers=headers, data=payload, timeout=10)
        data = res.json()

        snippets = []
        for item in data.get("organic", [])[:5]:
            snippets.append(item.get("snippet", ""))

        return "\n".join(snippets)

    except Exception as e:
        print("Search error:", e)
        return ""


# ---------- START ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user.first_name

    await update.message.reply_text(f"""
Hello {user} 👋

I am AskSahilAI 🤖

You can chat with me like ChatGPT.
I also use internet search for latest information.

Ask anything:
• Studies
• Coding
• Career
• News
• Life advice

Commands:
/image prompt
""")


# ---------- IMAGE (FINAL WORKING) ----------
async def image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    prompt = " ".join(context.args)

    if not prompt:
        await update.message.reply_text("Usage: /image futuristic AI classroom")
        return

    try:
        img_url = f"https://image.pollinations.ai/prompt/{prompt.replace(' ', '%20')}"
        response = requests.get(img_url, timeout=60)

        if response.status_code != 200:
            await update.message.reply_text("Image server busy. Try again.")
            return

        image_bytes = BytesIO(response.content)
        image_bytes.name = "ai.png"

        await update.message.reply_photo(
            photo=image_bytes,
            caption=f"Generated image for: {prompt}"
        )

    except Exception as e:
        print("IMAGE ERROR:", e)
        await update.message.reply_text("Image generation failed. Try another prompt.")


# ---------- CHAT ----------
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user_text = update.message.text
    user_id = update.effective_user.id

    # memory create
    if user_id not in user_memory:
        user_memory[user_id] = []

    user_memory[user_id].append({"role": "user", "content": user_text})
    user_memory[user_id] = user_memory[user_id][-15:]

    # save user message to sheet
    try:
        requests.post(GOOGLE_SCRIPT_URL, json={
            "userid": user_id,
            "role": "user",
            "message": user_text
        }, timeout=5)
    except:
        pass

    # internet data
    search_results = web_search(user_text)

    try:
        messages = [
            {
                "role": "system",
                "content": f"""
You are AskSahilAI, a conversational assistant similar to ChatGPT.

Continue previous topic if user asks follow-up questions like:
why, explain more, continue, how, what about that.

Use this real-time web information if useful:
{search_results}

Help with study, coding, career, general knowledge and personal advice.
Be clear and helpful. Never give illegal or harmful guidance.
"""
            }
        ] + user_memory[user_id]

        chat = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            temperature=0.7,
            messages=messages
        )

        reply = clean_text(chat.choices[0].message.content)

        # save reply
        user_memory[user_id].append({"role": "assistant", "content": reply})

        try:
            requests.post(GOOGLE_SCRIPT_URL, json={
                "userid": user_id,
                "role": "assistant",
                "message": reply
            }, timeout=5)
        except:
            pass

    except Exception as e:
        print("AI error:", e)
        reply = "Server busy. Please try again."

    await update.message.reply_text(reply)


# ---------- RUN ----------
app = ApplicationBuilder().token(BOT_TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("image", image))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

print("Bot running...")
app.run_polling()
