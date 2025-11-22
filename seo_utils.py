# seo_utils.py
"""
Helpers for generating YouTube SEO (title, description, tags)
from an Instagram caption.
"""

from __future__ import annotations
import re
from typing import List, Tuple


def _sanitize_text(text: str, max_len: int = 100) -> str:
    """Trim whitespace, collapse spaces, and cut at a word boundary."""
    if not text:
        return ""
    text = text.strip()
    text = re.sub(r"\s+", " ", text)
    if len(text) > max_len:
        text = text[:max_len].rsplit(" ", 1)[0]
    return text


def generate_seo_from_caption(caption: str) -> Tuple[str, str, List[str]]:
    """
    Given the original Instagram caption, return:
      - title (max ~70 chars)
      - description
      - list of tags (max ~15)
    """
    if not caption:
        caption = ""

    # Title: first line or beginning of caption
    first_line = caption.splitlines()[0] if caption.splitlines() else caption
    title = _sanitize_text(first_line, max_len=70)
    if not title:
        title = "Short video"

    # Description: original caption + CTA
    description = caption.strip()
    if description:
        description += "\n\n"
    description += (
        "Reposted with permission from the creator.\n"
        "Like, comment & subscribe for more! ❤️"
    )

    # Tags: simple word-based extraction
    words = re.findall(r"[A-Za-z0-9]+", caption.lower())
    stopwords = {
        "the", "and", "a", "to", "in", "of", "for", "on", "is", "with",
        "this", "that", "it", "you", "from", "are", "as", "be", "at",
        "by", "an", "or", "have", "was", "but", "not",
    }

    tags: List[str] = []
    for w in words:
        if len(w) < 3:
            continue
        if w.isdigit():
            continue
        if w in stopwords:
            continue
        if w not in tags:
            tags.append(w)
        if len(tags) >= 15:
            break

    return title, description, tags
