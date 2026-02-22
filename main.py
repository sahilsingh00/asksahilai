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

# ---------------- AI CLIENT ----------------
client = OpenAI(
    api_key=GROQ_API_KEY,
    base_url="https://api.groq.com/openai/v1"
)

# ---------------- MEMORY ----------------
user_memory = {}

# ---------------- CLEAN TEXT ----------------
def clean_text(text):
    text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)
    text = text.replace("```", "")
    return text


# ---------------- WEB SEARCH ----------------
def web_search(query):

    if not SERPER_API_KEY:
        return ""

    try:
        url = "https://google.serper.dev/search"
        headers = {
            "X-API-KEY": SERPER_API_KEY,
            "Content-Type": "application/json"
        }

        payload = {"q": query}
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        data = response.json()

        snippets = []
        for item in data.get("organic", [])[:5]:
            snippets.append(item.get("snippet", ""))

        return "\n".join(snippets)

    except Exception as e:
        print("SEARCH ERROR:", e)
        return ""


# ---------------- IMAGE PROMPT ENGINE ----------------
def generate_image_prompt(user_text):
    try:
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            temperature=0.3,
            messages=[
                {
                    "role": "system",
                    "content": """
You are an expert image prompt engineer.

Convert user request into an image generation prompt.

Rules:
- Only output prompt
- No explanation
- If study topic → labeled diagram
- If career topic → infographic
- If object → realistic photo
Add: ultra detailed, clean background, professional lighting, 4k, sharp focus
"""
                },
                {"role": "user", "content": user_text}
            ]
        )
        return response.choices[0].message.content.strip()
    except:
        return user_text


# ---------------- IMAGE INTENT ----------------
def is_image_request(text: str):
    t = text.lower().strip()

    starters = ["draw ", "create ", "generate ", "make ", "show "]
    if any(t.startswith(s) for s in starters):
        return True

    image_words = ["image","picture","photo","diagram","chart","infographic","sketch","illustration"]
    request_words = ["show","send","give","mujhe","chahiye","dikhao","bhejo","i want","i need"]

    if any(w in t for w in image_words) and any(r in t for r in request_words):
        return True

    return False


# ---------------- AUTO VISUAL MODE ----------------
def auto_visual_mode(text: str):
    t = text.lower().strip()

    question_words = ["what","why","how","when","where","explain","kaise","kyu","kya"]
    if any(q in t for q in question_words):
        return False

    words = t.split()

    if 1 <= len(words) <= 3:
        return True

    return False


# ---------------- IMAGE GENERATOR ----------------
async def send_image(update, prompt):

    try:
        final_prompt = generate_image_prompt(prompt)

        prompts_to_try = [
            final_prompt,
            f"realistic detailed image of {prompt}, high detail, 4k, sharp focus",
            f"educational labeled diagram of {prompt}, clean background, high resolution"
        ]

        for p in prompts_to_try:

            img_url = f"https://image.pollinations.ai/prompt/{p.replace(' ', '%20')}?width=1024&height=1024&seed=7"
            response = requests.get(img_url, timeout=60)

            if response.status_code == 200 and len(response.content) > 5000:
                image_bytes = BytesIO(response.content)
                image_bytes.name = "ai.png"

                await update.message.reply_photo(photo=image_bytes, caption="Here is your generated image")

                explanation = client.chat.completions.create(
                    model="llama-3.1-8b-instant",
                    temperature=0.5,
                    messages=[
                        {"role": "system", "content": "Explain this topic in short simple bullet points for a student."},
                        {"role": "user", "content": prompt}
                    ]
                )

                text = clean_text(explanation.choices[0].message.content)
                await update.message.reply_text(text)

                return True

        return False

    except Exception as e:
        print("IMAGE ERROR:", e)
        return False


# ---------------- START ----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user.first_name

    await update.message.reply_text(f"""
👋 Welcome {user}

I am *AskSahilAI* — your AI assistant.

You can ask:
• Study questions
• Coding help
• Career guidance
• Generate images & diagrams
• Latest news & current affairs

Try:
cat
ai classroom
latest AI news
solar system diagram
""", parse_mode="Markdown")


# ---------------- /IMAGE COMMAND ----------------
async def image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    prompt = " ".join(context.args)
    if not prompt:
        await update.message.reply_text("Usage: /image human heart diagram")
        return
    await send_image(update, prompt)


# ---------------- CHAT ----------------
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user_text = update.message.text
    user_id = update.effective_user.id

    # IMAGE ROUTING
    if is_image_request(user_text):
        if await send_image(update, user_text):
            return

    if auto_visual_mode(user_text):
        if await send_image(update, user_text):
            return

    # MEMORY
    if user_id not in user_memory:
        user_memory[user_id] = []

    user_memory[user_id].append({"role": "user", "content": user_text})
    user_memory[user_id] = user_memory[user_id][-12:]

    # INTERNET SEARCH
    search_results = web_search(user_text)

    try:
        messages = [{
            "role": "system",
            "content": f"""
You are AskSahilAI, an intelligent assistant created by Sahil Singh.

Use this real-time internet information if useful:
{search_results}

Rules:
- Continue conversation context
- Be clear and professional
- If current affairs asked → rely on internet info
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


# ---------------- RUN ----------------
app = ApplicationBuilder().token(BOT_TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("image", image))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

print("Bot running...")
app.run_polling()
