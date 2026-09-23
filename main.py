"""
Instagram Media API for Telegram Bots & Developers
Optimized for Vercel Serverless & Cloud Deployments.
"""

import asyncio
import os
import re
import uuid
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

import yt_dlp
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, field_validator

# ─── Configuration ─────────────────────────────────────────────────────────
# On Vercel, only /tmp is writable
IS_VERCEL = os.environ.get("VERCEL") == "1" or os.environ.get("VERCEL_ENV") is not None
DOWNLOAD_DIR = Path("/tmp/downloads") if IS_VERCEL else Path("./downloads")
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

executor = ThreadPoolExecutor(max_workers=5)

app = FastAPI(
    title="Instagram Media API",
    description="Fast API to fetch direct MP4 links, thumbnails, and media for Telegram Bots.",
    version="2.2.0"
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

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        v = v.strip()
        if not v.startswith("http://") and not v.startswith("https://"):
            if re.match(r"^[A-Za-z0-9_-]+$", v):
                v = f"https://www.instagram.com/reel/{v}/"
            else:
                raise ValueError("Invalid Instagram URL or Reel shortcode")
        return v

# ─── Core Extraction Logic ─────────────────────────────────────────────────
def _extract_media_info(url: str, download_file: bool = False) -> dict:
    """Extract direct CDN links & metadata. Fast extraction for Telegram Bots."""
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
        
        # Best direct stream URL (Instagram CDN)
        direct_url = info.get("url")
        if not direct_url and "formats" in info and len(info["formats"]) > 0:
            direct_url = info["formats"][-1].get("url")

        result = {
            "id": info.get("id"),
            "title": info.get("title") or info.get("fulltitle") or "Instagram Media",
            "uploader": info.get("uploader") or info.get("channel"),
            "duration": info.get("duration"),
            "thumbnail": info.get("thumbnail"),
            "direct_url": direct_url,  # Direct MP4 CDN link for Telegram Bot
            "ext": info.get("ext", "mp4")
        }

        if download_file:
            filename = ydl.prepare_filename(info)
            file_path = Path(filename)
            result["filename"] = file_path.name
            result["download_url"] = f"/download/file/{file_path.name}"
            result["file_size"] = file_path.stat().st_size if file_path.exists() else 0

        return result

# ─── API Endpoints for Telegram Bots ───────────────────────────────────────

@app.get("/")
async def root():
    return {
        "status": "online",
        "service": "Instagram Media API",
        "endpoints": {
            "extract_direct_link": "POST /api/extract (Fastest for Telegram Bot)",
            "download_media": "POST /api/download",
            "docs": "/docs"
        }
    }

@app.post("/api/extract")
async def extract_direct(req: ReelRequest):
    """
    Fastest Endpoint for Telegram Bots:
    Returns direct Instagram CDN .mp4 URL & thumbnail without downloading to server.
    Your bot can directly do: bot.send_video(chat_id, video=data['direct_url'])
    """
    loop = asyncio.get_event_loop()
    try:
        data = await loop.run_in_executor(executor, _extract_media_info, req.url, False)
        return {"success": True, "data": data}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Extraction failed: {str(e)}")

@app.post("/api/download")
@app.post("/download/reel")
async def download_media(req: ReelRequest):
    """Downloads media locally and returns file download URL."""
    loop = asyncio.get_event_loop()
    try:
        data = await loop.run_in_executor(executor, _extract_media_info, req.url, True)
        return {"success": True, "data": data}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Download failed: {str(e)}")

@app.get("/download/file/{filename}")
async def serve_file(filename: str):
    """Serve downloaded file."""
    safe_name = Path(filename).name
    file_path = DOWNLOAD_DIR / safe_name
    
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(
        path=file_path,
        filename=safe_name,
        media_type="application/octet-stream"
    )

@app.get("/health")
async def health():
    return {"status": "ok", "service": "ig-api"}
