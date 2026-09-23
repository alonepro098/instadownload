"""
Instagram Public Profile Downloader API
Only works with PUBLIC accounts. No login required for public content.
"""

import asyncio
import uuid
import shutil
from pathlib import Path
from datetime import datetime
from typing import Optional, List
from concurrent.futures import ThreadPoolExecutor

import instaloader
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, field_validator

# ─── Config ────────────────────────────────────────────────────────────────
DOWNLOAD_DIR = Path("./downloads")
DOWNLOAD_DIR.mkdir(exist_ok=True)

MAX_POSTS_DEFAULT = 20
executor = ThreadPoolExecutor(max_workers=3)

app = FastAPI(
    title="Instagram Public Downloader",
    description="Download media from PUBLIC Instagram profiles only.",
    version="1.0.0"
)

# ─── Job Store (replace with Redis/DB in production) ───────────────────────
jobs: dict = {}

# ─── Models ────────────────────────────────────────────────────────────────
class DownloadRequest(BaseModel):
    username: str
    max_posts: int = MAX_POSTS_DEFAULT
    download_media: bool = True
    
    @field_validator("username")
    @classmethod
    def clean_username(cls, v: str) -> str:
        v = v.strip().lstrip("@").lower()
        if not v or not v.replace("_", "").replace(".", "").isalnum():
            raise ValueError("Invalid Instagram username format")
        return v

class MediaItem(BaseModel):
    shortcode: str
    media_type: str
    url: Optional[str] = None
    video_url: Optional[str] = None
    caption: Optional[str] = None
    likes: Optional[int] = None
    comments: Optional[int] = None
    date_utc: Optional[str] = None
    is_video: bool = False

class DownloadResponse(BaseModel):
    job_id: str
    username: str
    status: str
    total_posts: int = 0
    media: List[MediaItem] = []
    local_files: List[str] = []
    error: Optional[str] = None

# ─── Core Instaloader Logic ────────────────────────────────────────────────

def _fetch_profile_sync(username: str, max_posts: int, download_media: bool, job_id: str):
    """
    Runs in thread — Instaloader is sync.
    Only works with PUBLIC profiles.
    """
    loader = instaloader.Instaloader(
        dirname_pattern=str(DOWNLOAD_DIR / "{target}"),
        filename_pattern="{date_utc:%Y%m%d_%H%M%S}_{shortcode}",
        download_pictures=download_media,
        download_videos=download_media,
        download_video_thumbnails=False,
        download_geotags=False,
        download_comments=False,
        save_metadata=True,
        post_metadata_txt_pattern=""  # We handle metadata ourselves
    )

    profile = instaloader.Profile.from_username(loader.context, username)

    # Hard stop: only public
    if profile.is_private:
        raise PermissionError(
            f"@{username} is PRIVATE. This API only supports public profiles."
        )

    posts = []
    local_files = []
    count = 0

    for post in profile.get_posts():
        if count >= max_posts:
            break

        item = {
            "shortcode": post.shortcode,
            "media_type": post.typename,
            "caption": (post.caption or "")[:500],  # truncate
            "likes": post.likes,
            "comments": post.comments,
            "date_utc": post.date_utc.isoformat() if post.date_utc else None,
            "is_video": post.is_video,
            "url": post.url,
            "video_url": post.video_url if post.is_video else None,
        }
        posts.append(item)

        if download_media:
            try:
                loader.download_post(post, target=username)
                # Instaloader saves files; collect them
                profile_dir = DOWNLOAD_DIR / username
                for f in profile_dir.iterdir():
                    if post.shortcode in f.name:
                        local_files.append(str(f))
            except Exception as e:
                # Don't fail whole job for one file
                print(f"[warn] Failed to download {post.shortcode}: {e}")

        count += 1

        # Update job progress
        jobs[job_id]["total_posts"] = count
        jobs[job_id]["media"] = posts
        jobs[job_id]["local_files"] = local_files

    return posts, local_files


async def _fetch_profile_async(username, max_posts, download_media, job_id):
    loop = asyncio.get_event_loop()
    try:
        posts, files = await loop.run_in_executor(
            executor, _fetch_profile_sync, username, max_posts, download_media, job_id
        )
        jobs[job_id].update({
            "status": "completed",
            "total_posts": len(posts),
            "media": posts,
            "local_files": files,
            "completed_at": datetime.utcnow().isoformat()
        })
    except PermissionError as e:
        jobs[job_id].update({"status": "failed", "error": str(e)})
    except instaloader.exceptions.ProfileNotExistsException:
        jobs[job_id].update({"status": "failed", "error": f"@{username} does not exist"})
    except instaloader.exceptions.LoginRequiredException:
        jobs[job_id].update({
            "status": "failed",
            "error": "Instagram requires login for this profile. It may not be truly public."
        })
    except Exception as e:
        jobs[job_id].update({"status": "failed", "error": f"Unexpected: {str(e)}"})


# ─── Endpoints ─────────────────────────────────────────────────────────────

@app.post("/download/profile", response_model=DownloadResponse)
async def download_profile(req: DownloadRequest, background: BackgroundTasks):
    """
    Start a download job for a PUBLIC Instagram profile.
    Returns immediately with a job_id. Poll /status/{job_id} for progress.
    """
    job_id = uuid.uuid4().hex[:12]
    jobs[job_id] = {
        "job_id": job_id,
        "username": req.username,
        "status": "queued",
        "total_posts": 0,
        "media": [],
        "local_files": [],
        "error": None,
        "created_at": datetime.utcnow().isoformat()
    }

    background.add_task(
        _fetch_profile_async,
        req.username,
        min(req.max_posts, 100),  # hard cap
        req.download_media,
        job_id
    )

    return DownloadResponse(
        job_id=job_id,
        username=req.username,
        status="queued",
        total_posts=0
    )


@app.get("/status/{job_id}", response_model=DownloadResponse)
async def get_status(job_id: str):
    """Poll job status."""
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    return DownloadResponse(
        job_id=job["job_id"],
        username=job["username"],
        status=job["status"],
        total_posts=job.get("total_posts", 0),
        media=[MediaItem(**m) for m in job.get("media", [])],
        local_files=job.get("local_files", []),
        error=job.get("error")
    )


@app.get("/download/file/{job_id}/{filename}")
async def get_file(job_id: str, filename: str):
    """Serve a downloaded file."""
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found")

    for path_str in job.get("local_files", []):
        p = Path(path_str)
        if p.name == filename:
            return FileResponse(p, filename=filename)

    raise HTTPException(404, "File not found in this job")


@app.get("/health")
async def health():
    return {"status": "ok", "service": "ig-public-downloader"}
