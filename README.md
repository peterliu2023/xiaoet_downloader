# Xiaoet 视频/音频下载工具（支持扫码登录/GUI/批量下载）

> 仅支持下载本人已购买的课程资源，不提供任何破解功能；仅供学习研究自用，勿用于商业用途。

## 原理（新版方案概述）
- 使用 Playwright 启动 Chromium，打开小鹅通资源页面，扫码登录并将会话持久化（本地 `playwright_data/`）。
- 通过浏览器“网络响应监听”拦截页面产生的请求，自动识别音频直链（如 `.mp3/.m4a/.m3u8`）或 JSON 字段中的播放地址（`audio_url/play_url/hls_url`）。
- 将抓取到的请求头（含 Cookie）、候选直链与上下文信息保存为 `captured/{appid}/{resource_id}.json`。
- 使用 `requests` 携带抓到的头信息下载音频到 `download/`，文件名优先使用资源标题。
- 专栏/店铺列表通过监听页面的 JSON 接口响应，递归提取 `p_`（专栏）与 `a_/v_`（资源）的结构化数据。

## 目录结构
- `xet_core.py`：核心逻辑（扫码登录与持久化、网络拦截、候选提取、下载、列表抓取）
- `xet_cli.py`：统一 CLI（登录抓取、下载、快速一键、列表抓取）
- `xet_playwright.py`/`xet_download.py`：早期的登录捕获与下载脚本（仍可用）
- `app_streamlit.py`：Streamlit GUI（扫码登录/抓取/下载/列表）
- `download_product_all.py`：按专栏批量下载脚本（跳过已存在、随机等待）
- `captured/`：抓到的候选与列表 JSON
- `download/`：下载输出目录

## 安装
1) 安装依赖
```
pip3 install -r requirements.txt
```
2) 安装浏览器内核（首次）
```
python3 -m playwright install chromium --with-deps
```
3) （可选）安装 ffmpeg（仅旧版视频 .m3u8 合成使用）
```
brew install ffmpeg
```

## 使用方式

### 1. GUI（Streamlit）
启动：
```
streamlit run app_streamlit.py
```
浏览器访问控制台给出的地址（例如 `http://localhost:8502`）。

界面包含三块：
- 扫码登录并抓取候选音频URL：输入店铺ID、资源页面URL（可包含 `anonymous=2&product_id=...`）和资源ID，点击按钮后弹出浏览器扫码并抓取，结果以 JSON 显示。
- 从抓取文件下载音频：输入店铺ID与抓取 JSON 路径（上一步的输出），可自定义输出文件名，点击“开始下载”。
- 抓取专栏列表 / 资源列表：
  - 店铺专栏列表：输入店铺ID与入口 URL（如 `https://{appid}.xet.citv.cn`），抓取后表格显示 `id` 和 `title`。
  - 专栏内资源列表：输入专栏详情页 URL（形如 `/p/column/details?p_xxx`）与专栏ID（可选），抓取后表格显示资源 `id` 和 `title`。

### 2. CLI
统一命令：
```
python3 xet_cli.py <subcommand> [...options]
```

- capture：打开页面扫码并抓取音频候选
```
python3 xet_cli.py capture <appid> <resource_url> [--resource-id a_xxx] [--wait 180]
```

- download：使用抓取 JSON 下载
```
python3 xet_cli.py download <appid> <capture_json_path> [--title 输出名]
```

- quick：一步到位（打开-抓取-下载）
```
python3 xet_cli.py quick <appid> <resource_url> [--resource-id a_xxx] [--wait 180]
```

- quick-resource：通过 `product_id + resource_id` 构造资源页并下载
```
python3 xet_cli.py quick-resource <appid> <product_id> <resource_id> [--wait 180]
```

- list-products：抓取店铺专栏列表（可省略入口URL，自动拼 `https://{appid}.xet.citv.cn`）
```
python3 xet_cli.py list-products <appid> [entry_url] [--wait 120] [--show-browser]
```

- list-resources：抓取专栏内资源列表（`product_url` 可省略，配合 `--product-id` 自动构造）
```
python3 xet_cli.py list-resources <appid> [product_url] [--product-id p_xxx] [--wait 120] [--show-browser]
```

说明：
- `--show-browser` 用于可视化模式，便于手动滚动触发接口；默认无头模式。
- 资源页 URL 建议带 `anonymous=2&product_id=...`，工具会自动尝试触发播放（点击/`media.play()`）。

### 3. 批量下载整栏
脚本：`download_product_all.py`
```
python3 download_product_all.py <appid> <product_id> \
  [--wait-list 30] [--wait-capture 90] \
  [--sleep-min 3] [--sleep-max 8] \
  [--start 0] [--max -1] [--headless-list]
```
比如：`python download_product_all.py app8ydmwl262114 p_59e9fbdfbb63e_ttHpBdbE --wait-list 15 --wait-capture 45 --sleep-min 10 --sleep-max 30`
特性：
- 抓取到列表后，逐条打开资源页抓取并下载；输出文件名默认使用资源标题。
- 下载前检查 `download/` 是否已存在对应标题文件，存在则跳过。
- 每条下载间加入随机等待（默认 2-7 秒，参数可调）以降低风控概率。

## 实现细节
- Playwright 持久化登录：每个店铺使用独立的用户数据目录（`playwright_data/{appid}`），会话通常 4 小时有效，过期需重新扫码。
- 候选提取策略：
  - 音频响应：`content-type` 包含 `audio/`、`m3u8/mpegurl`；URL 后缀命中 `.m3u8/.mp3/.m4a/.aac/.flac`。
  - JSON 响应：字段命中 `audio_url`、`audioUrl`、`play_url`、`playUrl`、`hls_url`、`hlsUrl`。
- 列表提取策略：递归遍历 JSON，适配字段 `id/resource_id/spu_id/src_id`，前缀匹配 `p_/a_/v_`，并做去重（优先保留带标题的条目）。
- 下载：将抓到的 `headers`（含 `Cookie`）直接用于 `requests.get`，按资源标题命名保存到 `download/`。

## 注意事项
1. 仅下载本人已购买资源；本工具不提供任何破解能力。
2. 会话有效期有限（约 4 小时），失效后需重新扫码登录。
3. 若抓取不到列表/直链：
   - 增大 `--wait/--wait-list/--wait-capture` 等待时长；
   - 使用 `--show-browser` 并在页面内滚动，触发懒加载接口；
   - 确认资源页 URL 携带 `product_id`（如需）。
4. 视频合成（旧方案）：仅当使用 `xiaoet.py` 的视频下载与转码时需要 `ffmpeg`，纯音频下载无需。

## 示例链接（供调试）
- 某店铺与专栏/音频示例：
  - 店铺：`https://app8ydmwl262114.xet.citv.cn`
  - 专栏：`p_59e9fbdfbb63e_ttHpBdbE`
  - 音频资源：`a_68b6f890e4b0694c5b23e996`
  - 播放页：`https://app8ydmwl262114.xet.citv.cn/p/course/audio/a_68b6f890e4b0694c5b23e996?anonymous=2&product_id=p_59e9fbdfbb63e_ttHpBdbE`

## 备注：

1. 执行命令后需要微信扫码登录，session时效性为4小时，更换店铺需要重新扫码登录
2. 默认下载目录为同级download目录下，下载完成后视频为分段，将自动合成；音频不需要合成。
3. 店铺ID为appxxxx形式, 专栏ID(ProductID)为p_xxxx_xxx形式,资源ID(ResourceID)分为视频与音频, 分别为v_xxx_xxx、a_xxx_xxx形式，需要特别注意的是，这些ID区分大小写，因此从URL中复制这些信息的时候注意大小写要保留。


## 致谢
- 参考开源项目：`xiaoetong-video-downloader`（`https://github.com/jiji262/xiaoetong-video-downloader`）

