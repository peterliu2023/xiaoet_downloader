import json
import os
from typing import Optional

import streamlit as st

from xet_core import XetCore


st.set_page_config(page_title="小鹅通拉取工具", page_icon="🐣", layout="wide")


def ui_header():
    st.title("小鹅通音视频拉取工具")
    st.caption("已购资源抓取与下载，扫码登录有效期4小时")


def ui_capture_section():
    st.subheader("扫码登录并抓取候选音频URL")
    appid = st.text_input("店铺ID(appxx)", value=st.session_state.get("appid", ""))
    resource_url = st.text_input("资源播放页URL", value=st.session_state.get("resource_url", ""))
    resource_id = st.text_input("资源ID(可选)", value=st.session_state.get("resource_id", ""))
    wait = st.number_input("等待秒数", min_value=30, max_value=600, value=180)
    if st.button("打开浏览器扫码并抓取"):
        if not appid or not resource_url:
            st.error("请填写店铺ID与资源页URL")
        else:
            st.session_state["appid"] = appid
            st.session_state["resource_url"] = resource_url
            st.session_state["resource_id"] = resource_id
            core = XetCore(appid)
            path = core.login_and_capture(resource_url, resource_id or None, wait)
            st.success(f"抓取完成: {path}")
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            st.json({"candidates": data.get("candidates", [])})


def ui_download_section():
    st.subheader("从抓取文件下载音频")
    appid = st.text_input("店铺ID(appxx)", key="dl_appid", value=st.session_state.get("appid", ""))
    capture_file = st.text_input("抓取JSON路径", key="dl_cap", value="")
    title = st.text_input("输出文件名(可选)", key="dl_title", value="")
    if st.button("开始下载"):
        if not appid or not capture_file:
            st.error("请填写店铺ID与抓取文件路径")
        else:
            core = XetCore(appid)
            out = core.download_from_capture(capture_file, title or None)
            if out:
                st.success(f"下载完成: {out}")
            else:
                st.error("下载失败，请检查抓取文件与登录状态")


def ui_list_section():
    st.subheader("抓取专栏列表 / 资源列表")
    appid = st.text_input("店铺ID(appxx)", key="list_appid", value=st.session_state.get("appid", ""))
    core = XetCore(appid) if appid else None

    with st.expander("抓取店铺专栏列表"):
        entry_url = st.text_input("任意店铺页URL(有专栏列表)", key="entry_url", value="")
        if st.button("抓取专栏", key="btn_products"):
            if not core or not entry_url:
                st.error("请填写店铺ID与入口URL")
            else:
                items = core.capture_products(entry_url)
                st.write(f"共 {len(items)} 个专栏")
                st.table({"id": [i.get("id") for i in items], "title": [i.get("title") for i in items]})

    with st.expander("抓取专栏内资源列表"):
        product_url = st.text_input("专栏详情页URL", key="product_url", value="")
        product_id = st.text_input("专栏ID(可选)", key="product_id", value="")
        if st.button("抓取资源", key="btn_resources"):
            if not core or not product_url:
                st.error("请填写店铺ID与专栏URL")
            else:
                items = core.capture_resources(product_url, product_id or None)
                st.write(f"共 {len(items)} 个资源")
                st.table({"id": [i.get("id") for i in items], "title": [i.get("title") for i in items]})


def main():
    ui_header()
    with st.container():
        cols = st.columns(3)
        with cols[0]:
            ui_capture_section()
        with cols[1]:
            ui_download_section()
        with cols[2]:
            ui_list_section()


if __name__ == "__main__":
    main()


