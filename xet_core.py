import json
import os
import re
import time
from typing import Any, Dict, List, Optional

from playwright.sync_api import sync_playwright
import requests


class XetCore:
    def __init__(self, appid: str) -> None:
        self.appid = appid
        self.playwright_storage = os.path.join("playwright_data", appid)
        self.capture_dir = os.path.join("captured", appid)
        self.download_dir = "download"
        os.makedirs(self.playwright_storage, exist_ok=True)
        os.makedirs(self.capture_dir, exist_ok=True)
        os.makedirs(self.download_dir, exist_ok=True)

    @staticmethod
    def _walk_collect_entities(node: Any, id_prefixes: List[str]) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        try:
            if isinstance(node, dict):
                # If dict itself represents an entity
                possible_keys = ["id", "resource_id", "spu_id", "src_id", "rid"]
                _id = None
                for k in possible_keys:
                    v = node.get(k)
                    if isinstance(v, str) and any(v.startswith(p) for p in id_prefixes):
                        _id = v
                        break
                if _id:
                    title = (
                        node.get("title")
                        or node.get("product_name")
                        or node.get("name")
                        or node.get("resource_title")
                        or node.get("course_title")
                    )
                    results.append({"id": _id, "title": title, "raw": node})
                # Recurse values
                for v in node.values():
                    results.extend(XetCore._walk_collect_entities(v, id_prefixes))
            elif isinstance(node, list):
                for it in node:
                    results.extend(XetCore._walk_collect_entities(it, id_prefixes))
        except Exception:
            pass
        return results

    @staticmethod
    def _unique_by_id(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        best: Dict[str, Dict[str, Any]] = {}
        for it in items:
            _id = it.get("id")
            if not _id:
                continue
            cur = best.get(_id)
            if cur is None:
                best[_id] = it
                continue
            cur_title = cur.get("title")
            new_title = it.get("title")
            # Prefer the one with a non-empty title, or longer title text
            def _len(x: Optional[str]) -> int:
                return len(x) if isinstance(x, str) else 0
            if (not cur_title and new_title) or (_len(new_title) > _len(cur_title)):
                best[_id] = it
        return list(best.values())

    def _cookie_header_for_domain(self, cookies: List[Dict], domain: str) -> str:
        pairs: List[str] = []
        for c in cookies:
            if c.get("domain") and (c["domain"].lstrip(".") in domain or domain.endswith(c["domain"].lstrip("."))):
                pairs.append(f"{c['name']}={c['value']}")
        return "; ".join(pairs)

    def login_and_capture(self, resource_url: str, resource_id: Optional[str] = None, wait_seconds: int = 120) -> str:
        with sync_playwright() as p:
            context = p.chromium.launch_persistent_context(self.playwright_storage, headless=False)
            page = context.new_page()
            candidates: List[Dict[str, Any]] = []

            def on_response(resp):
                try:
                    url = resp.url
                    ct = resp.headers.get("content-type", "").lower()
                    if any(x in url for x in [".m3u8", ".mp3", ".m4a", ".aac", ".flac"]) or "audio/" in ct or "mpegurl" in ct or "m3u8" in ct:  # noqa: E501
                        candidates.append({"type": "response", "from": url, "url": url})
                    elif "application/json" in ct:
                        try:
                            data = resp.json()
                            for key in ["audio_url", "audioUrl", "play_url", "playUrl", "hls_url", "hlsUrl"]:
                                if isinstance(data, dict) and key in data and isinstance(data[key], str):
                                    candidates.append({"type": "json_key", "from": url, "url": data[key]})
                                    break
                        except Exception:
                            pass
                except Exception:
                    pass

            page.on("response", on_response)
            try:
                page.goto(resource_url, wait_until="domcontentloaded", timeout=60000)
            except Exception:
                pass

            # Try to trigger media playback/network by simulating user gestures
            try:
                page.wait_for_timeout(800)
                # Attempt clicking common play buttons
                selectors = [
                    "button:has-text('播放')",
                    "[aria-label='播放']",
                    ".play",
                    ".player-play",
                    "button",
                ]
                for sel in selectors:
                    try:
                        loc = page.locator(sel)
                        if loc.count() > 0:
                            loc.first.click(timeout=1000)
                            page.wait_for_timeout(300)
                            break
                    except Exception:
                        continue
                # Directly call HTMLMediaElement.play() on first audio/video
                try:
                    page.evaluate(
                        """
                        () => {
                          const media = document.querySelector('audio, video');
                          if (media) {
                            media.muted = false;
                            const p = media.play();
                            if (p && p.catch) p.catch(() => {});
                          }
                        }
                        """
                    )
                except Exception:
                    pass
            except Exception:
                pass

            start = time.time()
            while time.time() - start < wait_seconds:
                time.sleep(2)
                if candidates:
                    break
                try:
                    page.mouse.wheel(0, 800)
                except Exception:
                    pass

            cookies = context.cookies()
            domain = re.sub(r"^https?://([^/]+).*$", r"\1", resource_url)
            cookie_header = self._cookie_header_for_domain(cookies, domain)
            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/127.0.0.0 Safari/537.36"
                ),
                "Accept": "*/*",
                "Referer": resource_url,
                "Origin": re.sub(r"^(https?://[^/]+).*$", r"\\1", resource_url),
                "Cookie": cookie_header,
            }

            rid = resource_id or re.sub(r"^.*?/([av]_\w+).*?$", r"\1", resource_url)
            outfile = os.path.join(self.capture_dir, f"{rid or 'unknown_resource'}.json")
            payload = {
                "appid": self.appid,
                "resource_id": rid,
                "page_url": resource_url,
                "headers": headers,
                "cookies": cookies,
                "candidates": candidates,
                "captured_at": int(time.time()),
            }
            with open(outfile, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            try:
                context.close()
            except Exception:
                pass
            return outfile

    @staticmethod
    def pick_best_candidate(candidates: List[Dict[str, Any]]) -> Optional[str]:
        if not candidates:
            return None
        priority = [".m3u8", ".m4a", ".mp3", ".aac", ".flac"]
        for ext in priority:
            for c in candidates:
                url = c.get("url")
                if isinstance(url, str) and ext in url:
                    return url
        return candidates[0].get("url")

    @staticmethod
    def sanitize_filename(name: str) -> str:
        safe = re.sub(r"[\\/:*?\"<>|]", "_", name).strip()
        return safe or "audio"

    def download_from_capture(self, capture_json_path: str, title: Optional[str] = None) -> Optional[str]:
        if not os.path.exists(capture_json_path):
            print(f"Capture file not found: {capture_json_path}")
            return None
        with open(capture_json_path, "r", encoding="utf-8") as f:
            payload = json.load(f)
        headers = {k: v for k, v in payload.get("headers", {}).items() if k in ["User-Agent", "Accept", "Referer", "Origin", "Cookie"]}  # noqa: E501
        url = self.pick_best_candidate(payload.get("candidates", []))
        if not url:
            print("No audio candidate found.")
            return None
        rid = payload.get("resource_id") or "audio"
        base_name = self.sanitize_filename(title or rid)
        suffix = url.split("?")[0].split("#")[0].split("/")[-1]
        ext = suffix.split(".")[-1] if "." in suffix else "mp3"
        outfile = os.path.join(self.download_dir, f"{base_name}.{ext}")
        with requests.get(url, headers=headers, stream=True) as r:
            r.raise_for_status()
            with open(outfile + ".tmp", "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
        os.replace(outfile + ".tmp", outfile)
        return outfile

    def capture_products(self, entry_url: str, wait_seconds: int = 120, headless: bool = True) -> List[Dict[str, Any]]:
        with sync_playwright() as p:
            context = p.chromium.launch_persistent_context(self.playwright_storage, headless=headless)
            page = context.new_page()
            products: List[Dict[str, Any]] = []

            def on_response(resp):
                try:
                    ct = resp.headers.get("content-type", "").lower()
                    if "application/json" in ct:
                        data = resp.json()
                        found = self._walk_collect_entities(data, ["p_"])
                        if found:
                            products.extend(found)
                except Exception:
                    pass

            page.on("response", on_response)
            try:
                page.goto(entry_url, wait_until="domcontentloaded", timeout=60000)
            except Exception:
                pass

            start = time.time()
            while time.time() - start < wait_seconds:
                time.sleep(2)
                if products:
                    break
                try:
                    page.mouse.wheel(0, 1000)
                except Exception:
                    pass

            products = self._unique_by_id(products)
            out = {
                "appid": self.appid,
                "entry_url": entry_url,
                "products": products,
                "captured_at": int(time.time()),
            }
            os.makedirs(self.capture_dir, exist_ok=True)
            outfile = os.path.join(self.capture_dir, "products.json")
            with open(outfile, "w", encoding="utf-8") as f:
                json.dump(out, f, ensure_ascii=False, indent=2)
            try:
                context.close()
            except Exception:
                pass
            return products

    def capture_resources(self, product_url: str, product_id: Optional[str] = None, wait_seconds: int = 120, headless: bool = True) -> List[Dict[str, Any]]:
        with sync_playwright() as p:
            context = p.chromium.launch_persistent_context(self.playwright_storage, headless=headless)
            page = context.new_page()
            resources: List[Dict[str, Any]] = []

            def on_response(resp):
                try:
                    ct = resp.headers.get("content-type", "").lower()
                    if "application/json" in ct:
                        data = resp.json()
                        found = self._walk_collect_entities(data, ["a_", "v_"])
                        if found:
                            resources.extend(found)
                except Exception:
                    pass

            page.on("response", on_response)
            try:
                page.goto(product_url, wait_until="domcontentloaded", timeout=60000)
            except Exception:
                pass

            start = time.time()
            while time.time() - start < wait_seconds:
                time.sleep(2)
                if resources:
                    break
                try:
                    page.mouse.wheel(0, 1200)
                except Exception:
                    pass

            resources = self._unique_by_id(resources)
            # try to infer product_id
            pid = product_id
            if not pid:
                m = re.search(r"product_id=([pA-Za-z0-9_]+)", product_url)
                if m:
                    pid = m.group(1)

            out = {
                "appid": self.appid,
                "product_id": pid,
                "product_url": product_url,
                "resources": resources,
                "captured_at": int(time.time()),
            }
            os.makedirs(self.capture_dir, exist_ok=True)
            key = pid or "unknown_product"
            outfile = os.path.join(self.capture_dir, f"{key}_resources.json")
            with open(outfile, "w", encoding="utf-8") as f:
                json.dump(out, f, ensure_ascii=False, indent=2)
            try:
                context.close()
            except Exception:
                pass
            return resources

    @staticmethod
    def build_resource_page_url(appid: str, resource_id: str, product_id: Optional[str] = None) -> str:
        kind = "audio" if resource_id.startswith("a_") else "video"
        base = f"https://{appid}.xet.citv.cn/p/course/{kind}/{resource_id}"
        if product_id:
            return base + f"?anonymous=2&product_id={product_id}"
        return base


