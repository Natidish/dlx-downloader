import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import yt_dlp
import requests

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# የቴሌግራም ቦት እና የቻናል መረጃዎች
BOT_TOKEN = "8725682957:AAHaYE-5vomUfhJ5db6MjoQMPkfakdiyaA0"      # ከ @BotFather ያገኘኸው Token
CHANNEL_ID = "@hbeo11"   # የአንተ ቻናል ዩዘርኔም (በ @ የሚጀምር)

class DownloadRequest(BaseModel): 
    url: str

class CheckJoinRequest(BaseModel):
    user_id: str

@app.post("/check-join")
def check_channel_membership(request: CheckJoinRequest):
    """ተጠቃሚው ቻናሉን ጆይን ማድረጉን ማረጋገጫ"""
    if not request.user_id:
        raise HTTPException(status_code=400, detail="User ID ያስፈልጋል")
    
    # የቴሌግራም getChatMember API በመጠቀም ማረጋገጥ
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/getChatMember"
    params = {"chat_id": CHANNEL_ID, "user_id": request.user_id}
    
    try:
        response = requests.get(url, params=params).json()
        if response.get("ok"):
            status = response["result"]["status"]
            # ተጠቃሚው አባል ከሆነ status 'member', 'administrator', ወይም 'creator' ይሆናል
            if status in ["member", "administrator", "creator"]:
                return {"is_joined": True}
        return {"is_joined": False}
    except Exception:
        # ሰርቨሩ ቢበላሽ ተጠቃሚው እንዳይስተጓጎል በነፃ ማለፍ
        return {"is_joined": True}

@app.post("/extract")
def extract_media(request: DownloadRequest):
    if not request.url:
        raise HTTPException(status_code=400, detail="ሊንክ አልተገኘም")

    ydl_opts = {
        'format': 'best',
        'quiet': True,
        'no_warnings': True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(request.url, download=False)
            return {
                "status": "success",
                "title": info.get('title', 'Media File'),
                "download_url": info.get('url')
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
