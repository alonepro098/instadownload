"""
InstaDownloader - Fast & Modern Instagram Media Downloader
Supports Instagram Reels, Videos, Posts & Carousels.
"""

import asyncio
import os
import re
import uuid
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

import yt_dlp
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, field_validator

# ─── Configuration ─────────────────────────────────────────────────────────
DOWNLOAD_DIR = Path("./downloads")
DOWNLOAD_DIR.mkdir(exist_ok=True)

executor = ThreadPoolExecutor(max_workers=5)

app = FastAPI(
    title="InstaSaver Pro",
    description="High-speed Instagram Reels & Video Downloader",
    version="2.1.0"
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

# ─── Core Extraction Logic via yt-dlp ──────────────────────────────────────
def _extract_and_download(url: str) -> dict:
    unique_id = uuid.uuid4().hex[:8]
    ydl_opts = {
        'outtmpl': str(DOWNLOAD_DIR / f'%(id)s_{unique_id}.%(ext)s'),
        'format': 'best',
        'quiet': True,
        'no_warnings': True,
    }
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)
        file_path = Path(filename)
        
        return {
            "id": info.get("id"),
            "filename": file_path.name,
            "download_url": f"/download/file/{file_path.name}",
            "file_size": file_path.stat().st_size if file_path.exists() else 0,
            "ext": info.get("ext", "mp4")
        }

# ─── Endpoints ─────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def home():
    """Serve the Instagram Downloader Web Interface."""
    return HTMLResponse(content=HTML_PAGE)

@app.post("/api/download")
@app.post("/download/reel")
async def download_media(req: ReelRequest):
    """API endpoint to extract and process media."""
    loop = asyncio.get_event_loop()
    try:
        data = await loop.run_in_executor(executor, _extract_and_download, req.url)
        return {"success": True, "data": data}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Download failed: {str(e)}")

@app.get("/download/file/{filename}")
async def serve_file(filename: str):
    """Serve downloaded file for local instant download."""
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
    return {"status": "ok", "service": "instasaver-web"}

# ─── Frontend Web Page ─────────────────────────────────────────────────────
HTML_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>InstaSaver | Instagram Video & Reel Downloader</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg: #0b0f19;
      --card-bg: rgba(18, 24, 38, 0.75);
      --card-border: rgba(255, 255, 255, 0.08);
      --ig-gradient: linear-gradient(135deg, #f09433 0%, #e6683c 25%, #dc2743 50%, #cc2366 75%, #bc1888 100%);
      --ig-gradient-hover: linear-gradient(135deg, #f3a652 0%, #eb7c54 25%, #e13e56 50%, #d43b79 75%, #c52e95 100%);
      --text: #f8fafc;
      --text-muted: #94a3b8;
      --success: #10b981;
      --error: #ef4444;
    }

    * {
      box-sizing: border-box;
      margin: 0;
      padding: 0;
    }

    body {
      font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif;
      background-color: var(--bg);
      background-image: 
        radial-gradient(circle at 15% 15%, rgba(220, 39, 67, 0.12) 0%, transparent 40%),
        radial-gradient(circle at 85% 85%, rgba(188, 24, 136, 0.12) 0%, transparent 40%);
      color: var(--text);
      min-height: 100vh;
      display: flex;
      flex-direction: column;
      align-items: center;
      padding: 30px 16px;
    }

    .container {
      width: 100%;
      max-width: 600px;
    }

    /* Top Navbar */
    .navbar {
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 12px;
      margin-bottom: 24px;
    }

    .logo-icon {
      width: 38px;
      height: 38px;
      border-radius: 12px;
      background: var(--ig-gradient);
      display: flex;
      align-items: center;
      justify-content: center;
      box-shadow: 0 4px 15px rgba(220, 39, 67, 0.4);
    }

    .logo-icon svg {
      width: 22px;
      height: 22px;
      fill: #fff;
    }

    .logo-text {
      font-size: 1.4rem;
      font-weight: 800;
      background: var(--ig-gradient);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      letter-spacing: -0.5px;
    }

    /* Hero */
    .hero {
      text-align: center;
      margin-bottom: 24px;
    }

    .hero h1 {
      font-size: 2rem;
      font-weight: 800;
      line-height: 1.2;
      margin-bottom: 8px;
      letter-spacing: -0.5px;
    }

    .hero p {
      color: var(--text-muted);
      font-size: 0.95rem;
    }

    /* Main Box */
    .downloader-card {
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 24px;
      padding: 24px;
      backdrop-filter: blur(20px);
      box-shadow: 0 20px 50px rgba(0, 0, 0, 0.5);
      margin-bottom: 20px;
    }

    .input-wrapper {
      display: flex;
      flex-direction: column;
      gap: 12px;
    }

    .input-box {
      display: flex;
      background: rgba(11, 15, 25, 0.9);
      border: 1.5px solid rgba(255, 255, 255, 0.12);
      border-radius: 16px;
      padding: 6px;
      transition: all 0.25s ease;
    }

    .input-box:focus-within {
      border-color: #e6683c;
      box-shadow: 0 0 0 4px rgba(230, 104, 60, 0.2);
    }

    input[type="text"] {
      flex: 1;
      background: transparent;
      border: none;
      outline: none;
      padding: 14px 16px;
      font-size: 0.95rem;
      color: #fff;
      font-family: inherit;
    }

    input[type="text"]::placeholder {
      color: rgba(255, 255, 255, 0.35);
    }

    .btn-paste {
      background: rgba(255, 255, 255, 0.08);
      color: #fff;
      border: none;
      border-radius: 12px;
      padding: 0 16px;
      font-size: 0.88rem;
      font-weight: 600;
      cursor: pointer;
      display: flex;
      align-items: center;
      gap: 6px;
      transition: background 0.2s;
    }

    .btn-paste:hover {
      background: rgba(255, 255, 255, 0.16);
    }

    .btn-download-main {
      background: var(--ig-gradient);
      color: #fff;
      border: none;
      border-radius: 16px;
      padding: 16px;
      font-size: 1.05rem;
      font-weight: 700;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 10px;
      transition: all 0.25s ease;
      box-shadow: 0 6px 20px rgba(220, 39, 67, 0.35);
    }

    .btn-download-main:hover {
      background: var(--ig-gradient-hover);
      transform: translateY(-2px);
      box-shadow: 0 8px 25px rgba(220, 39, 67, 0.5);
    }

    .btn-download-main:disabled {
      opacity: 0.6;
      cursor: not-allowed;
      transform: none;
    }

    /* Loader */
    .loader-area {
      display: none;
      text-align: center;
      padding: 24px 0;
    }

    .spinner {
      width: 40px;
      height: 40px;
      border: 4px solid rgba(255, 255, 255, 0.1);
      border-top-color: #dc2743;
      border-radius: 50%;
      animation: spin 0.8s linear infinite;
      margin: 0 auto 10px;
    }

    @keyframes spin {
      100% { transform: rotate(360deg); }
    }

    /* Result Card */
    .result-section {
      display: none;
      margin-top: 20px;
      padding-top: 20px;
      border-top: 1px solid rgba(255, 255, 255, 0.08);
      animation: fadeIn 0.35s ease;
    }

    @keyframes fadeIn {
      from { opacity: 0; transform: translateY(12px); }
      to { opacity: 1; transform: translateY(0); }
    }

    .video-frame {
      width: 100%;
      border-radius: 16px;
      max-height: 440px;
      background: #000;
      box-shadow: 0 10px 30px rgba(0, 0, 0, 0.6);
      margin-bottom: 16px;
    }

    .btn-save {
      background: #10b981;
      color: #fff;
      text-decoration: none;
      border-radius: 16px;
      padding: 16px;
      font-size: 1.05rem;
      font-weight: 700;
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 10px;
      transition: all 0.2s;
      box-shadow: 0 4px 15px rgba(16, 185, 129, 0.3);
    }

    .btn-save:hover {
      background: #059669;
      transform: translateY(-2px);
      box-shadow: 0 6px 20px rgba(16, 185, 129, 0.45);
    }

    /* Error Banner */
    .error-banner {
      display: none;
      background: rgba(239, 68, 68, 0.15);
      border: 1px solid rgba(239, 68, 68, 0.35);
      color: #fca5a5;
      padding: 12px 16px;
      border-radius: 14px;
      margin-top: 14px;
      font-size: 0.9rem;
    }

    /* Feature tags */
    .tags-row {
      display: flex;
      justify-content: center;
      gap: 8px;
      flex-wrap: wrap;
      margin-top: 16px;
    }

    .tag-item {
      font-size: 0.78rem;
      padding: 6px 12px;
      border-radius: 999px;
      background: rgba(255, 255, 255, 0.05);
      border: 1px solid rgba(255, 255, 255, 0.08);
      color: var(--text-muted);
      font-weight: 500;
    }

    /* Footer */
    .footer {
      text-align: center;
      font-size: 0.82rem;
      color: var(--text-muted);
      margin-top: auto;
      padding-top: 20px;
    }
  </style>
</head>
<body>

  <div class="container">
    <!-- Navbar -->
    <div class="navbar">
      <div class="logo-icon">
        <svg viewBox="0 0 24 24">
          <path d="M12 2.163c3.204 0 3.584.012 4.85.07 3.252.148 4.771 1.691 4.919 4.919.058 1.265.069 1.645.069 4.849 0 3.205-.012 3.584-.069 4.849-.149 3.225-1.664 4.771-4.919 4.919-1.266.058-1.644.07-4.85.07-3.204 0-3.584-.012-4.849-.07-3.26-.149-4.771-1.699-4.919-4.92-.058-1.265-.07-1.644-.07-4.849 0-3.204.013-3.583.07-4.849.149-3.227 1.664-4.771 4.919-4.919 1.266-.057 1.645-.069 4.849-.069zm0-2.163c-3.259 0-3.667.014-4.947.072-4.358.2-6.78 2.618-6.98 6.98-.059 1.281-.073 1.689-.073 4.948 0 3.259.014 3.668.072 4.948.2 4.358 2.618 6.78 6.98 6.98 1.281.058 1.689.072 4.948.072 3.259 0 3.668-.014 4.948-.072 4.354-.2 6.782-2.618 6.979-6.98.059-1.28.073-1.689.073-4.948 0-3.259-.014-3.667-.072-4.947-.196-4.354-2.617-6.78-6.979-6.98-1.281-.059-1.69-.073-4.949-.073zm0 5.838c-3.403 0-6.162 2.759-6.162 6.162s2.759 6.163 6.162 6.163 6.162-2.759 6.162-6.163c0-3.403-2.759-6.162-6.162-6.162zm0 10.162c-2.209 0-4-1.79-4-4 0-2.209 1.791-4 4-4s4 1.791 4 4c0 2.21-1.791 4-4 4zm6.406-11.845c-.796 0-1.441.645-1.441 1.44s.645 1.44 1.441 1.44c.795 0 1.439-.645 1.439-1.44s-.644-1.44-1.439-1.44z"/>
        </svg>
      </div>
      <span class="logo-text">InstaSaver</span>
    </div>

    <!-- Hero -->
    <div class="hero">
      <h1>Instagram Downloader</h1>
      <p>Download Reels, Videos & Posts in Full HD</p>
    </div>

    <!-- Downloader Card -->
    <div class="downloader-card">
      <div class="input-wrapper">
        <div class="input-box">
          <input 
            type="text" 
            id="urlInput" 
            placeholder="Paste Instagram Reel or Post Link here..."
            autocomplete="off"
            spellcheck="false"
          >
          <button class="btn-paste" onclick="pasteLink()">
            📋 Paste
          </button>
        </div>

        <button id="downloadBtn" class="btn-download-main" onclick="startDownload()">
          <span>⚡</span>
          <span>Download Video</span>
        </button>
      </div>

      <!-- Loading Spinner -->
      <div id="loaderArea" class="loader-area">
        <div class="spinner"></div>
        <p style="color: var(--text-muted); font-size: 0.9rem;">Fetching video...</p>
      </div>

      <!-- Error Message -->
      <div id="errorBanner" class="error-banner"></div>

      <!-- Result Card -->
      <div id="resultSection" class="result-section">
        <video id="videoPlayer" class="video-frame" controls autoplay muted></video>

        <a id="saveFileBtn" class="btn-save" download>
          <span>⬇️</span>
          <span id="saveBtnText">Download Video (.mp4)</span>
        </a>
      </div>
    </div>

    <!-- Supported Features -->
    <div class="tags-row">
      <span class="tag-item">✨ Instagram Reels</span>
      <span class="tag-item">📹 HD Videos</span>
      <span class="tag-item">📸 Photo Posts</span>
      <span class="tag-item">⚡ Instant Download</span>
    </div>

    <!-- Footer -->
    <div class="footer">
      <p>Created with FastAPI &bull; Fast, Private & Free</p>
    </div>
  </div>

  <script>
    async function pasteLink() {
      try {
        const text = await navigator.clipboard.readText();
        if (text) {
          document.getElementById('urlInput').value = text.trim();
        }
      } catch (err) {
        document.getElementById('urlInput').focus();
      }
    }

    async function startDownload() {
      const urlInput = document.getElementById('urlInput');
      const url = urlInput.value.trim();
      const loader = document.getElementById('loaderArea');
      const errorBanner = document.getElementById('errorBanner');
      const resultSection = document.getElementById('resultSection');
      const downloadBtn = document.getElementById('downloadBtn');

      if (!url) {
        errorBanner.textContent = "Please enter or paste an Instagram link!";
        errorBanner.style.display = "block";
        return;
      }

      // Reset states
      errorBanner.style.display = "none";
      resultSection.style.display = "none";
      loader.style.display = "block";
      downloadBtn.disabled = true;

      try {
        const response = await fetch('/api/download', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ url: url })
        });

        const res = await response.json();

        if (!response.ok || !res.success) {
          throw new Error(res.detail || "Could not fetch media. Please check link.");
        }

        const data = res.data;
        const videoPlayer = document.getElementById('videoPlayer');
        videoPlayer.src = data.download_url;

        const saveBtn = document.getElementById('saveFileBtn');
        saveBtn.href = data.download_url;
        saveBtn.download = data.filename;

        resultSection.style.display = "block";

        // Trigger automatic download smoothly
        const autoLink = document.createElement('a');
        autoLink.href = data.download_url;
        autoLink.download = data.filename;
        document.body.appendChild(autoLink);
        autoLink.click();
        document.body.removeChild(autoLink);

      } catch (err) {
        errorBanner.textContent = err.message || "Failed to download video. Ensure account is public.";
        errorBanner.style.display = "block";
      } finally {
        loader.style.display = "none";
        downloadBtn.disabled = false;
      }
    }

    // Support Enter key
    document.getElementById('urlInput').addEventListener('keypress', function (e) {
      if (e.key === 'Enter') {
        startDownload();
      }
    });
  </script>
</body>
</html>
"""
