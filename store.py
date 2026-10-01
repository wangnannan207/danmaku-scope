# -*- coding: utf-8 -*-
"""
数据存储与管理模块（SQLite 嵌入式数据库）
=========================================
课程要求"数据存储"环节：
  - 选用 SQLite：免安装服务器、单文件、事务支持，适合万条级以内小体量数据
  - 报告中对比 Excel / MySQL / SQLite 三者的读写、扩容、查询、冗余（见 docs/数据字典.md）
课程要求"数据管理"环节：
  - 数据字典见 docs/数据字典.md
  - 下方提供 5 个典型查询需求的 SQL 实现
"""

import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "danmaku.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS video_info (
    bvid        TEXT PRIMARY KEY,
    title       TEXT,
    owner       TEXT,
    duration    INTEGER,
    pubdate     INTEGER,
    view        INTEGER,
    danmaku_stat INTEGER,
    like_cnt    INTEGER,
    coin        INTEGER,
    favorite    INTEGER,
    share       INTEGER
);

CREATE TABLE IF NOT EXISTS danmaku (
    dm_id      TEXT PRIMARY KEY,
    bvid       TEXT,
    t          REAL,          -- 视频内出现时间（秒）
    minute     INTEGER,       -- 派生字段：t // 60，便于按分钟查询
    mode       INTEGER,       -- 弹幕模式
    size       INTEGER,       -- 字号
    color      INTEGER,       -- 颜色（十进制RGB）
    ts         INTEGER,       -- 发送时刻（Unix时间戳）
    uid_hash   TEXT,          -- 用户hash（脱敏）
    text       TEXT,          -- 弹幕文本
    sentiment  TEXT,          -- 情感标签：正向/中性/负向
    sent_score INTEGER        -- 情感得分
);
CREATE INDEX IF NOT EXISTS idx_danmaku_bvid   ON danmaku(bvid);
CREATE INDEX IF NOT EXISTS idx_danmaku_minute ON danmaku(minute);
CREATE INDEX IF NOT EXISTS idx_danmaku_sent   ON danmaku(sentiment);
"""


def get_conn(db_path=DB_PATH):
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA)
    return conn


def save_session(conn, info, records):
    """保存一次采集：视频信息 + 弹幕记录（带情感标注）"""
    cur = conn.cursor()
    cur.execute(
        """INSERT OR REPLACE INTO video_info
           (bvid,title,owner,duration,pubdate,view,danmaku_stat,like_cnt,coin,favorite,share)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (info["bvid"], info["title"], info["owner"], info["duration"], info["pubdate"],
         info["view"], info["danmaku_count_stat"], info["like"], info["coin"],
         info["favorite"], info["share"]),
    )
    cur.executemany(
        """INSERT OR REPLACE INTO danmaku
           (dm_id,bvid,t,minute,mode,size,color,ts,uid_hash,text,sentiment,sent_score)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        [(r["dm_id"], info["bvid"], r["t"], int(r["t"] // 60), r["mode"], r["size"],
          r["color"], r["ts"], r["uid_hash"], r["text"], r.get("sentiment", "中性"),
          r.get("sent_score", 0)) for r in records],
    )
    conn.commit()


# ---------------- 课程要求：典型查询需求（SQL 实现） ----------------

def q_time_range(conn, bvid, start_min, end_min, limit=500):
    """查询需求1：查询视频第 start~end 分钟内的弹幕"""
    return conn.execute(
        "SELECT minute, text, sentiment FROM danmaku WHERE bvid=? AND minute BETWEEN ? AND ? LIMIT ?",
        (bvid, start_min, end_min, limit),
    ).fetchall()


def q_sentiment(conn, bvid, label, limit=500):
    """查询需求2：筛选情感为某类（正向/中性/负向）的弹幕"""
    return conn.execute(
        "SELECT text, t FROM danmaku WHERE bvid=? AND sentiment=? LIMIT ?",
        (bvid, label, limit),
    ).fetchall()


def q_keyword(conn, bvid, keyword, limit=500):
    """查询需求3：查询包含某关键词的弹幕"""
    return conn.execute(
        "SELECT text, t FROM danmaku WHERE bvid=? AND text LIKE ? LIMIT ?",
        (bvid, f"%{keyword}%", limit),
    ).fetchall()


def q_mode(conn, bvid, mode_label, limit=200):
    """查询需求4：按弹幕模式筛选（顶端=5 底端=4 滚动=1,2,3）"""
    modes = {"顶端": (5,), "底端": (4,), "滚动": (1, 2, 3)}[mode_label]
    ph = ",".join("?" * len(modes))
    return conn.execute(
        f"SELECT text, t FROM danmaku WHERE bvid=? AND mode IN ({ph}) LIMIT ?",
        (bvid, *modes, limit),
    ).fetchall()


def q_minute_count(conn, bvid):
    """查询需求5：统计每分钟弹幕数量（高能时刻榜）"""
    return conn.execute(
        "SELECT minute, COUNT(*) FROM danmaku WHERE bvid=? GROUP BY minute ORDER BY minute",
        (bvid,),
    ).fetchall()
