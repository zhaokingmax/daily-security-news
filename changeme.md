# ChangeMe

## 0.2
- 数据输出改为按月归档，日报保存到 `data/YYYY-MM/YYYY-MM-DD.{json,md}`。
- 新增关注关键词优先机制，支持中英文关键词匹配并在报告中标记命中词。
- 新增黑名单过滤机制，默认过滤 `密码学`、`cryptography`、`CVE` 相关内容。
- 增强大模型提示词，要求英文资讯先翻译再生成中文摘要，并在必要时做二次中文化修正。
- 扩充资讯源，新增 CSO Online、Infosecurity Magazine、CyberScoop、The CyberWire、安全内参、安全客、CNCERT。

## 0.1
- 初始版本：按天抓取网络安全 RSS，生成日报并写回仓库。
