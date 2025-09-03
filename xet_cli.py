import argparse
import os
import re
from typing import Optional

from xet_core import XetCore


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Unified CLI for Xiaoet (login/capture/download)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    # login + capture
    p_cap = sub.add_parser("capture", help="Open page, login via QR, capture audio URL")
    p_cap.add_argument("appid", type=str, help="Shop ID, e.g., appxxxx")
    p_cap.add_argument("resource_url", type=str, help="Audio/video page URL")
    p_cap.add_argument("--resource-id", type=str, default=None, help="Optional resource id")
    p_cap.add_argument("--wait", type=int, default=180, help="Max seconds to wait")

    # download from capture
    p_dl = sub.add_parser("download", help="Download using captured json")
    p_dl.add_argument("appid", type=str, help="Shop ID, e.g., appxxxx")
    p_dl.add_argument("capture", type=str, help="Path to captured JSON file")
    p_dl.add_argument("--title", type=str, default=None, help="Optional output file title")

    # quick: open URL -> capture -> download
    p_quick = sub.add_parser("quick", help="Capture then download in one go")
    p_quick.add_argument("appid", type=str, help="Shop ID, e.g., appxxxx")
    p_quick.add_argument("resource_url", type=str, help="Audio/video page URL")
    p_quick.add_argument("--resource-id", type=str, default=None, help="Optional resource id")
    p_quick.add_argument("--wait", type=int, default=180, help="Max seconds to wait")

    # quick by product id + resource id
    p_qr = sub.add_parser("quick-resource", help="Capture+download by product_id and resource_id")
    p_qr.add_argument("appid", type=str)
    p_qr.add_argument("product_id", type=str)
    p_qr.add_argument("resource_id", type=str)
    p_qr.add_argument("--wait", type=int, default=180)

    # list products
    p_lp = sub.add_parser("list-products", help="Capture product list (entry_url defaults to https://{appid}.xet.citv.cn)")
    p_lp.add_argument("appid", type=str, help="Shop ID")
    p_lp.add_argument("entry_url", nargs='?', default=None, type=str, help="Shop entry URL (optional)")
    p_lp.add_argument("--wait", type=int, default=120)
    p_lp.add_argument("--show-browser", action="store_true", help="Show browser window while capturing")

    # list resources under product
    p_lr = sub.add_parser("list-resources", help="Capture resources under a product (product_url optional if product_id provided)")
    p_lr.add_argument("appid", type=str, help="Shop ID")
    p_lr.add_argument("product_url", nargs='?', default=None, type=str, help="Product page URL (optional)")
    p_lr.add_argument("--product-id", type=str, default=None, help="Product ID (required if product_url omitted)")
    p_lr.add_argument("--wait", type=int, default=120)
    p_lr.add_argument("--show-browser", action="store_true", help="Show browser window while capturing")

    return parser.parse_args()


def cmd_capture(appid: str, resource_url: str, resource_id: Optional[str], wait: int) -> None:
    core = XetCore(appid)
    path = core.login_and_capture(resource_url, resource_id, wait)
    print(f"Capture saved to: {path}")


def cmd_download(appid: str, capture: str, title: Optional[str]) -> None:
    core = XetCore(appid)
    outfile = core.download_from_capture(capture, title)
    print(f"Downloaded: {outfile}")


def cmd_quick(appid: str, resource_url: str, resource_id: Optional[str], wait: int) -> None:
    core = XetCore(appid)
    cap = core.login_and_capture(resource_url, resource_id, wait)
    out = core.download_from_capture(cap)
    print(f"Downloaded: {out}")


def cmd_quick_resource(appid: str, product_id: str, resource_id: str, wait: int) -> None:
    core = XetCore(appid)
    url = XetCore.build_resource_page_url(appid, resource_id, product_id)
    cap = core.login_and_capture(url, resource_id, wait)
    out = core.download_from_capture(cap)
    print(f"Downloaded: {out}")


def main() -> None:
    # args = parse_args()
    # 调试代码：硬编码参数（按需启用其中一个预设）
    # 预设A：list-products（抓取专栏列表）
    # args = argparse.Namespace(
    #     cmd="list-products",
    #     appid="app8ydmwl262114",
    #     entry_url="https://app8ydmwl262114.xet.citv.cn",
    #     wait=120,
    #     show_browser=True,
    # )
    # 预设B：list-resources（抓取某专栏资源列表）
    # args = argparse.Namespace(
    #     cmd="list-resources",
    #     appid="app8ydmwl262114",
    #     product_url="https://app8ydmwl262114.xet.citv.cn/p/column/details?p_59e9fbdfbb63e_ttHpBdbE",
    #     product_id="p_59e9fbdfbb63e_ttHpBdbE",
    #     wait=120,
    #     show_browser=True,
    # )
    # 预设C：quick-resource（通过 product_id + resource_id 直接打开页面并下载）
    args = argparse.Namespace(
        cmd="quick-resource",
        appid="app8ydmwl262114",
        product_id="p_59e9fbdfbb63e_ttHpBdbE",
        resource_id="a_68b3f491e4b0694ca10c26e9",
        wait=100,
    )
    
    if args.cmd == "capture":
        cmd_capture(args.appid, args.resource_url, args.resource_id, args.wait)
    elif args.cmd == "download":
        cmd_download(args.appid, args.capture, args.title)
    elif args.cmd == "quick":
        cmd_quick(args.appid, args.resource_url, args.resource_id, args.wait)
    elif args.cmd == "list-products":
        core = XetCore(args.appid)
        entry_url = args.entry_url or f"https://{args.appid}.xet.citv.cn"
        items = core.capture_products(entry_url, args.wait, headless=(not args.show_browser))
        outfile = os.path.join(core.capture_dir, "products.json")
        print(f"Saved to: {outfile} ({len(items)} items)")
        for it in items:
            print(f"{it.get('id')}\t{it.get('title')}")
    elif args.cmd == "list-resources":
        core = XetCore(args.appid)
        product_url = args.product_url
        if not product_url:
            if not args.product_id:
                raise SystemExit("Either product_url or --product-id must be provided")
            product_url = f"https://{args.appid}.xet.citv.cn/p/column/details?{args.product_id}"
        items = core.capture_resources(product_url, args.product_id, args.wait, headless=(not args.show_browser))
        pid = args.product_id
        if not pid:
            m = re.search(r"product_id=([pA-Za-z0-9_]+)", product_url)
            if m:
                pid = m.group(1)
        key = pid or "unknown_product"
        outfile = os.path.join(core.capture_dir, f"{key}_resources.json")
        print(f"Saved to: {outfile} ({len(items)} items)")
        for it in items:
            print(f"{it.get('id')}\t{it.get('title')}")
    elif args.cmd == "quick-resource":
        cmd_quick_resource(args.appid, args.product_id, args.resource_id, args.wait)


if __name__ == "__main__":
    main()


