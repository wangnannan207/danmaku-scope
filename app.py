# -*- coding: utf-8 -*-
"""
弹幕显微镜 · B站视频观众集体行为数据分析系统（Streamlit 互动网页）
==========================================================================
- 输入任意 BV 号 → 现场采集弹幕 → 清洗 → SQLite → 自动生成分析报告
- 海外/离线演示环境自动回退到预置数据集（data/preset/）
- 交互查询：时间段 / 情感 / 弹幕模式 / 关键词 多条件联动 + CSV 下载
"""

import json
import os
import glob

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from fetcher import fetch_by_bvid
from analyzer import (
    clean_records, minute_density, top_moments, word_freq, keyword_timeline,
    sentiment_summary, sentiment_by_minute, send_hour_dist, mode_dist,
    color_dist, meme_density, basic_stats, sentiment_of,
)

# ---------------- 页面配置 ----------------

st.set_page_config(page_title="弹幕显微镜 · Danmaku Scope", page_icon="🔬",
                   layout="wide", initial_sidebar_state="collapsed")

PINK, BLUE, DARK = "#FB7299", "#00A1D6", "#1F2937"
PRESET_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "preset")

# ---------------- 全局样式（B站蓝粉主题） ----------------

st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+SC:wght@400;500;700;900&display=swap');
html, body, [class*="css"] {{ font-family: 'Noto Sans SC', 'Microsoft YaHei', sans-serif; }}
.hero {{
    background: linear-gradient(120deg, #00A1D6 0%, #23ADE5 45%, #FB7299 100%);
    border-radius: 18px; padding: 34px 40px 28px 40px; color: white;
    margin-bottom: 18px; box-shadow: 0 8px 28px rgba(0,161,214,.25);
}}
.hero h1 {{ font-size: 2.1rem; font-weight: 900; letter-spacing: 1px; margin: 0 0 6px 0; }}
.hero p {{ font-size: 1.02rem; opacity: .95; margin: 0; }}
.badge {{
    display: inline-block; background: rgba(255,255,255,.22); border: 1px solid rgba(255,255,255,.5);
    border-radius: 999px; padding: 2px 14px; font-size: .82rem; margin-right: 8px; margin-top: 10px;
}}
.metric-card {{
    background: linear-gradient(180deg, #FFFFFF, #F0F7FB); border: 1px solid #D6ECF7;
    border-radius: 14px; padding: 16px 10px 10px 10px; text-align: center;
    box-shadow: 0 2px 10px rgba(0,0,0,.04);
}}
.metric-card .num {{ font-size: 1.55rem; font-weight: 900; color: {BLUE}; }}
.metric-card .num.pink {{ color: {PINK}; }}
.metric-card .lbl {{ font-size: .85rem; color: #6B7280; margin-top: 2px; }}
.section-title {{
    font-size: 1.25rem; font-weight: 800; color: {DARK};
    border-left: 5px solid {PINK}; padding-left: 10px; margin: 26px 0 10px 0;
}}
.stButton > button {{
    background: linear-gradient(90deg, {BLUE}, {PINK}); color: white; border: none;
    border-radius: 10px; font-weight: 700; font-size: 1rem; padding: .55rem 1rem;
    box-shadow: 0 4px 14px rgba(251,114,153,.30); transition: transform .12s;
}}
.stButton > button:hover {{ transform: translateY(-2px); color: white; }}
div[data-testid="stMetric"] {{
    background: #F0F7FB; border: 1px solid #D6ECF7; border-radius: 12px; padding: 10px;
}}
</style>
""", unsafe_allow_html=True)


# ---------------- 预置数据集 ----------------

@st.cache_data(show_spinner=False)
def load_presets():
    presets = {}
    for info_fp in glob.glob(os.path.join(PRESET_DIR, "*_info.json")):
        bvid = os.path.basename(info_fp).replace("_info.json", "")
        csv_fp = os.path.join(PRESET_DIR, f"{bvid}_danmaku.csv")
        if not os.path.exists(csv_fp):
            continue
        with open(info_fp, encoding="utf-8") as f:
            info = json.load(f)
        df = pd.read_csv(csv_fp)
        presets[bvid] = {"info": info, "df": df}
    return presets


def annotate(df):
    """CSV 里无 sentiment 时补算（预置数据已带则跳过）"""
    if "sentiment" not in df.columns:
        scores, labels = [], []
        for t in df["text"].fillna(""):
            s, lab = sentiment_of(str(t))
            scores.append(s); labels.append(lab)
        df["sentiment"], df["sent_score"] = labels, scores
    return df


# ---------------- Hero 区 ----------------

st.markdown("""
<div class="hero">
  <h1>🔬 弹幕显微镜 <span style="font-size:1rem;font-weight:400;opacity:.85">Danmaku Scope</span></h1>
  <p>输入任意 B 站视频 BV 号，10 秒解剖它的弹幕生态 —— 名场面定位 · 情绪曲线 · 热词画像 · 观众行为</p>
  <span class="badge">《大数据导论》形式二实践项目</span>
  <span class="badge">采集-清洗-存储-查询-分析-可视化 全链路</span>
</div>
""", unsafe_allow_html=True)


# ---------------- 输入区 + 预置选择 ----------------

presets = load_presets()

with st.container():
    c1, c2 = st.columns([3, 1])
    with c1:
        bvid = st.text_input("视频 BV 号", placeholder="例如 BV1GJ411x7h7",
                             label_visibility="collapsed")
    with c2:
        go_btn = st.button("🚀 开始解剖", use_container_width=True)

preset_names = {bv: f"《{p['info']['title'][:22]}》" for bv, p in presets.items()}
pc1, pc2 = st.columns([1, 2])
with pc1:
    preset_sel = st.selectbox("或选择预置演示数据集（离线/演示环境可用）",
                              ["（不使用）"] + [f"{preset_names[bv]}  {bv}" for bv in presets],
                              label_visibility="collapsed") if presets else "（不使用）"
with pc2:
    st.caption("💡 提示：BV 号在 B 站视频网址里，形如 BV 开头的一串字符。实时抓取需要网络可访问 B 站。")


# ---------------- 数据装载 ----------------

def save_session(info, records):
    try:
        from store import get_conn, save_session
        conn = get_conn()
        save_session(conn, info, records)
        conn.close()
        return True
    except Exception:
        return False


def session_from_preset(bv, p):
    df = annotate(p["df"].copy())
    records = df.to_dict("records")
    st.session_state["info"] = p["info"]
    st.session_state["df"] = df
    st.session_state["clean_log"] = None
    st.session_state["preset"] = True


def session_from_live(bv):
    info, rows = fetch_by_bvid(bv, max_count=5000)
    cleaned, log = clean_records(rows, info["duration"])
    for r in cleaned:
        r["sent_score"], r["sentiment"] = sentiment_of(r["text"])
    df = pd.DataFrame(cleaned)
    df["minute"] = (df["t"] // 60).astype(int)
    st.session_state["info"] = info
    st.session_state["df"] = df
    st.session_state["clean_log"] = log
    st.session_state["preset"] = False
    save_session(info, cleaned)
    return info


if go_btn and bvid:
    with st.spinner("🔬 正在采集弹幕数据……"):
        try:
            info = session_from_live(bvid)
            st.success(f"✅ 实时采集成功！《{info['title']}》弹幕 {len(st.session_state['df'])} 条已入库")
        except Exception as e:
            st.session_state.pop("info", None)
            st.warning(f"⚠️ 实时采集失败（{e}）—— 演示环境网络可能受限，请改用预置数据集")
            st.stop()
elif preset_sel and preset_sel != "（不使用）":
    bv = preset_sel.split()[-1]
    if st.session_state.get("df") is None or st.session_state.get("preset_bv") != bv:
        session_from_preset(bv, presets[bv])
        st.session_state["preset_bv"] = bv
        st.info(f"📦 已载入预置数据集：《{presets[bv]['info']['title']}》（{len(presets[bv]['df'])} 条弹幕）")

if "info" not in st.session_state:
    st.stop()

info = st.session_state["info"]
df = st.session_state["df"]


# ---------------- 指标卡片 ----------------

def card(col, num, lbl, pink=False):
    col.markdown(f'<div class="metric-card"><div class="num{" pink" if pink else ""}">{num}</div>'
                 f'<div class="lbl">{lbl}</div></div>', unsafe_allow_html=True)


m = st.columns(6)
card(m[0], f"{info.get('view', 0):,}", "播放量")
card(m[1], f"{info.get('danmaku_count_stat', 0):,}", "弹幕总数")
card(m[2], len(df), "本次样本", pink=True)
card(m[3], f"{info.get('like', 0):,}", "点赞")
card(m[4], f"{info.get('coin', 0):,}", "投币")
card(m[5], f"{info.get('share', 0):,}", "分享")
st.divider()


# ---------------- 侧边栏查询筛选器 ----------------

with st.sidebar:
    st.header("🔍 查询筛选器")
    st.caption("对应报告『数据管理—查询需求』：每个筛选器即一条 SQL 查询")
    dur_min = max(int(info.get("duration", 0)) // 60, 1)
    time_range = st.slider("视频时间段（分钟）", 0, dur_min, (0, dur_min))
    sent_sel = st.multiselect("情感类型", ["正向", "中性", "负向"],
                              default=["正向", "中性", "负向"])
    mode_sel = st.multiselect("弹幕模式", ["滚动弹幕", "顶端弹幕", "底端弹幕", "其他模式"],
                              default=["滚动弹幕", "顶端弹幕", "底端弹幕", "其他模式"])
    kw = st.text_input("关键词包含", placeholder="如：名场面 / 高能 / 泪目")
    st.divider()
    log = st.session_state.get("clean_log")
    if log:
        st.header("🧹 清洗日志")
        for k, v in log.items():
            st.write(f"- {k}：**{v}** 条")
    st.caption("数据量 ≤5000 条，符合课程小体量数据集要求")

mode_map = {1: "滚动弹幕", 2: "滚动弹幕", 3: "滚动弹幕", 4: "底端弹幕", 5: "顶端弹幕"}
df["mode_label"] = df["mode"].map(mode_map).fillna("其他模式")

mask = df["minute"].between(time_range[0], time_range[1])
mask &= df["sentiment"].isin(sent_sel)
mask &= df["mode_label"].isin(mode_sel)
if kw:
    mask &= df["text"].astype(str).str.contains(kw, case=False)
fdf = df[mask]

st.markdown(f'<div class="section-title">筛选命中：{len(fdf)} / {len(df)} 条弹幕</div>',
            unsafe_allow_html=True)
st.download_button("⬇ 下载筛选结果 CSV", fdf.to_csv(index=False).encode("utf-8-sig"),
                   file_name=f"{info['bvid']}_danmaku.csv")

tab1, tab2, tab3 = st.tabs(["📈 高能时刻", "💬 文本与情感", "🕐 观众行为"])


# ---------------- Tab 1 ----------------

with tab1:
    density = minute_density(df.to_dict("records"), info.get("duration", 0))
    moments = top_moments(density, 10)
    g1, g2 = st.columns([3, 2])
    with g1:
        ddf = pd.DataFrame(density, columns=["分钟", "弹幕数"])
        fig = px.area(ddf, x="分钟", y="弹幕数", title="弹幕密度曲线 —— 哪里最热闹？")
        fig.update_traces(fill="tozeroy", line_color=BLUE, fillcolor="rgba(0,161,214,.25)")
        for mm, cnt in moments[:3]:
            fig.add_annotation(x=mm, y=cnt, text=f"第{mm}分·{cnt}条",
                               showarrow=True, arrowhead=2, ay=-45,
                               font=dict(color=PINK, size=12))
        fig.update_layout(height=400, hovermode="x unified")
        st.plotly_chart(fig, use_container_width=True)
    with g2:
        mdf = pd.DataFrame(moments, columns=["分钟", "弹幕数"])
        fig = px.bar(mdf, x="弹幕数", y="分钟", orientation="h", title="🏆 高能时刻 Top10",
                     color="弹幕数", color_continuous_scale=[(0, BLUE), (1, PINK)])
        fig.update_layout(height=400, yaxis={"autorange": "reversed"},
                          coloraxis_showscale=False)
        st.plotly_chart(fig, use_container_width=True)
    show_cols = ["t", "text", "sentiment", "mode_label"]
    st.dataframe(
        fdf[show_cols].rename(columns={"t": "时间(秒)", "text": "弹幕内容",
                                       "sentiment": "情感", "mode_label": "模式"}),
        use_container_width=True, height=280)


# ---------------- Tab 2 ----------------

with tab2:
    a1, a2 = st.columns(2)
    with a1:
        wf = word_freq(df.to_dict("records"), topk=25)
        wdf = pd.DataFrame(wf, columns=["词", "次数"])
        fig = px.bar(wdf, x="次数", y="词", orientation="h", title="观众都在说什么（词频 Top25）",
                     color="次数", color_continuous_scale=[(0, BLUE), (1, PINK)])
        fig.update_layout(height=430, yaxis={"autorange": "reversed"},
                          coloraxis_showscale=False)
        st.plotly_chart(fig, use_container_width=True)
    with a2:
        ss = sentiment_summary(df.to_dict("records"))
        sdf = pd.DataFrame({"情感": list(ss["ratio"].keys()), "占比": list(ss["ratio"].values())})
        fig = px.pie(sdf, names="情感", values="占比",
                     title=f"情感倾向占比（均值 {ss['mean_score']:.3f}）",
                     color="情感", hole=0.35,
                     color_discrete_map={"正向": "#34D399", "中性": "#94A3B8", "负向": "#F87171"})
        fig.update_layout(height=430)
        st.plotly_chart(fig, use_container_width=True)

    emo = sentiment_by_minute(df.to_dict("records"), info.get("duration", 0))
    edf = pd.DataFrame(emo, columns=["分钟", "平均情感得分"])
    fig = px.line(edf, x="分钟", y="平均情感得分", title="观众情绪曲线（正=欢呼，负=吐槽）")
    fig.update_traces(line_color=PINK, line_width=2.5)
    fig.add_hline(y=0, line_dash="dash", opacity=0.5)
    fig.update_layout(height=300, hovermode="x unified")
    st.plotly_chart(fig, use_container_width=True)

    st.markdown('<div class="section-title">🎯 关键词时间定位</div>', unsafe_allow_html=True)
    q = st.text_input("输入任意词，看它在视频哪一刻被刷屏", placeholder="例如：被骗 / 名场面 / 好听")
    if q:
        tl = keyword_timeline(df.to_dict("records"), q, bucket=10)
        if tl:
            tdf = pd.DataFrame(tl, columns=["秒", "出现次数"])
            fig = px.bar(tdf, x="秒", y="出现次数",
                         title=f"「{q}」在视频中的分布（每10秒一桶）")
            fig.update_traces(marker_color=BLUE)
            fig.update_layout(height=300, hovermode="x unified")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.warning("该关键词未在弹幕中出现")


# ---------------- Tab 3 ----------------

with tab3:
    b1, b2 = st.columns(2)
    with b1:
        hd = send_hour_dist(df.to_dict("records"))
        hdf = pd.DataFrame(hd, columns=["小时", "发送量"])
        fig = px.bar(hdf, x="小时", y="发送量", title="观众都是几点发弹幕的？（北京时间）")
        fig.update_traces(marker_color=BLUE)
        fig.update_layout(height=340, hovermode="x unified")
        st.plotly_chart(fig, use_container_width=True)
    with b2:
        md = mode_dist(df.to_dict("records"))
        mdf2 = pd.DataFrame({"模式": list(md.keys()), "数量": list(md.values())})
        fig = px.pie(mdf2, names="模式", values="数量", title="弹幕模式分布", hole=0.4,
                     color_discrete_sequence=[BLUE, PINK, "#94A3B8", "#FBBF24"])
        fig.update_layout(height=340)
        st.plotly_chart(fig, use_container_width=True)

    b3, b4 = st.columns(2)
    with b3:
        cd = color_dist(df.to_dict("records"))
        cdf = pd.DataFrame({"颜色": list(cd.keys()), "数量": list(cd.values())})
        fig = px.pie(cdf, names="颜色", values="数量",
                     title="弹幕颜色：白色是默认，彩色是刻意设置", hole=0.4,
                     color="颜色", color_discrete_map={"白色(默认)": "#CBD5E1", "彩色(自定义)": PINK})
        fig.update_layout(height=340)
        st.plotly_chart(fig, use_container_width=True)
    with b4:
        mm = meme_density(df.to_dict("records"))
        if mm:
            mm_df = pd.DataFrame(mm.most_common(10), columns=["梗词", "次数"])
            fig = px.bar(mm_df, x="次数", y="梗词", orientation="h", title="玩梗浓度 Top10",
                         color="次数", color_continuous_scale=[(0, BLUE), (1, PINK)])
            fig.update_layout(height=340, yaxis={"autorange": "reversed"},
                              coloraxis_showscale=False)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("本视频弹幕中未命中常见梗词表")

    st.markdown('<div class="section-title">描述性统计摘要</div>', unsafe_allow_html=True)
    st.json(basic_stats(df.to_dict("records")))

st.divider()
st.caption("弹幕显微镜 Danmaku Scope · 《大数据导论》形式二实践项目 · 数据来源：B站公开接口 · 样本量≤5000条")
