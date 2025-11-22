# uploader.py
import os
import sys
import json
import time
import pickle
import shutil
import pathlib
from pathlib import Path
from dotenv import load_dotenv

import instaloader
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
import requests

from seo_utils import generate_seo_from_caption

load_dotenv()

# Config (read from env / GitHub secrets)
INSTAGRAM_USERNAME = os.getenv("INSTAGRAM_USERNAME")
INSTAGRAM_PASSWORD = os.getenv("INSTAGRAM_PASSWORD")
YT_CLIENT_ID = os.getenv("YT_CLIENT_ID")
YT_CLIENT_SECRET = os.getenv("YT_CLIENT_SECRET")
YT_REFRESH_TOKEN = os.getenv("YT_REFRESH_TOKEN")

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
INDEX_FILE = "index.json"
SOURCES_FILE = "sources.json"
DOWNLOAD_FOLDER = "downloads"
LOG_FILE = "upload_log.txt"

# Helper: refresh Google credentials from refresh token
def get_youtube_service():
    if not (YT_CLIENT_ID and YT_CLIENT_SECRET and YT_REFRESH_TOKEN):
        raise RuntimeError("YouTube client ID/secret/refresh token not set in env.")
    creds = Credentials(
        token=None,
        refresh_token=YT_REFRESH_TOKEN,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=YT_CLIENT_ID,
        client_secret=YT_CLIENT_SECRET,
        scopes=SCOPES
    )
    # refresh to get access token
    creds.refresh(Request())
    youtube = build("youtube", "v3", credentials=creds)
    return youtube

def download_instagram_post(shortcode: str, target_folder=DOWNLOAD_FOLDER):
    if not INSTAGRAM_USERNAME or not INSTAGRAM_PASSWORD:
        raise RuntimeError("Set INSTAGRAM_USERNAME and INSTAGRAM_PASSWORD.")
    L = instaloader.Instaloader(dirname_pattern=target_folder, download_video_thumbnails=False, save_metadata=False)
    # attempt to load saved session to avoid login every time
    session_file = Path(f"{INSTAGRAM_USERNAME}_session")
    try:
        L.login(INSTAGRAM_USERNAME, INSTAGRAM_PASSWORD)
    except Exception as e:
        # If login fails, try without login (public posts only)
        print("Warning: Instagram login failed — trying without login (public posts only). Error:", e)
    Post = instaloader.Post
    try:
        post = Post.from_shortcode(L.context, shortcode)
    except Exception as e:
        raise RuntimeError(f"Could not fetch post {shortcode}: {e}")
    if not post.is_video:
        raise RuntimeError("Post is not a video. Only videos supported.")
    L.download_post(post, target=post.owner_username)
    downloaded_dir = Path(target_folder) / post.owner_username
    video_file = None
    for p in downloaded_dir.glob("**/*.mp4"):
        if shortcode in p.name:
            video_file = p
            break
    if not video_file:
        mp4s = list(downloaded_dir.glob("**/*.mp4"))
        if mp4s:
            video_file = mp4s[0]
    if not video_file:
        raise RuntimeError("Downloaded but couldn't find video file for post.")
    caption_text = post.caption or ""
    return str(video_file), caption_text

def upload_video(youtube, file_path, title, description, tags=None, privacyStatus="public"):
    media = MediaFileUpload(file_path, chunksize=-1, resumable=True)
    request_body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags or []
        },
        "status": {
            "privacyStatus": privacyStatus
        }
    }
    request = youtube.videos().insert(part="snippet,status", body=request_body, media_body=media)
    response = None
    print("Uploading:", file_path)
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"Upload progress: {int(status.progress() * 100)}%")
    return response

# Manage queue
def load_sources():
    with open(SOURCES_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def load_index():
    if not os.path.exists(INDEX_FILE):
        with open(INDEX_FILE, "w") as f:
            json.dump({"next_index": 0}, f)
        return {"next_index": 0}
    with open(INDEX_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_index(idx):
    with open(INDEX_FILE, "w", encoding="utf-8") as f:
        json.dump(idx, f, indent=2)

# Logging helper
def log(msg):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}\n"
    print(line, end="")
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line)

# Commit index back to repo (so the queue advances)
def git_commit_and_push(commit_message):
    # Attempt to commit and push using GITHUB_TOKEN/persisted credentials in Actions
    try:
        os.system("git config user.name 'github-actions[bot]'")
        os.system("git config user.email 'github-actions[bot]@users.noreply.github.com'")
        os.system("git add index.json upload_log.txt")
        # check if anything to commit
        status = os.system("git diff --cached --quiet || git commit -m \"%s\"" % commit_message)
        os.system("git push")
        log("Pushed index update to repo.")
    except Exception as e:
        log(f"Git commit/push failed: {e}")

def run_one_upload():
    sources = load_sources()
    idx = load_index()
    next_i = idx.get("next_index", 0)
    if next_i >= len(sources):
        log("No more items in sources.json (next_index >= len(sources)). Resetting to 0.")
        next_i = 0
    item = sources[next_i]
    shortcode = item.get("shortcode")
    try:
        video_path, caption = download_instagram_post(shortcode)
    except Exception as e:
        log(f"Download failed for {shortcode}: {e}")
        # advance index anyway to avoid getting stuck? — decision: advance to next
        idx["next_index"] = (next_i + 1) % len(sources)
        save_index(idx)
        git_commit_and_push(f"Advance index after failed download for {shortcode}")
        return False

    title, description, tags = generate_seo_from_caption(caption)
    try:
        youtube = get_youtube_service()
    except Exception as e:
        log(f"YouTube auth failed: {e}")
        return False

    try:
        resp = upload_video(youtube, video_path, title, description, tags)
        video_id = resp.get("id")
        log(f"Uploaded {video_path} as https://youtu.be/{video_id}")
    except Exception as e:
        log(f"Upload failed for {video_path}: {e}")
        return False

    # Move uploaded file to uploads/ folder for record
    uploads_folder = Path("uploaded_videos")
    uploads_folder.mkdir(exist_ok=True)
    dest = uploads_folder / Path(video_path).name
    shutil.move(video_path, dest)
    log(f"Moved uploaded file to {dest}")

    # Advance index and commit
    idx["next_index"] = (next_i + 1) % len(sources)
    save_index(idx)
    git_commit_and_push(f"Advance index after uploading {shortcode}")
    return True

def main():
    # number of uploads to do this run (for GitHub Actions the workflow triggers twice/day and we upload 1 each run)
    count = int(os.getenv("UPLOAD_COUNT", "1"))
    for i in range(count):
        success = run_one_upload()
        time.sleep(5)

if __name__ == "__main__":
    main()
