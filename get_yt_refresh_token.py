# get_yt_refresh_token.py
"""
Run this locally (not on GitHub Actions) to obtain a refresh token for your Google account.
Steps:
1. Create OAuth 2.0 Client ID (Desktop app) in Google Cloud Console for YouTube Data API v3.
2. Download the client_secrets.json (or copy client_id and client_secret).
3. Run: python get_yt_refresh_token.py
4. It will prompt to open a URL — complete the flow and paste the code.
5. Copy the printed refresh_token and add to GitHub Secrets as YT_REFRESH_TOKEN.
"""
import json
import os
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

def main():
    # expects client_secrets.json in current dir (format Google provides)
    if not os.path.exists("client_secrets.json"):
        print("Place your client_secrets.json (OAuth client credentials) here.")
        return
    flow = InstalledAppFlow.from_client_secrets_file("client_secrets.json", SCOPES)
    creds = flow.run_console()
    # creds will contain token, refresh_token, client_id/secret
    info = {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": creds.scopes
    }
    print("=== Save these values as GitHub Secrets ===")
    print("YT_REFRESH_TOKEN =", creds.refresh_token)
    print("YT_CLIENT_ID =", creds.client_id)
    print("YT_CLIENT_SECRET =", creds.client_secret)
    # optionally save to a local file
    with open("yt_token_info.json", "w") as f:
        json.dump(info, f, indent=2)
    print("Saved yt_token_info.json locally.")

if __name__ == "__main__":
    main()
