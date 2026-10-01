# B站弹幕数据分析仪

《大数据导论》形式二实践项目 —— 输入任意 B 站视频 BV 号，现场解剖这个视频的弹幕生态。

## 功能

- 输入 BV 号 → 采集弹幕（≤5000 条）→ 清洗 → SQLite 存储 → 自动生成分析报告网页
- 三大分析页签：弹幕密度高能时刻 / 词频·情感·关键词定位 / 观众发送行为
- 侧边栏多条件联动筛选（时间段、情感、弹幕模式、关键词）+ CSV 下载

## 快速开始

**方式一：一键生成公网网址（推荐，答辩现场用）**

双击 `start_web.bat`，约 20 秒后自动打开浏览器并显示 `https://xxx.trycloudflare.com` 公网网址——任何设备（教室电脑、同学手机）都能访问。详见 docs/部署说明.md。

**方式二：本地运行**

```bash
# 依赖已装入 .venv 虚拟环境（Python 3.12），直接激活使用
.venv\Scripts\activate
streamlit run app.py
```

浏览器自动打开后，输入 BV 号（如 BV1GJ411x7h7），点击"开始解剖"。

## 纯命令行测试（无需装任何依赖）

```bash
python fetcher.py BV1GJ411x7h7
```

## 目录结构

```
├── app.py          # Streamlit 互动网页（主程序）
├── fetcher.py      # 弹幕采集（纯标准库：urllib/cookiejar/gzip/zlib/re）
├── analyzer.py     # 清洗 + 描述性分析（jieba 分词；无 jieba 自动兜底）
├── store.py        # SQLite 存储 + 5 个查询需求的 SQL 实现
├── requirements.txt
├── data/           # SQLite 数据库（运行后生成）
├── output/         # 报告示例图表与示例数据集（Rickroll 视频）
└── docs/
    ├── 数据字典.md      # 课程"数据管理"环节直接引用
    ├── 报告大纲.md      # 3000 字报告写作框架（含实测数据）
    └── AI使用说明.md    # 附录A：AI 提示词记录
```

## 注意事项

- 仅采集公开弹幕数据，请求间隔 ≥1 秒；数据量 ≤5000 条，符合课程要求
- 部分超大弹幕池视频接口返回量有限（如 Rickroll 返回约 1200 条），属正常现象
- 建议在报告附录中附上网页运行截图与本目录 output/ 中的示例图表
