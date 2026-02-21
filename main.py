import os
import re
from openai import OpenAI
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

BOT_TOKEN = os.getenv("BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# Groq AI client
client = OpenAI(
    api_key=GROQ_API_KEY,
    base_url="https://api.groq.com/openai/v1"
)

# ---------- FORMAT FIX (removes **bold** issue) ----------
def clean_text(text):
    text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)  # remove markdown bold
    text = text.replace("```", "")  # remove code blocks
    return text


# ---------- START INTRO ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user.first_name

    intro = f"""
👋 Hello {user}!

Main *Sahil Singh* hoon — AskSahilAI bot ka creator 😊

🤖 Ye ek AI Student Assistant hai jo specially students ki help ke liye banaya gaya hai.

Main help kar sakta hoon:
📚 Study doubts
💻 Coding & Programming
🎓 Final year projects
🧠 Career guidance

Commands use karo:
/help  - sab features
/notes - study material
/projectideas - project ideas
/roadmap - coding path

Aap mujhse normal chat bhi kar sakte ho 🙂
"""

    await update.message.reply_text(intro, parse_mode="Markdown")


# ---------- HELP COMMAND ----------
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = """
🤖 AskSahilAI Commands

/notes - Important CS/IT subjects study material
/projectideas - Final year project ideas
/roadmap - Coding learning roadmap
/help - Commands list

Ya phir directly question pucho 🙂
"""
    await update.message.reply_text(text)


# ---------- NOTES ----------
async def notes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = """
📚 Important Subjects

DBMS:
https://www.geeksforgeeks.org/dbms/

Operating System:
https://www.geeksforgeeks.org/operating-systems/

Computer Networks:
https://www.geeksforgeeks.org/computer-network-tutorials/

Data Structures:
https://www.geeksforgeeks.org/data-structures/

Tip: Roz thoda padhoge to semester easy ho jayega 💪
"""
    await update.message.reply_text(text)


# ---------- PROJECT IDEAS ----------
async def projectideas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = """
💡 Final Year Project Ideas

1. AI Resume Analyzer
2. Face Recognition Attendance System
3. College Q&A Chatbot
4. Fake News Detection System
5. Smart Timetable Generator
6. Online Code Compiler

Detail chahiye to pucho 🙂
"""
    await update.message.reply_text(text)


# ---------- ROADMAP ----------
async def roadmap(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = """
🧠 Coding Roadmap (Beginner to Job)

STEP 1 → Python Basics (2 weeks)
STEP 2 → Data Structures
STEP 3 → Git & GitHub
STEP 4 → Web Development (HTML CSS JS)
STEP 5 → Projects banana start
STEP 6 → Internship apply

Daily 2-3 hours = 6 months me job ready 🚀
"""
    await update.message.reply_text(text)


# ---------- AI CHAT ----------
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text

    try:
        chat = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are AskSahilAI created by Sahil Singh. "
                        "You are a friendly Indian student assistant. "
                        "Always reply in simple Hinglish (Hindi + English). "
                        "Explain like a teacher but friendly. "
                        "Help in study, coding, projects, and career guidance."
                    ),
                },
                {"role": "user", "content": user_text},
            ],
        )

        reply = chat.choices[0].message.content
        reply = clean_text(reply)

    except Exception as e:
        print(e)
        reply = "⚠️ Server thoda busy hai, 10 sec baad try karo."

    await update.message.reply_text(reply)


# ---------- BOT RUN ----------
app = ApplicationBuilder().token(BOT_TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("help", help_command))
app.add_handler(CommandHandler("notes", notes))
app.add_handler(CommandHandler("projectideas", projectideas))
app.add_handler(CommandHandler("roadmap", roadmap))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

print("Bot running...")
app.run_polling()
