"""
Instagram Media API for Telegram Bots & Developers
Supports GET query parameters: ?url=https://instagram.com/reel/...
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
from pydantic import BaseModel, field_validator

# ─── Configuration ─────────────────────────────────────────────────────────
IS_VERCEL = os.environ.get("VERCEL") == "1" or os.environ.get("VERCEL_ENV") is not None
DOWNLOAD_DIR = Path("/tmp/downloads") if IS_VERCEL else Path("./downloads")
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

executor = ThreadPoolExecutor(max_workers=5)

app = FastAPI(
    title="Instagram Media API",
    description="Query param support: ?url=https://www.instagram.com/reel/...",
    version="2.3.0"
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
        
        direct_url = info.get("url")
        if not direct_url and "formats" in info and len(info["formats"]) > 0:
            direct_url = info["formats"][-1].get("url")

        result = {
            "id": info.get("id"),
            "title": info.get("title") or info.get("fulltitle") or "Instagram Media",
            "uploader": info.get("uploader") or info.get("channel"),
            "duration": info.get("duration"),
            "thumbnail": info.get("thumbnail"),
            "direct_url": direct_url,
            "ext": info.get("ext", "mp4")
        }

        if download_file:
            filename = ydl.prepare_filename(info)
            file_path = Path(filename)
            result["filename"] = file_path.name
            result["download_url"] = f"/download/file/{file_path.name}"
            result["file_size"] = file_path.stat().st_size if file_path.exists() else 0

        return result

# ─── GET API with Query Parameters (?url=...) ──────────────────────────────

@app.get("/")
@app.get("/api")
@app.get("/api/extract")
async def extract_get(url: Optional[str] = Query(None, description="Instagram URL, e.g. https://www.instagram.com/reel/DdjK1JmogNe/")):
    """
    GET API: Open directly in browser or bot via:
    https://instadownload-gamma.vercel.app/?url=https://www.instagram.com/reel/DdjK1JmogNe/
    """
    if not url:
        return {
            "status": "online",
            "usage": "Add '?url=' with your instagram link to fetch direct video URL",
            "example": "https://instadownload-gamma.vercel.app/?url=https://www.instagram.com/reel/DdjK1JmogNe/",
            "docs": "/docs"
        }

    loop = asyncio.get_event_loop()
    try:
        data = await loop.run_in_executor(executor, _extract_media_info, url, False)
        return {"success": True, "data": data}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Extraction failed: {str(e)}")

# ─── POST API Support ───────────────────────────────────────────────────────

@app.post("/api/extract")
@app.post("/api/download")
async def extract_post(req: ReelRequest):
    """POST JSON body: {'url': 'https://...' }"""
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
    return {"status": "ok", "service": "ig-api"}
