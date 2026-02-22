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

# memory
user_memory = {}

client = OpenAI(
    api_key=GROQ_API_KEY,
    base_url="https://api.groq.com/openai/v1"
)

# ---------- TEXT CLEAN ----------
def clean_text(text):
    text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)
    text = text.replace("```", "")
    return text


# ---------- AI IMAGE PROMPT ENGINE ----------
def generate_image_prompt(user_text):
    try:
        prompt_ai = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            temperature=0.4,
            messages=[
                {
                    "role": "system",
                    "content": """
You convert user request into perfect image generation prompt.

Rules:
- Only output prompt
- No explanation
- If educational → labeled diagram or infographic
- If object → realistic
- If place → cinematic realistic scene
- Add: high detail, clean background, sharp focus, 4k, professional lighting
"""
                },
                {"role": "user", "content": user_text}
            ]
        )

        return prompt_ai.choices[0].message.content.strip()

    except:
        return user_text


# ---------- WEB SEARCH ----------
def web_search(query):
    if not SERPER_API_KEY:
        return ""
    try:
        url = "https://google.serper.dev/search"
        headers = {"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"}
        payload = json.dumps({"q": query})
        res = requests.post(url, headers=headers, data=payload, timeout=10)
        data = res.json()

        snippets = []
        for item in data.get("organic", [])[:5]:
            snippets.append(item.get("snippet", ""))

        return "\n".join(snippets)
    except:
        return ""


# ---------- START ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user.first_name
    await update.message.reply_text(f"""
Hello {user} 👋

I am AskSahilAI 🤖

You can chat with me or just type:

draw solar system
human heart diagram
career options after BMS infographic
latest AI news
""")


# ---------- IMAGE GENERATOR ----------
async def send_image(update, prompt):

    try:
        # AI makes best prompt
        final_prompt = generate_image_prompt(prompt)

        img_url = f"https://image.pollinations.ai/prompt/{final_prompt.replace(' ', '%20')}?width=1024&height=1024&seed=7"

        response = requests.get(img_url, timeout=60)
        if response.status_code != 200:
            return False

        image_bytes = BytesIO(response.content)
        image_bytes.name = "ai.png"

        # send image
        await update.message.reply_photo(photo=image_bytes, caption=f"🖼️ {prompt}")

        # ----- EXPLANATION -----
        explanation = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            temperature=0.5,
            messages=[
                {"role": "system", "content": "Explain the topic simply for a student in short clear points."},
                {"role": "user", "content": prompt}
            ]
        )

        text = clean_text(explanation.choices[0].message.content)
        await update.message.reply_text(text)

        return True

    except Exception as e:
        print("IMAGE ERROR:", e)
        return False


# ---------- /IMAGE ----------
async def image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    prompt = " ".join(context.args)
    if not prompt:
        await update.message.reply_text("Usage: /image solar system diagram")
        return
    await send_image(update, prompt)


# ---------- CHAT ----------
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user_text = update.message.text
    user_id = update.effective_user.id

    # AUTO IMAGE DETECTION
    image_triggers = [
        "draw","diagram","chart","infographic","sketch",
        "illustration","poster","picture","image","photo"
    ]

    if any(word in user_text.lower() for word in image_triggers):
        sent = await send_image(update, user_text)
        if sent:
            return

    # MEMORY
    if user_id not in user_memory:
        user_memory[user_id] = []

    user_memory[user_id].append({"role": "user", "content": user_text})
    user_memory[user_id] = user_memory[user_id][-15:]

    # LOG USER
    try:
        requests.post(GOOGLE_SCRIPT_URL, json={
            "userid": user_id,
            "role": "user",
            "message": user_text
        }, timeout=5)
    except:
        pass

    # WEB SEARCH
    search_results = web_search(user_text)

    try:
        messages = [{
            "role": "system",
            "content": f"""
You are AskSahilAI, a helpful conversational assistant like ChatGPT.

Continue topic if user asks why/how/explain more.

Use this internet info if useful:
{search_results}
"""
        }] + user_memory[user_id]

        chat = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            temperature=0.7,
            messages=messages
        )

        reply = clean_text(chat.choices[0].message.content)

        user_memory[user_id].append({"role": "assistant", "content": reply})

    except Exception as e:
        print("AI ERROR:", e)
        reply = "Server busy. Try again."

    await update.message.reply_text(reply)


# ---------- RUN ----------
app = ApplicationBuilder().token(BOT_TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("image", image))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

print("Bot running...")
app.run_polling()
