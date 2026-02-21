import os
import re
import requests
from openai import OpenAI
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

BOT_TOKEN = os.getenv("BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# Google Sheet Logging URL
GOOGLE_SCRIPT_URL = "https://script.google.com/macros/s/AKfycbzdXrvhSPFdHberD2ruE4yxiTRfYwo2oKxRNPZH543H53nF1GjPeJNtqJimFMXivDbiXw/exec"

# Groq client
client = OpenAI(
    api_key=GROQ_API_KEY,
    base_url="https://api.groq.com/openai/v1"
)

# -------- CLEAN RESPONSE ----------
def clean_text(text):
    text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)
    text = text.replace("```", "")
    return text


# -------- START INTRO ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user.first_name

    intro = f"""
Hello {user},

I am Sahil Singh, creator of AskSahilAI.

This assistant can help you with:
• Study doubts
• Coding & programming
• Career guidance
• Project ideas
• Personal guidance & motivation

You can chat normally with me or ask any question.

Use:
/help – see features
/notes – study material
/projectideas – project ideas
/roadmap – learning path
"""

    await update.message.reply_text(intro)


# -------- HELP ----------
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = """
Available Commands:

/notes - Important CS/IT study resources
/projectideas - Final year project ideas
/roadmap - Programming learning path

You can also ask:
• Study questions
• Career confusion
• Motivation or stress help
• Normal conversation
"""
    await update.message.reply_text(text)


# -------- NOTES ----------
async def notes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = """
Study Resources:

DBMS:
https://www.geeksforgeeks.org/dbms/

Operating System:
https://www.geeksforgeeks.org/operating-systems/

Computer Networks:
https://www.geeksforgeeks.org/computer-network-tutorials/

Data Structures:
https://www.geeksforgeeks.org/data-structures/
"""
    await update.message.reply_text(text)


# -------- PROJECT IDEAS ----------
async def projectideas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = """
Final Year Project Ideas:

1. AI Resume Analyzer
2. Face Recognition Attendance System
3. College Q&A Chatbot
4. Fake News Detection System
5. Smart Timetable Generator
6. Online Code Compiler
"""
    await update.message.reply_text(text)


# -------- ROADMAP ----------
async def roadmap(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = """
Programming Roadmap:

Step 1: Learn Python Basics
Step 2: Data Structures
Step 3: Git & GitHub
Step 4: Web Development
Step 5: Build Projects
Step 6: Apply for Internship
"""
    await update.message.reply_text(text)


# -------- AI CHAT ----------
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    user = update.effective_user.first_name
    userid = update.effective_user.id

    # ---- LOG USER DATA TO GOOGLE SHEET ----
    try:
        data = {
            "userid": userid,
            "name": user,
            "message": user_text
        }
        requests.post(GOOGLE_SCRIPT_URL, json=data)
    except:
        pass

    try:
        chat = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            temperature=0.5,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are AskSahilAI created by Sahil Singh, a student life assistant AI. "

                        "You can do both normal conversation and serious help."

                        "If user greets, chat normally and politely."

                        "If user asks study, coding, or career questions, explain like a teacher in clear simple English."

                        "If user shares personal problems (stress, sadness, family issues, confusion), respond supportively like a mentor. "
                        "Give practical suggestions, motivation, and step-by-step advice."

                        "Never flirt, never insult, never use inappropriate language."

                        "If user shows severe emotional distress, encourage them to talk to a trusted person like a friend, parent, teacher, or counselor."

                        "Keep answers clear, structured, and easy to understand."
                    ),
                },
                {"role": "user", "content": user_text},
            ],
        )

        reply = chat.choices[0].message.content
        reply = clean_text(reply)

    except Exception as e:
        print(e)
        reply = "The server is temporarily busy. Please try again in a few seconds."

    await update.message.reply_text(reply)


# -------- RUN BOT ----------
app = ApplicationBuilder().token(BOT_TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("help", help_command))
app.add_handler(CommandHandler("notes", notes))
app.add_handler(CommandHandler("projectideas", projectideas))
app.add_handler(CommandHandler("roadmap", roadmap))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

print("Bot running...")
app.run_polling()
