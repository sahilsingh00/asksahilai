import os
from openai import OpenAI
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

BOT_TOKEN = os.getenv("BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# Groq client
client = OpenAI(
    api_key=GROQ_API_KEY,
    base_url="https://api.groq.com/openai/v1"
)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Hello! Main AskSahilAI hoon 🤖\nKuch bhi pucho!"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text

    try:
        chat = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": user_text}]
        )
        reply = chat.choices[0].message.content
    except Exception as e:
        print(e)
        reply = "Thoda busy hoon, 5 sec baad try karo."

    await update.message.reply_text(reply)

app = ApplicationBuilder().token(BOT_TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

print("Bot running...")
app.run_polling()

