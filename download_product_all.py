import argparse
import os
import time
import random
from typing import List, Dict, Any

from xet_core import XetCore


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download all resources under a Xiaoet product")
    parser.add_argument("appid", type=str, help="Shop ID, e.g., appxxxx")
    parser.add_argument("product_id", type=str, help="Product/column ID, e.g., p_xxx")
    parser.add_argument("--wait-list", type=int, default=120, help="Seconds to wait for listing resources")
    parser.add_argument("--wait-capture", type=int, default=180, help="Seconds to wait for each capture")
    parser.add_argument("--max", type=int, default=-1, help="Limit number of resources to download (-1 for all)")
    parser.add_argument("--start", type=int, default=0, help="Start index in the resource list")
    parser.add_argument("--headless-list", action="store_true", help="Headless when listing resources")
    parser.add_argument("--sleep-min", type=float, default=2.0, help="Min seconds to sleep between downloads")
    parser.add_argument("--sleep-max", type=float, default=7.0, help="Max seconds to sleep between downloads")
    return parser.parse_args()


def build_product_url(appid: str, product_id: str) -> str:
    # Observed pattern: details?{product_id}
    return f"https://{appid}.xet.citv.cn/p/column/details?{product_id}"


def main() -> None:
    args = parse_args()
    core = XetCore(args.appid)

    # 1) list resources under the product
    product_url = build_product_url(args.appid, args.product_id)
    resources: List[Dict[str, Any]] = core.capture_resources(
        product_url=product_url,
        product_id=args.product_id,
        wait_seconds=args.wait_list,
        headless=args.headless_list,
    )
    print(f"Found {len(resources)} resources under {args.product_id}")

    # 2) iterate and download each resource by title
    start = max(0, args.start)
    end = len(resources) if args.max == -1 else min(len(resources), start + max(0, args.max))
    selected = resources[start:end]
    print(f"Downloading items [{start}:{end}) ...")

    for idx, item in enumerate(selected, start=start):
        rid = item.get("id")
        title = item.get("title") or rid
        if not isinstance(rid, str):
            print(f"Skip index {idx}: invalid resource id")
            continue
        # Skip if a file with the resource title already exists in download dir
        base_name = XetCore.sanitize_filename(title)
        try:
            existing_files = [fn for fn in os.listdir(core.download_dir) if fn.startswith(base_name + ".")]
        except FileNotFoundError:
            existing_files = []
        if existing_files:
            print(f"[{idx}] Skip: already exists -> {existing_files[0]}")
            continue
        try:
            resource_url = XetCore.build_resource_page_url(args.appid, rid, args.product_id)
            print(f"[{idx}] Capture: {rid} - {title}")
            cap = core.login_and_capture(resource_url, rid, wait_seconds=args.wait_capture)
            print(f"[{idx}] Download -> {title}")
            out = core.download_from_capture(cap, title=title)
            print(f"[{idx}] Done: {out}")
            # Randomized backoff between items to avoid rate limiting
            if idx < end - 1:
                lo = max(0.0, min(args.sleep_min, args.sleep_max))
                hi = max(args.sleep_min, args.sleep_max)
                delay = random.uniform(lo, hi)
                print(f"[{idx}] Sleeping {delay:.1f}s before next item...")
                time.sleep(delay)
        except Exception as e:
            print(f"[{idx}] Failed: {rid} - {e}")

    print("All done.")


if __name__ == "__main__":
    main()


