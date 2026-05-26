import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI()

# CORS (GitHub Pages / Frontend Access)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==========================
# TELEGRAM BOT TOKEN
# ==========================
BOT_TOKEN = "8725682957:AAHaYE-5vomUfhJ5db6MjoQMPkfakdiyaA0"

class DownloadRequest(BaseModel):
    url: str


@app.get("/")
async def root():
    return {
        "status": "DLX Backend is Running Perfectly!"
    }


@app.post("/download")
async def download_video(req: DownloadRequest):

    url = req.url.strip()

    if not url:
        return {
            "success": False,
            "error": "No URL provided!"
        }

    try:
        async with httpx.AsyncClient(
            timeout=30.0,
            follow_redirects=True
        ) as client:

            # ==========================
            # 1. TIKTOK DOWNLOADER
            # ==========================
            if (
                "tiktok.com" in url
                or "vt.tiktok.com" in url
            ):

                try:
                    api_url = (
                        f"https://www.tikwm.com/api/?url={url}"
                    )

                    res = await client.get(api_url)

                    if res.status_code == 200:

                        data = res.json()

                        video_link = (
                            data.get("data", {})
                            .get("play")
                        )

                        if video_link:

                            if video_link.startswith("//"):
                                video_link = (
                                    "https:" + video_link
                                )

                            return {
                                "success": True,
                                "download_url": video_link,
                                "platform": "tiktok"
                            }

                except Exception as e:
                    print("TikTok Error:", e)

                return {
                    "success": False,
                    "error":
                    "TikTok video source not found."
                }

            # ==========================
            # 2. INSTAGRAM DOWNLOADER
            # ==========================
            elif "instagram.com" in url:

                try:
                    api_url = (
                        "https://api.vkrdown.com"
                        f"/api/download?url={url}"
                    )

                    res = await client.get(api_url)

                    if res.status_code == 200:

                        data = res.json()

                        medias = (
                            data.get("data", {})
                            .get("medias", [])
                        )

                        if medias:

                            media_url = (
                                medias[0].get("url")
                            )

                            if media_url:
                                return {
                                    "success": True,
                                    "download_url":
                                    media_url,
                                    "platform":
                                    "instagram"
                                }

                except Exception as e:
                    print("Instagram Error:", e)

                return {
                    "success": False,
                    "error":
                    "Instagram video not found."
                }

            # ==========================
            # UNSUPPORTED PLATFORM
            # ==========================
            return {
                "success": False,
                "error":
                "Only TikTok & Instagram supported."
            }

    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


# ==========================
# TELEGRAM WEBHOOK
# ==========================
@app.post("/webhook")
async def telegram_webhook(request: Request):
    return {"status": "ok"}
