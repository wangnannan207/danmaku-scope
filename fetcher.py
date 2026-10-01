# -*- coding: utf-8 -*-
"""
B站弹幕数据采集模块
====================
功能：输入视频 BV 号 → 获取视频基本信息 + 抓取全部弹幕（XML → 结构化数据）
依赖：Python 标准库（无需安装任何第三方包）

数据接口（均为B站公开接口）：
  1. 视频信息: https://api.bilibili.com/x/web-interface/view?bvid={BV号}
     返回 JSON，含标题、UP主、时长、播放量、弹幕数等
  2. 弹幕列表: https://api.bilibili.com/x/v1/dm/list.so?oid={cid}
     返回 XML（deflate 压缩），含该视频全部弹幕

合规说明：仅采集公开弹幕数据，遵守 robots 协议与网站条款，控制请求频率（默认每两次请求间隔 1 秒以上）。
"""

import urllib.request
import http.cookiejar
import json
import gzip
import zlib
import re
import time
import random


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.bilibili.com",
}

# 弹幕 XML 标签正则：<d p="时间,模式,字号,颜色,时间戳,池,用户hash,弹幕ID">文本</d>
DM_RE = re.compile(r'<d p="([^"]+)">([^<]*)</d>')


def build_opener():
    """构造带 Cookie 处理器的 urlopen（先访问首页获取 buvid3，模拟正常访客）。"""
    cj = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    req = urllib.request.Request("https://www.bilibili.com", headers=HEADERS)
    opener.open(req, timeout=15).read()
    return opener


def _get_json(opener, url):
    req = urllib.request.Request(url, headers=HEADERS)
    with opener.open(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))


def _get_bytes(opener, url):
    req = urllib.request.Request(url, headers=HEADERS)
    with opener.open(req, timeout=30) as r:
        return r.read()


def fetch_video_info(opener, bvid):
    """
    根据 BV 号获取视频基本信息。
    返回 dict：bvid/aid/cid/title/owner/duration/pubdate/ view/danmaku/reply/like/coin/favorite/share
    """
    data = _get_json(opener, f"https://api.bilibili.com/x/web-interface/view?bvid={bvid}")
    if data.get("code") != 0:
        raise RuntimeError(f"视频信息接口返回错误 code={data.get('code')}（BV号可能不存在）")
    d = data["data"]
    stat = d.get("stat", {})
    info = {
        "bvid": d.get("bvid"),
        "aid": d.get("aid"),
        "cid": d.get("cid"),
        "title": d.get("title"),
        "owner": (d.get("owner") or {}).get("name"),
        "duration": d.get("duration"),          # 秒
        "pubdate": d.get("pubdate"),            # 发布时间（Unix时间戳）
        "view": stat.get("view"),
        "danmaku_count_stat": stat.get("danmaku"),
        "reply": stat.get("reply"),
        "like": stat.get("like"),
        "coin": stat.get("coin"),
        "favorite": stat.get("favorite"),
        "share": stat.get("share"),
    }
    return info


def fetch_danmaku_xml(opener, cid):
    """下载弹幕 XML 并解压（服务器返回 deflate 或 gzip 压缩）。"""
    raw = _get_bytes(opener, f"https://api.bilibili.com/x/v1/dm/list.so?oid={cid}")
    if raw[:2] == b"\x1f\x8b":                       # gzip 魔数
        raw = gzip.decompress(raw)
    else:                                            # deflate
        try:
            raw = zlib.decompress(raw)
        except zlib.error:
            raw = zlib.decompress(raw, -zlib.MAX_WBITS)
    return raw.decode("utf-8", errors="replace")


def parse_danmaku(xml):
    """
    解析弹幕 XML → 记录列表。
    每条弹幕解析出 9 个字段（含义见 docs/数据字典.md）：
      t       视频内出现时间（秒，float）
      mode    弹幕模式（1-3滚动 / 4底端 / 5顶端 / 6逆向 / 7高级 / 8代码）
      size    字号
      color   颜色（十进制 RGB，16777215=白色）
      ts      发送时刻（Unix 时间戳）
      pool    弹幕池（0普通池）
      uid_hash 用户标识 hash（脱敏，无法反推具体用户）
      dm_id   弹幕 ID
      text    弹幕文本
    """
    rows = []
    for p, text in DM_RE.findall(xml):
        f = p.split(",")
        if len(f) < 8:
            continue
        try:
            rows.append({
                "t": float(f[0]),
                "mode": int(f[1]),
                "size": int(f[2]),
                "color": int(f[3]),
                "ts": int(f[4]),
                "pool": int(f[5]),
                "uid_hash": f[6],
                "dm_id": f[7],
                "text": text.strip(),
            })
        except (ValueError, IndexError):
            continue   # 字段解析失败的脏数据直接丢弃
    return rows


def fetch_by_bvid(bvid, max_count=5000, delay=1.0):
    """
    一键采集：BV号 → (视频信息, 弹幕记录列表)
    max_count: 课程要求不超过 5000 条，超出则按视频内时间均匀采样
    delay:     礼貌延迟，避免请求过快
    """
    bvid = bvid.strip()
    if not bvid.upper().startswith("BV"):
        raise ValueError("请输入以 BV 开头的视频编号，例如 BV1fK4y1t7hj")

    opener = build_opener()
    time.sleep(delay + random.random())

    info = fetch_video_info(opener, bvid)
    time.sleep(delay + random.random())

    xml = fetch_danmaku_xml(opener, info["cid"])
    rows = parse_danmaku(xml)

    # 课程要求数据量 ≤ 5000 条：超出则均匀采样
    if len(rows) > max_count:
        step = len(rows) / max_count
        rows = [rows[int(i * step)] for i in range(max_count)]

    return info, rows


if __name__ == "__main__":
    # 小测试：python fetcher.py BV1fK4y1t7hj
    import sys
    bv = sys.argv[1] if len(sys.argv) > 1 else "BV1fK4y1t7hj"
    info, rows = fetch_by_bvid(bv)
    print(f"《{info['title']}》 UP主: {info['owner']} 时长: {info['duration']}秒")
    print(f"播放量: {info['view']}  弹幕总数: {info['danmaku_count_stat']}  实际采集: {len(rows)} 条")
    for r in rows[:3]:
        print(f"  [{r['t']:8.1f}s] {r['text'][:30]}")
