import os
import re
import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI()

# ⚠️ የትኛውም ድረገጽ ከሰርቨሩ ጋር እንዲገናኝ መፍቀድ (የመቆም/Freezing ችግርን ይፈታል)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BOT_TOKEN = "8725682957:AAHaYE-5vomUfhJ5db6MjoQMPkfakdiyaA0"  #8725682957:AAHaYE-5vomUfhJ5db6MjoQMPkfakdiyaA0

class DownloadRequest(BaseModel):
    url: str

@app.get("/")
async def root():
    return {"status": "DLX Backend is Running Successfully!"}

@app.post("/download")
async def download_video(req: DownloadRequest):
    url = req.url
    
    # 🔍 የቲክቶክ ሊንክ መሆኑን ማረጋገጥ
    if "tiktok.com" in url:
        try:
            # በጣም ፈጣን እና አዲስ የቲክቶክ ኤፒአይ (ያለ ዋተርማርክ)
            api_url = f"https://api.tiklydown.eu.org/api/download?url={url}"
            async with httpx.AsyncClient(timeout=15.0) as client:
                res = await client.get(api_url)
                data = res.json()
                
                # የቪዲዮ ሊንኩን ማውጣት
                video_link = data.get("video", {}).get("noWatermark") or data.get("video", {}).get("noWatermarkHD")
                if video_link:
                    return {"success": True, "download_url": video_link}
                else:
                    return {"success": False, "error": "Could not extract watermark-free video."}
        except Exception as e:
            return {"success": False, "error": f"TikTok API error: {str(e)}"}
            
    # 🔍 የኢንስታግራም ሊንክ መሆኑን ማረጋገጥ
    elif "instagram.com" in url:
        try:
            api_url = f"https://api.vkrdown.com/api/download?url={url}"
            async with httpx.AsyncClient(timeout=15.0) as client:
                res = await client.get(api_url)
                data = res.json()
                
                # የኢንስታግራም ማውረጃ ሊንክ ፍለጋ
                medias = data.get("data", {}).get("medias", [])
                if medias:
                    video_link = medias[0].get("url")
                    return {"success": True, "download_url": video_link}
                return {"success": False, "error": "Instagram media not found."}
        except Exception as e:
            return {"success": False, "error": f"Instagram API error: {str(e)}"}

    return {"success": False, "error": "This platform is not supported yet!"}

# ቴሌግራም ዌብሁክ መቀበያ መስመር
@app.post("/webhook")
async def telegram_webhook(request: Request):
    return {"status": "ok"}
