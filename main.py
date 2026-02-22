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

# Memory storage
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
            temperature=0.3,
            messages=[
                {
                    "role": "system",
                    "content": """
You are an image prompt engineer.

Convert the user request into a perfect image prompt.

Rules:
- Never explain anything
- Only output prompt
- Educational topics → clean labeled diagram
- Career topics → infographic
- Object → realistic
- Add: high detail, sharp focus, clean background, professional lighting, 4k
"""
                },
                {"role": "user", "content": user_text}
            ]
        )
        return prompt_ai.choices[0].message.content.strip()

    except:
        return user_text


# ---------- START MESSAGE ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user.first_name

    await update.message.reply_text(f"""
👋 Welcome {user}

I am *AskSahilAI* — your personal AI learning & productivity assistant.

I can help you with:
• Study concepts & explanations
• Coding & programming help
• Career guidance
• Visual diagrams & educational images
• Latest information

You can type your question naturally.

Try:
• solar system diagram
• explain python simply
• career options after BMS in India
• latest AI news
""", parse_mode="Markdown")


# ---------- IMAGE GENERATION ----------
async def send_image(update, prompt):
    try:
        final_prompt = generate_image_prompt(prompt)

        img_url = f"https://image.pollinations.ai/prompt/{final_prompt.replace(' ', '%20')}?width=1024&height=1024&seed=5"

        response = requests.get(img_url, timeout=60)
        if response.status_code != 200:
            return False

        image_bytes = BytesIO(response.content)
        image_bytes.name = "ai.png"

        # send image
        await update.message.reply_photo(
            photo=image_bytes,
            caption="Generated educational visual"
        )

        # explanation
        explanation = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            temperature=0.5,
            messages=[
                {
                    "role": "system",
                    "content": "Explain this topic clearly in short bullet points for a student."
                },
                {"role": "user", "content": prompt}
            ]
        )

        text = clean_text(explanation.choices[0].message.content)
        await update.message.reply_text(text)

        return True

    except Exception as e:
        print("IMAGE ERROR:", e)
        return False


# ---------- /IMAGE COMMAND ----------
async def image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    prompt = " ".join(context.args)
    if not prompt:
        await update.message.reply_text("Usage: /image human heart diagram")
        return
    await send_image(update, prompt)


# ---------- CHAT ----------
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user_text = update.message.text
    user_id = update.effective_user.id

    # IMAGE PRIORITY ROUTER
    image_triggers = [
        "draw","diagram","chart","infographic","sketch","illustration",
        "poster","picture","image","photo","visualize","structure","labeled"
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

    try:
        messages = [{
            "role": "system",
            "content": """
You are AskSahilAI, an advanced AI assistant created by Sahil Singh.

IMPORTANT RULES:
- Never create ASCII diagrams
- Never give drawing instructions
- Continue same topic when user says why/explain more
- Be clear, structured and professional
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
        reply = "Server busy. Please try again."

    await update.message.reply_text(reply)


# ---------- RUN ----------
app = ApplicationBuilder().token(BOT_TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("image", image))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

print("Bot running...")
app.run_polling()
