# seo_utils.py
import re

def sanitize_text(s: str, max_len=100):
    if not s:
        return ""
    s = s.strip()
    s = re.sub(r'\s+', ' ', s)
    if len(s) > max_len:
        s = s[:max_len].rsplit(' ', 1)[0]
    return s

def generate_seo_from_caption(caption: str):
    if not caption:
        caption = ""
    title = caption.splitlines()[0] if caption.splitlines() else caption
    title = sanitize_text(title, max_len=70)
    if not title:
        title = "Short video"

    description = caption.strip()
    if description:
        description += "\n\n"
    description += "Uploaded automatically. Credit to original creator if not you.\n"
    description += "Like & subscribe."

    words = re.findall(r"[A-Za-z0-9]+", caption.lower())
    stopwords = set([
        "the","and","a","to","in","of","for","on","is","with","this","that","it",
        "you","from","are","as","be","at","by","an","or","have","was","but","not"
    ])
    tags = []
    for w in words:
        if len(w) < 3: continue
        if w.isdigit(): continue
        if w in stopwords: continue
        if w not in tags:
            tags.append(w)
        if len(tags) >= 15:
            break

    return title, description, tags
