# Instagram → YouTube auto-uploader (2 shorts/day)

**IMPORTANT:** Only upload videos you own or have permission to repost.

## What this repo does
- Downloads an Instagram video from a queue and uploads it to YouTube with the caption-derived title/description/tags.
- Runs twice daily via GitHub Actions (one upload per run, so 2 uploads/day total).
- Advances through a `sources.json` queue and keeps state in `index.json`.

## Setup (one-time)
1. Create a Google Cloud project and enable **YouTube Data API v3**.
2. Create **OAuth 2.0 Client ID** (Desktop app). Download `client_secrets.json`.
3. On your local machine run:
   ```bash
   pip install -r requirements.txt
   python get_yt_refresh_token.py
