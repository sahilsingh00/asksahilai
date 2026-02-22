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

# Google Sheet Logging URL
GOOGLE_SCRIPT_URL = "https://script.google.com/macros/s/AKfycbxt9UNs0zLWgPR3uQYr_Gz1W2zEBmpSLW5DLd4GHb_lew1Hu4VF0nT6iCxe4yktiJ1xjQ/exec"

# -------- AI CLIENT --------
client = OpenAI(
    api_key=GROQ_API_KEY,
    base_url="https://api.groq.com/openai/v1"
)

# -------- MEMORY --------
user_memory = {}

# -------- CLEAN TEXT --------
def clean_text(text):
    text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)
    text = text.replace("```", "")
    return text

# -------- SAVE CHAT --------
def save_chat(userid, name, role, message):
    try:
        requests.post(GOOGLE_SCRIPT_URL, json={
            "userid": str(userid),
            "name": str(name),
            "role": str(role),
            "message": str(message)
        }, timeout=5)
    except Exception as e:
        print("Sheet Error:", e)

# -------- WEB SEARCH --------
def web_search(query):
    if not SERPER_API_KEY:
        return ""

    try:
        url = "https://google.serper.dev/search"
        headers = {"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"}
        payload = {"q": query}

        response = requests.post(url, headers=headers, json=payload, timeout=10)
        data = response.json()

        snippets = []
        for item in data.get("organic", [])[:5]:
            snippets.append(item.get("snippet", ""))

        return "\n".join(snippets)

    except Exception as e:
        print("Search Error:", e)
        return ""

# -------- IMAGE PROMPT ENGINE --------
def generate_image_prompt(user_text):
    try:
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            temperature=0.3,
            messages=[
                {"role":"system","content":"Convert the user request into a clear image prompt. Educational topics = labeled diagram. Career topics = infographic. Objects = realistic photo. Only output prompt."},
                {"role":"user","content":user_text}
            ]
        )
        return response.choices[0].message.content.strip()
    except:
        return user_text

# -------- IMAGE DETECTION --------
def is_image_request(text):
    t = text.lower()
    starters = ["draw ","create ","generate ","make ","show "]
    if any(t.startswith(s) for s in starters):
        return True

    image_words = ["image","picture","photo","diagram","chart","infographic","sketch"]
    if any(w in t for w in image_words):
        return True

    return False

def auto_visual_mode(text):
    t = text.lower()
    question_words = ["what","why","how","when","where","explain","solve","calculate"]
    if any(q in t for q in question_words):
        return False
    if len(t.split()) <= 3:
        return True
    return False

# -------- IMAGE GENERATION --------
async def send_image(update, prompt):

    try:
        final_prompt = generate_image_prompt(prompt)

        prompts = [
            final_prompt,
            f"realistic detailed image of {prompt}, 4k, sharp focus",
            f"educational labeled diagram of {prompt}, clean background"
        ]

        for p in prompts:
            url = f"https://image.pollinations.ai/prompt/{p.replace(' ','%20')}?width=1024&height=1024&seed=7"
            r = requests.get(url, timeout=60)

            if r.status_code == 200 and len(r.content) > 5000:
                img = BytesIO(r.content)
                img.name="ai.png"

                await update.message.reply_photo(photo=img, caption="Generated Visual")

                explanation = client.chat.completions.create(
                    model="llama-3.1-8b-instant",
                    messages=[
                        {"role":"system","content":"Explain this topic simply in points for a student."},
                        {"role":"user","content":prompt}
                    ]
                )

                text = clean_text(explanation.choices[0].message.content)
                await update.message.reply_text(text)

                user_id = update.effective_user.id
                user_name = update.effective_user.first_name
                save_chat(user_id,user_name,"assistant",text)

                return True
        return False

    except Exception as e:
        print("Image Error:",e)
        return False

# -------- START --------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.effective_user.first_name
    await update.message.reply_text(f"""
Hello {name} 👋

I am AskSahilAI — your personal AI learning assistant.

You can:
• Ask study doubts
• Solve maths
• Coding help
• Career guidance
• Get latest news
• Generate diagrams & images

Try:
cat
solve 2x+5=15
latest AI news
python roadmap chart
""")

# -------- CHAT --------
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user_text = update.message.text
    user_id = update.effective_user.id
    user_name = update.effective_user.first_name

    save_chat(user_id,user_name,"user",user_text)

    # IMAGE
    if is_image_request(user_text) or auto_visual_mode(user_text):
        if await send_image(update,user_text):
            return

    # MEMORY
    if user_id not in user_memory:
        user_memory[user_id]=[]

    user_memory[user_id].append({"role":"user","content":user_text})
    user_memory[user_id]=user_memory[user_id][-12:]

    # SEARCH
    search_results=web_search(user_text)

    system_prompt=f"""
You are AskSahilAI created by Sahil Singh.

You are:
- Personal AI tutor
- Maths solver (show steps)
- Coding mentor
- Career advisor
- General knowledge assistant

Use this internet info if needed:
{search_results}

Always:
• Continue conversation context
• Explain clearly
• For maths → solve step-by-step
• Be professional and helpful
"""

    try:
        messages=[{"role":"system","content":system_prompt}]+user_memory[user_id]

        chat=client.chat.completions.create(
            model="llama-3.1-8b-instant",
            temperature=0.7,
            messages=messages
        )

        reply=clean_text(chat.choices[0].message.content)
        user_memory[user_id].append({"role":"assistant","content":reply})

    except Exception as e:
        print("AI Error:",e)
        reply="Server busy. Try again."

    save_chat(user_id,user_name,"assistant",reply)
    await update.message.reply_text(reply)

# -------- RUN --------
app=ApplicationBuilder().token(BOT_TOKEN).build()
app.add_handler(CommandHandler("start",start))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND,handle_message))

print("Bot running...")
app.run_polling()
