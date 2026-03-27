# Daily Security News

一个适合放在 GitHub 仓库里长期运行的 `v1` 项目：定时抓取网络安全 RSS，调用你自己的大模型 API 生成中文摘要，并把结果自动保存回仓库。

这个版本默认不做微信推送，产物直接写入：

- `data/YYYY-MM/YYYY-MM-DD.json`
- `data/YYYY-MM/YYYY-MM-DD.md`
- `data/latest.json`
- `data/latest.md`

## 适用边界

- 适合：每天定时运行、抓取 RSS、做摘要、把结果写回 GitHub。
- 不适合：常驻后台服务、实时监听、开放 HTTP 端口。
- 公开仓库不会自动泄露你的 API Key，前提是 Key 只放在 GitHub Actions Secrets 里。

## 目录结构

```text
.
├── .github/workflows/daily.yml
├── data/
├── state/seen_urls.json
├── src/
│   ├── config.py
│   ├── feeds.py
│   ├── fetcher.py
│   ├── main.py
│   ├── models.py
│   ├── storage.py
│   ├── summarizer.py
│   └── writer.py
├── .env.example
├── .gitignore
├── README.md
└── requirements.txt
```

## 仓库建议

GitHub 仓库 URL 建议使用：

```text
daily-security-news
```

README 标题和项目展示名保持：

```text
Daily Security News
```

## 快速开始

### 1. 创建 GitHub 仓库

建议新建一个公开仓库，然后把本目录代码推上去。

如果你以后给我的是 GitHub 用户名，我可以继续按 `owner/repo` 的形式帮你生成后续命令。你刚才提供的 `zhaokingmax@gmail.coom` 是邮箱格式，不是 GitHub 用户名，而且后缀看起来像有拼写问题。

### 2. 配置 GitHub Actions Secrets

进入仓库：

`Settings -> Secrets and variables -> Actions`

至少配置下面三个：

- `LLM_API_KEY`：你的模型 Key
- `LLM_BASE_URL`：模型接口地址，例如 `https://api.openai.com/v1`
- `LLM_MODEL`：模型名，例如 `gpt-4o-mini`、`deepseek-chat`

## 工作流说明

工作流文件是：

[`./.github/workflows/daily.yml`](./.github/workflows/daily.yml)

默认每天北京时间 `08:15` 运行一次，也支持手动触发。

运行流程：

1. 拉取 RSS。
2. 过滤已处理链接。
3. 尝试抓取正文。
4. 调用大模型生成中文摘要。
5. 使用批量摘要减少 token 消耗，并对失败文章自动单篇重试。
6. 英文内容优先翻译后生成中文摘要。
7. 按关注关键词优先排序，不够时自动补充非关键词资讯，并过滤黑名单内容。
8. 生成 JSON 和 Markdown 报告，顶部附带分类清单。
9. 自动提交 `data/` 和 `state/` 回仓库。

## 本地运行

### Windows PowerShell

```powershell
python -m venv .venv
. .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
python -m src.main
```

然后编辑 `.env`，填入你的 Key 和模型配置。

### 常用环境变量

- `LLM_API_KEY`
- `LLM_BASE_URL`
- `LLM_MODEL`
- `TZ_NAME`，默认 `Asia/Shanghai`
- `MAX_ARTICLES_PER_RUN`，默认 `50`
- `MAX_ARTICLES_PER_FEED`，默认 `8`
- `LLM_BATCH_SIZE`，默认 `5`；批量送给大模型，减少重复提示词的 token 开销
- `LLM_RETRY_COUNT`，默认 `2`；模型调用失败时自动重试
- `MAX_LLM_INPUT_CHARS_PER_ARTICLE`，默认 `2500`；每篇送入模型的正文截断长度
- `ENABLE_CONTENT_FETCH`，默认 `true`
- `ALLOW_FALLBACK_SUMMARY`，默认 `true`；没有配置模型或模型调用失败时会回退
- `FOCUS_KEYWORDS`，可选，逗号分隔；默认内置关注词，支持中英文匹配与优先排序
- `BLACKLIST_KEYWORDS`，可选，逗号分隔；命中后自动忽略
- `OUTPUT_DIR`，可选，自定义报告输出目录
- `STATE_FILE`，可选，自定义去重状态文件路径

## 输出文件说明

### `data/YYYY-MM/YYYY-MM-DD.json`

结构示例：

```json
{
  "date": "2026-03-27",
  "generated_at": "2026-03-27T08:15:00+08:00",
  "count": 2,
  "items": [
    {
      "source": "The Hacker News",
      "title": "Example title",
      "link": "https://example.com/article",
      "canonical_link": "https://example.com/article",
      "published_at": "2026-03-27T00:01:00+00:00",
      "category": "终端安全与EDR/XDR",
      "risk_level": "高",
      "keywords": ["勒索软件", "漏洞利用", "补丁"],
      "summary": "中文摘要",
      "important_points": ["要点 1", "要点 2"],
      "used_fallback": false,
      "matched_focus_keywords": ["microsoft", "edr"]
    }
  ]
}
```

### `state/seen_urls.json`

用于去重，避免同一篇文章被重复处理。

### `data/latest.md`

最上方会先输出今日分类清单，按 10+ 个主流安全主题把标题分组，便于快速浏览：

- AI安全与安全智能体
- 身份与访问控制
- 终端安全与 EDR/XDR
- APT 与国家级威胁
- 运营商与关键基础设施
- 漏洞与补丁
- 恶意软件与勒索软件
- 钓鱼与社工诈骗
- 数据泄露与隐私
- 云安全与容器
- 网络与边界安全
- 应用安全与供应链
- 威胁情报与研判
- 安全运营与 SOC
- 工控与物联网安全
- 政策合规与治理
- 综合资讯

## 数据源

默认内置这些资讯源：

- The Hacker News
- Krebs on Security
- BleepingComputer
- SecurityWeek
- Dark Reading
- CSO Online
- Infosecurity Magazine
- CyberScoop
- The CyberWire
- 安全内参
- 安全客
- CNCERT

你可以直接改这个文件：

[`./src/feeds.py`](./src/feeds.py)

## 安全建议

- 不要把 `.env` 提交到仓库。
- 不要在代码里 `print(LLM_API_KEY)`。
- 不要把请求头、完整报错对象、原始 API 响应写回 `data/`。
- 公开仓库建议只开放 `schedule` 和 `workflow_dispatch`，不要把不可信 PR 代码放进带 secrets 的工作流里执行。

## 后续扩展

这个 `v1` 完成后，下一步最自然的扩展是：

- Telegram 推送
- 企业微信机器人推送
- GitHub Pages 展示日报
- 按主题分类，例如漏洞 / 勒索软件 / 数据泄露 / APT
- 自动生成每周汇总
