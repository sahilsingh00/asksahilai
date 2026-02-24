from fastapi import FastAPI
from pydantic import BaseModel
from supabase import create_client
import google.generativeai as genai
import os

app = FastAPI()

# ENV variables
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
GEMINI_API = os.getenv("GEMINI_API")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
genai.configure(api_key=GEMINI_API)

class ChatRequest(BaseModel):
    user_id: str
    platform: str
    message: str

@app.post("/chat")
async def chat(req: ChatRequest):

    # find or create user
    user = supabase.table("users").select("*").eq("platform_user_id", req.user_id).execute()

    if len(user.data) == 0:
        new_user = supabase.table("users").insert({
            "platform": req.platform,
            "platform_user_id": req.user_id
        }).execute()
        user_id = new_user.data[0]["id"]
    else:
        user_id = user.data[0]["id"]

    # create conversation
    conv = supabase.table("conversations").insert({
        "user_id": user_id
    }).execute()

    conversation_id = conv.data[0]["id"]

    # save user message
    supabase.table("messages").insert({
        "conversation_id": conversation_id,
        "role": "user",
        "content": req.message
    }).execute()

    # AI response
    model = genai.GenerativeModel("gemini-1.5-flash")
    response = model.generate_content(req.message)
    reply = response.text

    # save AI message
    supabase.table("messages").insert({
        "conversation_id": conversation_id,
        "role": "assistant",
        "content": reply
    }).execute()

    return {"reply": reply}
