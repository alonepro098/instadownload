"""
Instagram Media API for Telegram Bots & Developers
Extracts Video (.mp4) and Separate Pure Audio (.m4a/aac/mp3)
"""

import asyncio
import os
import re
import uuid
from pathlib import Path
from typing import Optional
from concurrent.futures import ThreadPoolExecutor

import yt_dlp
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ─── Configuration ─────────────────────────────────────────────────────────
IS_VERCEL = os.environ.get("VERCEL") == "1" or os.environ.get("VERCEL_ENV") is not None
DOWNLOAD_DIR = Path("/tmp/downloads") if IS_VERCEL else Path("./downloads")
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

executor = ThreadPoolExecutor(max_workers=5)

app = FastAPI(
    title="Instagram Video & Audio API",
    description="Extracts both Video (MP4) and pure Audio stream from Instagram Reels & Posts.",
    version="2.4.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Models ────────────────────────────────────────────────────────────────
class ReelRequest(BaseModel):
    url: str

# ─── Core Extraction Logic ─────────────────────────────────────────────────
def _extract_media_info(url: str, download_file: bool = False) -> dict:
    url = url.strip()
    if not url.startswith("http://") and not url.startswith("https://"):
        if re.match(r"^[A-Za-z0-9_-]+$", url):
            url = f"https://www.instagram.com/reel/{url}/"
        else:
            raise ValueError("Invalid Instagram URL or Reel shortcode")

    unique_id = uuid.uuid4().hex[:8]
    ydl_opts = {
        'format': 'best',
        'quiet': True,
        'no_warnings': True,
    }
    
    if download_file:
        ydl_opts['outtmpl'] = str(DOWNLOAD_DIR / f'%(id)s_{unique_id}.%(ext)s')

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=download_file)
        
        # 1. Best Video URL (Instagram CDN)
        direct_url = info.get("url")
        if not direct_url and "formats" in info and len(info["formats"]) > 0:
            direct_url = info["formats"][-1].get("url")

        # 2. Extract Separate Pure Audio Stream (if available in DASH formats)
        audio_url = None
        formats = info.get("formats", [])
        pure_audio = [f for f in formats if f.get("acodec") != "none" and f.get("vcodec") == "none"]
        if pure_audio:
            # Pick highest bitrate audio
            pure_audio.sort(key=lambda f: f.get("tbr") or f.get("abr") or 0)
            audio_url = pure_audio[-1].get("url")
        
        # Fallback to direct_url if standalone audio track is not provided separately
        if not audio_url:
            audio_url = direct_url

        result = {
            "id": info.get("id"),
            "title": info.get("title") or info.get("fulltitle") or "Instagram Media",
            "uploader": info.get("uploader") or info.get("channel"),
            "duration": info.get("duration"),
            "thumbnail": info.get("thumbnail"),
            "direct_url": direct_url,    # Full Video (.mp4)
            "audio_url": audio_url,      # Pure Audio Track (.m4a / .mp3 stream)
            "has_separate_audio": bool(pure_audio),
            "ext": info.get("ext", "mp4")
        }

        if download_file:
            filename = ydl.prepare_filename(info)
            file_path = Path(filename)
            result["filename"] = file_path.name
            result["download_url"] = f"/download/file/{file_path.name}"
            result["file_size"] = file_path.stat().st_size if file_path.exists() else 0

        return result

# ─── Endpoints ─────────────────────────────────────────────────────────────

@app.get("/")
@app.get("/api")
@app.get("/api/extract")
async def extract_get(url: Optional[str] = Query(None, description="Instagram URL, e.g. https://www.instagram.com/reel/DdjK1JmogNe/")):
    """
    GET API: Pass ?url=... to get Video & Separate Audio URL.
    """
    if not url:
        return {
            "status": "online",
            "usage": "https://instadownload-gamma.vercel.app/api?url=YOUR_INSTAGRAM_LINK",
            "features": ["Video (MP4)", "Separate Pure Audio (M4A/MP3)", "Thumbnail"],
            "docs": "/docs"
        }

    loop = asyncio.get_event_loop()
    try:
        data = await loop.run_in_executor(executor, _extract_media_info, url, False)
        return {"success": True, "data": data}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Extraction failed: {str(e)}")

@app.post("/api/extract")
@app.post("/api/download")
async def extract_post(req: ReelRequest):
    loop = asyncio.get_event_loop()
    try:
        data = await loop.run_in_executor(executor, _extract_media_info, req.url, False)
        return {"success": True, "data": data}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Extraction failed: {str(e)}")

@app.get("/download/file/{filename}")
async def serve_file(filename: str):
    safe_name = Path(filename).name
    file_path = DOWNLOAD_DIR / safe_name
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(path=file_path, filename=safe_name, media_type="application/octet-stream")

@app.get("/health")
async def health():
    return {"status": "ok", "service": "ig-api", "version": "2.4.0"}
