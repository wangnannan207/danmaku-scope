# -*- coding: utf-8 -*-
"""
弹幕数据清洗与分析模块
======================
功能：对采集到的弹幕记录进行清洗、描述性统计与可视化数据准备
分析方法均为描述性统计（均值/分布/相关性/词频/规则法情感倾向），不使用机器学习建模。

依赖：jieba（中文分词，pip install jieba）
"""

import re
import math
from collections import Counter

try:
    import jieba
    jieba.setLogLevel(60)   # 关闭分词日志输出
    HAS_JIEBA = True
except ImportError:
    HAS_JIEBA = False


# ---------- 内置小型停用词表与情感词典（规则法，非机器学习） ----------

STOPWORDS = set("""
的 了 是 在 我 你 他 她 它 们 和 就 都 而 及 与 或 也 但 被 把 让 向 从 到 于 这 那 有 无 不 没 还 又 再 就 很 太 最 啊 呀 呢 吧 吗 哦 哈 嗯 嘛 咯 呗 喽 哈 嘻 嘿 哇 哟 呕 哼 啧 咋 啥 怎 多 少 么 之 其 此 彼 一 二 三 这个 那个 什么 怎么 这样 那样 就是 因为 所以 如果 虽然 可以 可能 应该 已经 正在 没有 不要 不能 不会 真的 感觉 现在 知道 看到 视频 up UP 主播 大家 哈哈哈 哈哈哈哈 1111 2222 3333
""".split())

POSITIVE_WORDS = set("""
好 棒 强 厉害 优秀 完美 精彩 好看 好听 牛 牛逼 绝 绝了 美 帅 酷 燃 萌 可爱 甜 泪目 感动 震撼 惊艳 喜欢 爱 支持 赞 好评 吹爆 打call 加油 期待 真香 稳 秀 神仙 宝藏 清晰 流畅 舒服 享受 震撼 壮观 优雅 细腻 厉害 硬核 专业 良心 用心 不错 可以 行 顶 爱了 赢麻 无敌 封神
""".split())

NEGATIVE_WORDS = set("""
差 烂 垃圾 难看 难听 失望 无聊 尴尬 假 水 菜 弱 崩 卡 糊 糊了 模糊 垃 废 不行 不好 讨厌 烦 吵 杂 乱 假 拖 慢 低配 顶不住 不行 难看 退 差劲 拉胯 摆烂 垃圾 白给 离谱 阴间 辣眼 刺耳 翻车 劝退
""".split())

# B站常见弹幕梗词（中性，单独统计可出"玩梗浓度"）
MEME_WORDS = ["awsl", "yyds", "卧槽", "名场面", "名场景", "高能", "前方高能",
              "弹幕护体", "火钳刘明", "爷青回", "泪目", "名场面", "名台词",
              "233", "666", "草", "去世", "去世", "去世"]


def clean_records(rows, duration):
    """
    数据清洗：
      1) 剔除空文本弹幕
      2) 剔除超出视频时长的异常时间戳弹幕
      3) 按（uid_hash, text, 分钟级时间）去重，处理重复刷屏弹幕
      4) ts=0 的异常发送时间保留但标记
    返回清洗后的记录列表 + 清洗日志（报告"数据质量问题"章节直接引用）
    """
    log = {"空文本剔除": 0, "超时长剔除": 0, "重复剔除": 0}
    seen = set()
    cleaned = []
    for r in rows:
        if not r["text"]:
            log["空文本剔除"] += 1
            continue
        if duration and r["t"] > duration + 1:
            log["超时长剔除"] += 1
            continue
        key = (r["uid_hash"], r["text"], int(r["t"] // 60))
        if key in seen:
            log["重复剔除"] += 1
            continue
        seen.add(key)
        cleaned.append(r)
    return cleaned, log


# ---------- 1. 时间分布 ----------

def minute_density(rows, duration):
    """按视频分钟统计弹幕密度，返回 [(minute, count), ...]（高能时刻榜）"""
    counter = Counter(int(r["t"] // 60) for r in rows)
    minutes = duration // 60 + 1
    return [(m, counter.get(m, 0)) for m in range(minutes)]


def top_moments(density, topk=10):
    """弹幕密度 TopK 分钟 → "高能时刻表" """
    return sorted(density, key=lambda x: -x[1])[:topk]


# ---------- 2. 文本分析 ----------

def _cut_words(text):
    if HAS_JIEBA:
        return jieba.lcut(text)
    # 无 jieba 时的兜底：按非中文字符切分 + 单字
    return [w for w in re.split(r"[^\u4e00-\u9fa5A-Za-z0-9]+", text) if w]


def word_freq(rows, topk=30):
    """
    词频统计：jieba 分词 → 去停用词 → 过滤长度为1的纯标点 → Counter
    返回 [(词, 次数), ...]
    """
    counter = Counter()
    for r in rows:
        for w in _cut_words(r["text"]):
            w = w.strip().lower()
            if len(w) < 2 and not w.isascii():   # 去掉单字中文噪音
                continue
            if w.isdigit():                       # 去掉纯数字（时间戳碎片等）
                continue
            if w in STOPWORDS:
                continue
            counter[w] += 1
    return counter.most_common(topk)


def keyword_timeline(rows, keyword, bucket=10):
    """
    关键词时间定位：该关键词的弹幕在视频每 `bucket` 秒桶内的分布
    用于互动查询"某个词在视频哪一刻集中出现"
    """
    kw = keyword.strip().lower()
    counter = Counter()
    for r in rows:
        if kw in r["text"].lower():
            counter[int(r["t"] // bucket)] += 1
    if not counter:
        return []
    max_bucket = max(counter)
    return [(b * bucket, counter.get(b, 0)) for b in range(max_bucket + 1)]


# ---------- 3. 情感倾向（词典规则法，属于描述性统计） ----------

def sentiment_of(text):
    """
    规则法：命中正向词 +1，命中负向词 -1，得到情感得分
    返回 (得分, 标签)  标签 ∈ {正向, 中性, 负向}
    """
    words = [w.strip().lower() for w in _cut_words(text)]
    pos = sum(1 for w in words if w in POSITIVE_WORDS)
    neg = sum(1 for w in words if w in NEGATIVE_WORDS)
    score = pos - neg
    if score > 0:
        return score, "正向"
    if score < 0:
        return score, "负向"
    return 0, "中性"


def sentiment_summary(rows):
    """
    返回：整体情感占比 {正向:x, 中性:x, 负向:x}、
          每条记录的情感得分列表、情感均值
    """
    labels = Counter()
    scores = []
    for r in rows:
        s, lab = sentiment_of(r["text"])
        scores.append(s)
        labels[lab] += 1
    mean_score = sum(scores) / len(scores) if scores else 0
    total = sum(labels.values()) or 1
    ratio = {k: labels.get(k, 0) / total for k in ("正向", "中性", "负向")}
    return {"ratio": ratio, "mean_score": mean_score, "scores": scores}


def sentiment_by_minute(rows, duration):
    """情感随时间变化（每分钟平均情感得分）→ 观众情绪曲线"""
    buckets = {}
    for r in rows:
        m = int(r["t"] // 60)
        s, _ = sentiment_of(r["text"])
        buckets.setdefault(m, []).append(s)
    minutes = duration // 60 + 1
    return [(m, sum(buckets[m]) / len(buckets[m]) if m in buckets else 0)
            for m in range(minutes)]


# ---------- 4. 发送行为分析 ----------

def send_hour_dist(rows):
    """弹幕发送时刻（北京时间小时）分布 → '观众都几点看视频' """
    import datetime
    counter = Counter()
    for r in rows:
        if r["ts"] <= 0:
            continue
        h = datetime.datetime.fromtimestamp(r["ts"]).hour
        counter[h] += 1
    return [(h, counter.get(h, 0)) for h in range(24)]


def mode_dist(rows):
    """弹幕模式分布：1-3滚动 / 4底端 / 5顶端 / 其他"""
    counter = Counter()
    for r in rows:
        m = r["mode"]
        if m in (1, 2, 3):
            counter["滚动弹幕"] += 1
        elif m == 4:
            counter["底端弹幕"] += 1
        elif m == 5:
            counter["顶端弹幕"] += 1
        else:
            counter["其他模式"] += 1
    return counter


def color_dist(rows):
    """颜色分布：白色(默认) vs 彩色(自定义)"""
    counter = Counter()
    for r in rows:
        counter["白色(默认)"] += 1 if r["color"] == 16777215 else 0
        counter["彩色(自定义)"] += 1 if r["color"] != 16777215 else 0
    return counter


def meme_density(rows):
    """玩梗浓度：命中的常见弹幕梗词统计"""
    counter = Counter()
    for r in rows:
        t = r["text"].lower()
        for m in MEME_WORDS:
            if m in t:
                counter[m] += 1
                break
    return counter


def basic_stats(rows):
    """基础描述性统计（报告'数据分析'章节用）"""
    likes = [r.get("like", 0) for r in rows]
    n = len(rows) or 1
    return {
        "样本量": len(rows),
        "平均每条弹幕长度": round(sum(len(r["text"]) for r in rows) / n, 2),
        "弹幕点赞均值": round(sum(likes) / n, 2),
        "弹幕点赞最大值": max(likes) if likes else 0,
    }
