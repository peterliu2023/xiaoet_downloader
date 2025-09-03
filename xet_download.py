import argparse
import json
import os
import re
from typing import Any, Dict, List, Optional

import requests


def pick_best_candidate(candidates: List[Dict[str, Any]]) -> Optional[str]:
    if not candidates:
        return None
    # Priority: m3u8 > m4a/mp3 > others
    priority = [".m3u8", ".m4a", ".mp3", ".aac", ".flac"]
    for ext in priority:
        for c in candidates:
            url = c.get("url")
            if isinstance(url, str) and ext in url:
                return url
    # Fallback to first
    return candidates[0].get("url")


def build_requests_headers(headers: Dict[str, str]) -> Dict[str, str]:
    allow = ["User-Agent", "Accept", "Referer", "Origin", "Cookie"]
    return {k: v for k, v in headers.items() if k in allow}


def sanitize_filename(name: str) -> str:
    safe = re.sub(r"[\\/:*?\"<>|]", "_", name).strip()
    return safe or "audio"


def download_audio(capture_json_path: str, title: Optional[str] = None, out_dir: str = "download") -> Optional[str]:
    if not os.path.exists(capture_json_path):
        print(f"Capture file not found: {capture_json_path}")
        return None
    with open(capture_json_path, "r", encoding="utf-8") as f:
        payload = json.load(f)

    headers = build_requests_headers(payload.get("headers", {}))
    candidates = payload.get("candidates", [])
    url = pick_best_candidate(candidates)
    if not url:
        print("No audio candidate found in capture file.")
        return None

    # Infer title from resource_id if not provided
    rid = payload.get("resource_id") or "audio"
    base_name = sanitize_filename(title or rid)

    # Choose extension from URL
    suffix = url.split("?")[0].split("#")[0].split("/")[-1]
    if "." in suffix:
        ext = suffix.split(".")[-1]
    else:
        ext = "mp3"

    os.makedirs(out_dir, exist_ok=True)
    outfile = os.path.join(out_dir, f"{base_name}.{ext}")

    with requests.get(url, headers=headers, stream=True) as r:
        r.raise_for_status()
        with open(outfile + ".tmp", "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
    os.replace(outfile + ".tmp", outfile)
    print(f"Downloaded: {outfile}")
    return outfile


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download audio using captured data")
    parser.add_argument("capture", type=str, help="Path to captured JSON (from xet_playwright.py)")
    parser.add_argument("--title", type=str, default=None, help="Optional output title (filename)")
    parser.add_argument("--out", type=str, default="download", help="Output directory")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    download_audio(args.capture, args.title, args.out)


if __name__ == "__main__":
    main()


