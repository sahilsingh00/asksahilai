import os
import re
import requests
from io import BytesIO
from openai import OpenAI
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

BOT_TOKEN = os.getenv("BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
SERPER_API_KEY = os.getenv("SERPER_API_KEY")

GOOGLE_SCRIPT_URL = "https://script.google.com/macros/s/AKfycbxweVv2IzlVR_9ZWxpc922hmdl4eXPcv9dRcX3IS20eTG2jc5UXKwmUANxK99UioeTSUw/exec"

# ---------- AI CLIENT ----------
client = OpenAI(
    api_key=GROQ_API_KEY,
    base_url="https://api.groq.com/openai/v1"
)

# ---------- MEMORY ----------
user_memory = {}

# ---------- CLEAN TEXT ----------
def clean_text(text):
    text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)
    text = text.replace("```", "")
    return text

# ---------- SAVE CHAT ----------
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

# ---------- WEB SEARCH ----------
def web_search(query):
    if not SERPER_API_KEY:
        return ""

    try:
        url = "https://google.serper.dev/search"
        headers = {"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"}
        response = requests.post(url, headers=headers, json={"q": query}, timeout=10)
        data = response.json()

        snippets = []
        for item in data.get("organic", [])[:5]:
            snippets.append(item.get("snippet", ""))

        return "\n".join(snippets)

    except:
        return ""

# ---------- IMAGE PROMPT ----------
def generate_image_prompt(user_text):
    try:
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            temperature=0.3,
            messages=[
                {"role":"system","content":"Convert request into a professional image prompt. Educational = labeled diagram. Career = infographic. Object = realistic photo. Only output prompt."},
                {"role":"user","content":user_text}
            ]
        )
        return response.choices[0].message.content.strip()
    except:
        return user_text

# ---------- IMAGE DETECTION ----------
def is_image_request(text):
    t = text.lower()
    starters = ["draw ","create ","generate ","make ","show "]
    if any(t.startswith(s) for s in starters):
        return True

    image_words = ["image","picture","photo","diagram","chart","infographic","sketch"]
    if any(w in t for w in image_words):
        return True

    if len(t.split()) <= 2:  # single word auto visual
        return True

    return False

# ---------- IMAGE GENERATION ----------
async def send_image(update, prompt):

    user_id = update.effective_user.id
    user_name = update.effective_user.first_name

    # log user prompt also
    save_chat(user_id, user_name, "user", prompt)

    try:
        final_prompt = generate_image_prompt(prompt)

        url = f"https://image.pollinations.ai/prompt/{final_prompt.replace(' ','%20')}?width=1024&height=1024&seed=7"
        r = requests.get(url, timeout=60)

        if r.status_code != 200:
            return False

        img = BytesIO(r.content)
        img.name = "ai.png"

        await update.message.reply_photo(photo=img, caption="Generated Visual")

        # explanation
        explanation = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role":"system","content":"Explain the topic in clear short student-friendly points."},
                {"role":"user","content":prompt}
            ]
        )

        text = clean_text(explanation.choices[0].message.content)
        await update.message.reply_text(text)

        # log explanation
        save_chat(user_id, user_name, "assistant", text)

        return True

    except Exception as e:
        print("Image Error:", e)
        return False

# ---------- START ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.effective_user.first_name
    user_id = update.effective_user.id

    msg = f"""Hello {name} 👋

I am AskSahilAI — your personal AI learning assistant.

You can:
• Study doubts
• Maths solving
• Coding help
• Career guidance
• Latest news
• Generate images & diagrams

Try:
cat
solve 2x+5=15
latest AI news
python roadmap chart
"""

    save_chat(user_id, name, "user", "/start")
    save_chat(user_id, name, "assistant", msg)

    await update.message.reply_text(msg)

# ---------- CHAT ----------
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user_text = update.message.text
    user_id = update.effective_user.id
    user_name = update.effective_user.first_name

    # IMAGE MODE
    if is_image_request(user_text):
        if await send_image(update, user_text):
            return

    # LOG USER MESSAGE
    save_chat(user_id, user_name, "user", user_text)

    # MEMORY
    if user_id not in user_memory:
        user_memory[user_id] = []

    user_memory[user_id].append({"role":"user","content":user_text})
    user_memory[user_id] = user_memory[user_id][-12:]

    # INTERNET SEARCH
    search_results = web_search(user_text)

    system_prompt = f"""
You are AskSahilAI created by Sahil Singh.

Roles:
- Personal tutor
- Maths solver (step-by-step)
- Coding mentor
- Career advisor
- General assistant

Use internet info if needed:
{search_results}

Rules:
Continue conversation context.
If follow-up question asked, continue topic.
Explain clearly and professionally.
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
        print("AI Error:", e)
        reply = "Server busy. Try again."

    # LOG BOT REPLY
    save_chat(user_id, user_name, "assistant", reply)

    await update.message.reply_text(reply)

# ---------- RUN ----------
app = ApplicationBuilder().token(BOT_TOKEN).build()
app.add_handler(CommandHandler("start",start))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND,handle_message))

print("Bot running...")
app.run_polling()

