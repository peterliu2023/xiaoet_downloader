import argparse
import json
import os
import re
import time
from typing import Dict, List, Optional

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError


class XetPlaywright:
    def __init__(self, appid: str, storage_root: str = "playwright_data") -> None:
        self.appid = appid
        self.storage_dir = os.path.join(storage_root, appid)
        self.captured_dir = os.path.join("captured", appid)
        os.makedirs(self.storage_dir, exist_ok=True)
        os.makedirs(self.captured_dir, exist_ok=True)

    def _build_default_headers(self, page_url: str, cookie_header: str) -> Dict[str, str]:
        return {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/127.0.0.0 Safari/537.36"
            ),
            "Accept": "*/*",
            "Referer": page_url,
            "Origin": re.sub(r"^(https?://[^/]+).*$", r"\\1", page_url),
            "Cookie": cookie_header,
        }

    def _cookie_header_for_domain(self, cookies: List[Dict], domain: str) -> str:
        pairs: List[str] = []
        for c in cookies:
            # Domain match: include host-only and parent-domain cookies
            if c.get("domain") and (c["domain"].lstrip(".") in domain or domain.endswith(c["domain"].lstrip("."))):
                pairs.append(f"{c['name']}={c['value']}")
        return "; ".join(pairs)

    def login_and_capture(self, resource_url: str, resource_id: Optional[str], wait_seconds: int = 300) -> str:
        with sync_playwright() as p:
            # Use persistent context to retain login state across runs
            context = p.chromium.launch_persistent_context(self.storage_dir, headless=False, args=["--disable-dev-shm-usage"])  # noqa: E501
            page = context.new_page()

            candidates: List[Dict] = []

            def on_response(resp):
                try:
                    url = resp.url
                    ct = resp.headers.get("content-type", "").lower()
                    is_audio_ct = ct.startswith("audio/") or "mpegurl" in ct or "m3u8" in ct
                    is_audio_ext = any(s in url for s in [".m3u8", ".mp3", ".m4a", ".aac", ".flac"])  # heuristic
                    if not (is_audio_ct or is_audio_ext):
                        # Try JSON payload pattern
                        if "application/json" in ct:
                            try:
                                data = resp.json()
                                # Common key patterns observed historically
                                for key in [
                                    "audio_url",
                                    "audioUrl",
                                    "play_url",
                                    "playUrl",
                                    "hls_url",
                                    "hlsUrl",
                                ]:
                                    if isinstance(data, dict) and key in data and isinstance(data[key], str):
                                        candidates.append({"type": "json_key", "from": url, "url": data[key]})
                                        return
                            except Exception:
                                pass
                        return

                    # If content-type suggests audio or extension matches, accept as candidate
                    candidates.append({"type": "response", "from": url, "url": url})
                except Exception:
                    return

            page.on("response", on_response)

            # Navigate and wait for possible login
            try:
                page.goto(resource_url, wait_until="domcontentloaded", timeout=60000)
            except PlaywrightTimeoutError:
                pass

            # Heuristic: wait until either user logs in and page settles, or timeout
            start = time.time()
            last_count = 0
            while time.time() - start < wait_seconds:
                time.sleep(2)
                # If we are receiving new candidates, extend waiting a bit
                if len(candidates) != last_count:
                    last_count = len(candidates)
                    continue
                # Also periodically trigger small interactions to keep network active
                try:
                    # Try to scroll a bit to trigger lazy network activity
                    page.mouse.wheel(0, 800)
                except Exception:
                    pass

                # If already have some candidates and they've stabilized for a short period, break
                if last_count > 0 and time.time() - start > 8:
                    break

            # Collect cookies and build a cookie header for the target domain
            cookies = context.cookies()
            domain = re.sub(r"^https?://([^/]+).*$", r"\1", resource_url)
            cookie_header = self._cookie_header_for_domain(cookies, domain)
            headers = self._build_default_headers(resource_url, cookie_header)

            # Deduplicate candidates while preserving order
            seen: set = set()
            unique_candidates: List[Dict] = []
            for c in candidates:
                u = c.get("url")
                if u and u not in seen:
                    seen.add(u)
                    unique_candidates.append(c)

            # Persist capture
            rid = resource_id or re.sub(r"^.*?/([av]_\w+).*?$", r"\1", resource_url)
            outfile = os.path.join(self.captured_dir, f"{rid or 'unknown_resource'}.json")
            payload = {
                "appid": self.appid,
                "resource_id": rid,
                "page_url": resource_url,
                "headers": headers,
                "cookies": cookies,
                "candidates": unique_candidates,
                "captured_at": int(time.time()),
            }
            with open(outfile, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)

            # Also mirror to legacy config.json cookie store to facilitate requests-based flows
            try:
                config_path = os.path.join(os.getcwd(), "config.json")
                existing = {}
                if os.path.exists(config_path):
                    with open(config_path, "r", encoding="utf-8") as cf:
                        try:
                            existing = json.load(cf) or {}
                        except Exception:
                            existing = {}
                existing["last_appid"] = self.appid
                existing["cookies_time"] = int(time.time())
                # Flatten cookies into a simple dict for convenience
                cookie_dict = {c["name"]: c["value"] for c in cookies}
                existing["cookies"] = cookie_dict
                with open(config_path, "w", encoding="utf-8") as cf:
                    json.dump(existing, cf, ensure_ascii=False, indent=2)
            except Exception:
                pass

            # Keep browser open briefly for user visibility, then close
            time.sleep(1)
            try:
                context.close()
            except Exception:
                pass

            return outfile


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Xiaoet Playwright login and audio capture")
    parser.add_argument("appid", type=str, help="Shop ID of xiaoe-tech (e.g., appxxxx)")
    parser.add_argument("--resource-url", type=str, required=True, help="Full page URL of the audio/video resource")
    parser.add_argument("--resource-id", type=str, default=None, help="Optional resource id (a_xxx or v_xxx)")
    parser.add_argument("--wait", type=int, default=300, help="Max seconds to wait for capture")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    runner = XetPlaywright(args.appid)
    outfile = runner.login_and_capture(args.resource_url, args.resource_id, args.wait)
    print(f"Capture saved to: {outfile}")


if __name__ == "__main__":
    main()


