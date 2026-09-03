import hashlib
import re

def normalize_title(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()

def stable_item_id(source: str, title: str, url: str = "") -> str:
    base = f"{source}|{normalize_title(title)}|{url}".encode("utf-8")
    return hashlib.sha256(base).hexdigest()[:20]
