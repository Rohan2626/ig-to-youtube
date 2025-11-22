# uploader.py
"""
Main automation script:

- Reads state.json to know which post index to upload next.
- Fetches all video posts from TARGET_IG_USERNAME (@jenjenivive by default).
- Downloads the selected post's video and caption.
- Generates YouTube title/description/tags from caption.
- Uploads the video to YouTube as a Short (if vertical + <60s).
- Moves the uploaded file to uploaded_videos/.
- Updates state.json so next run uploads the next post.
"""

from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path
from typing import List

from dotenv import load_dotenv
import instaloader

from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

from seo_utils import generate_seo_from_caption

# Load .env if present (not required on GitHub Actions, but handy locally)
load_dotenv()

# --- Configuration via environment variables ---

# This is the public account we’re downloading from:
TARGET_IG_USERNAME: str = os.getenv("TARGET_IG_USERNAME", "jenjenivive")

# Optional login (NOT required for public accounts):
INSTAGRAM_LOGIN_USERNAME: str | None = os.getenv("INSTAGRAM_LOGIN_USERNAME")
INSTAGRAM_LOGIN_PASSWORD: str | None = os.getenv("INSTAGRAM_LOGIN_PASSWORD")

# YouTube OAuth credentials (from get_yt_refresh_token.py):
YT_CLIENT_ID: str | None = os.getenv("YT_CLIENT_ID")
YT_CLIENT_SECRET: str | None = os.getenv("YT_CLIENT_SECRET")
YT_REFRESH_TOKEN: str | None = os.getenv("YT_REFRESH_TOKEN")

# Misc:
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
STATE_FILE = "state.json"
DOWNLOAD_FOLDER = "downloads"
UPLOADED_FOLDER = "uploaded_videos"
LOG_FILE = "upload_log.txt"


# --- Utilities ---


def log(message: str) -> None:
    """Log to stdout and append to upload_log.txt."""
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {message}\n"
    print(line, end="")
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line)


def load_state() -> dict:
    """Load or initialize state.json."""
    if not os.path.exists(STATE_FILE):
        state = {"next_index": 0}
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
        return state

    with open(STATE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_state(state: dict) -> None:
    """Save state.json."""
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


def get_youtube_service():
    """Create a YouTube API client using a refresh token."""
    if not (YT_CLIENT_ID and YT_CLIENT_SECRET and YT_REFRESH_TOKEN):
        raise RuntimeError(
            "YouTube credentials missing. Set YT_CLIENT_ID, YT_CLIENT_SECRET, "
            "and YT_REFRESH_TOKEN as environment variables."
        )

    creds = Credentials(
        token=None,
        refresh_token=YT_REFRESH_TOKEN,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=YT_CLIENT_ID,
        client_secret=YT_CLIENT_SECRET,
        scopes=SCOPES,
    )
    creds.refresh(Request())
    return build("youtube", "v3", credentials=creds)


def get_instaloader() -> instaloader.Instaloader:
    """
    Create an Instaloader instance.
    - If INSTAGRAM_LOGIN_* are provided, attempt login.
    - Otherwise, use guest mode (fine for public accounts like @jenjenivive).
    """
    loader = instaloader.Instaloader(
        dirname_pattern=DOWNLOAD_FOLDER,
        download_video_thumbnails=False,
        save_metadata=False,
        post_metadata_txt_pattern="",
    )

    if INSTAGRAM_LOGIN_USERNAME and INSTAGRAM_LOGIN_PASSWORD:
        try:
            loader.login(INSTAGRAM_LOGIN_USERNAME, INSTAGRAM_LOGIN_PASSWORD)
            log(f"Logged in to Instagram as @{INSTAGRAM_LOGIN_USERNAME}")
        except Exception as e:
            log(f"Instagram login failed, continuing as guest: {e}")
    else:
        log("No Instagram login provided. Using guest mode (public posts only).")

    return loader


def get_all_video_posts(
    loader: instaloader.Instaloader, username: str
) -> List[instaloader.Post]:
    """Return all video posts from the given profile, sorted oldest → newest."""
    profile = instaloader.Profile.from_username(loader.context, username)
    posts = [p for p in profile.get_posts() if p.is_video]
    posts_sorted = sorted(posts, key=lambda p: p.date_utc)
    log(f"Found {len(posts_sorted)} video posts for @{username}.")
    return posts_sorted


def download_post_video(
    loader: instaloader.Instaloader, post: instaloader.Post
) -> tuple[str, str]:
    """
    Download the Instagram post video and return (video_path, caption).
    """
    loader.download_post(post, target=post.owner_username)
    downloaded_dir = Path(DOWNLOAD_FOLDER) / post.owner_username

    shortcode = post.shortcode
    video_path: Path | None = None

    # Find an mp4 file that contains the shortcode in the filename.
    for candidate in downloaded_dir.glob("**/*.mp4"):
        if shortcode in candidate.name:
            video_path = candidate
            break

    # Fallback: if not found, just take the first mp4.
    if video_path is None:
        mp4_files = list(downloaded_dir.glob("**/*.mp4"))
        if mp4_files:
            video_path = mp4_files[0]

    if video_path is None:
        raise RuntimeError("Could not find downloaded video file.")

    caption = post.caption or ""
    return str(video_path), caption


def upload_video_to_youtube(
    youtube,
    file_path: str,
    title: str,
    description: str,
    tags: list[str] | None = None,
    privacy_status: str = "public",
) -> str:
    """
    Upload a video file to YouTube and return the video ID.
    """
    media = MediaFileUpload(file_path, chunksize=-1, resumable=True)
    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags or [],
        },
        "status": {
            "privacyStatus": privacy_status,
        },
    }

    request = youtube.videos().insert(
        part="snippet,status", body=body, media_body=media
    )

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            log(f"Upload progress: {int(status.progress() * 100)}%")

    video_id = response.get("id")
    log(f"Uploaded video: https://youtu.be/{video_id}")
    return video_id


def run_one_upload() -> bool:
    """
    Perform a single upload:
      - pick next post
      - download
      - SEO
      - upload
      - update state
    """
    log("=== New upload run started ===")

    loader = get_instaloader()
    posts = get_all_video_posts(loader, TARGET_IG_USERNAME)
    if not posts:
        log("No video posts found. Exiting.")
        return False

    state = load_state()
    index = int(state.get("next_index", 0)) % len(posts)

    post = posts[index]
    shortcode = post.shortcode
    log(f"Selected post index={index}, shortcode={shortcode}")

    # Download video
    try:
        video_path, caption = download_post_video(loader, post)
        log(f"Downloaded video to {video_path}")
    except Exception as exc:
        log(f"Error downloading post {shortcode}: {exc}")
        # Skip this one to avoid being stuck
        state["next_index"] = (index + 1) % len(posts)
        save_state(state)
        log("Advanced index after failed download.")
        return False

    # Prepare SEO
    title, description, tags = generate_seo_from_caption(caption)
    log(f"Generated title: {title}")
    log(f"Generated tags: {tags}")

    # Upload to YouTube
    try:
        youtube = get_youtube_service()
    except Exception as exc:
        log(f"YouTube auth failed: {exc}")
        return False

    try:
        video_id = upload_video_to_youtube(
            youtube, video_path, title, description, tags
        )
    except Exception as exc:
        log(f"Upload failed: {exc}")
        return False

    # Move uploaded file to archive folder
    Path(UPLOADED_FOLDER).mkdir(exist_ok=True)
    dest = Path(UPLOADED_FOLDER) / Path(video_path).name
    shutil.move(video_path, dest)
    log(f"Moved uploaded file to {dest}")

    # Advance index
    state["next_index"] = (index + 1) % len(posts)
    save_state(state)
    log(f"Updated state.next_index → {state['next_index']}")

    log("=== Upload run completed successfully ===")
    return True


def main() -> None:
    """
    Entry point. UPLOAD_COUNT controls how many uploads per run.
    In GitHub Actions we run this job twice per day, with UPLOAD_COUNT=1.
    """
    uploads_to_do = int(os.getenv("UPLOAD_COUNT", "1"))
    for _ in range(uploads_to_do):
        run_one_upload()
        time.sleep(5)


if __name__ == "__main__":
    main()
