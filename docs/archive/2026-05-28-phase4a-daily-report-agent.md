# Phase 4A: 日报 Agent — 日志驱动的采集情况报告

> 关联: [architecture-simplification.md](./2026-05-06-architecture-simplification.md) Phase 4
> 后续: [Phase 4B 删除 SQLite/补采/前端](./2026-05-28-phase4b-remove-sqlite-recrawl-frontend.md)
> 优先级: P3
> 工期: 2 天
> 状态: 待执行

---

## 背景

原 Phase 4 方案依赖 SQLite 聚合数据生成日报,但后续数据存储不再使用 SQLite。新方案改为:

- **数据源**: `services/live-crawler/logs/YYYY-MM-DD.logs`(loguru 纯文本日志)
- **生成方式**: Python 预过滤 + OpenAI API 生成自然语言报告
- **触发时间**: 每天早上 10:00(分析 T-1 全天日志)
- **推送渠道**: 飞书 Webhook 富文本卡片

本 phase 只新增日报功能,不删除任何现有代码,验证稳定后再执行 Phase 4B。

---

## 架构

```
Cron (每天 10:00)
  └─ scripts/daily_report.py
       ├─ 1. log_parser.py: grep 关键行 → 结构化 JSON 摘要
       ├─ 2. status_tracker.py: 读/写 account_status.json
       ├─ 3. openai_client.py: 调 OpenAI 生成自然语言报告
       └─ 4. feishu_webhook.py: 推飞书富文本卡片
```

### 日志预过滤规则

每天约 5 万行 → 压缩到 ~500 行 → ~10KB,提取以下模式:

| 正则模式 | 用途 |
|---|---|
| `开始执行定时采集任务` | 任务次数统计 |
| `📱 平台:` | 平台/账号数 |
| `\[(增量\|全量)\] 采集成功\|失败` | 单账号结果 |
| `总计: \d+/\d+ 账号采集成功` | 每轮汇总 |
| `\| ERROR\s+\|` | 异常分析 |
| `登出\|login_status=False\|需要登录` | 登出账号识别 |
| `分组: \S+` | 国家/团队归属 |

### 状态文件 Schema

`services/live-crawler/account_status.json`(运行时数据,gitignored):

```json
{
  "k1c0io17": {
    "last_success_date": "2026-05-23",
    "consecutive_logout_days": 5,
    "platform": "tiktok",
    "country": "TH",
    "group_name": "泰国团队-tiktok"
  }
}
```

每次运行:
- 解析当天日志,更新每个账号的 `last_success_date`
- 重新计算 `consecutive_logout_days = today - last_success_date`

### 报告内容(飞书富文本卡片)

```
📊 直播采集日报 2026-05-28

🟢 采集完整度
  TIKTOK | TH: 95% (38/40)  ↑2%
  TIKTOK | MY: 88% (22/25)  ↓5%
  LAZADA | TH: 100% (2/2)

🔴 问题账号(连续登出 ≥ 3 天)
  - k1c0io17 (TH-tiktok): 已登出 5 天
  - k1aayvhj (MY-lazada): 已登出 3 天

⚠️ 异常 Top 3
  - AdsPower 限流: 47 次(昨天 12 次)
  - 浏览器超时: 8 次
  - 养号失败: 3 次

📈 与昨天对比
  整体成功率 92% → 88%(下降 4%)
  新增登出账号: 2 个
```

---

## 执行步骤

### 1. 项目结构搭建

- [ ] 新建 `services/live-crawler/scripts/` 目录(若不存在)
- [ ] 新建 `services/live-crawler/scripts/prompts/` 子目录
- [ ] 在 `.gitignore` 添加 `services/live-crawler/account_status.json`

### 2. 日志解析器 `log_parser.py`

- [ ] 实现 `parse_log_file(path: Path) -> dict`,输出结构化 JSON:
  ```python
  {
    "date": "2026-05-28",
    "rounds": [{"time": "...", "platform": "lazada", "success": 2, "fail": 0}],
    "account_results": [{"browser_id": "...", "platform": "...", "country": "...", "result": "success|fail|logout", "time": "..."}],
    "errors": [{"time": "...", "level": "ERROR", "module": "...", "message": "..."}]
  }
  ```
- [ ] 单测覆盖关键正则(用 `tests/fixtures/sample_log.logs`)
- [ ] 处理日志缺失/损坏场景(返回空结果而非崩溃)

### 3. 状态追踪器 `status_tracker.py`

- [ ] 实现 `update_status(parsed_log: dict) -> None`
- [ ] 实现 `get_problem_accounts(min_days: int = 3) -> list[dict]`
- [ ] JSON schema 校验(损坏时备份 + 重建)
- [ ] 单测: 模拟连续 5 天日志,验证 `consecutive_logout_days` 累加正确

### 4. OpenAI 客户端 `openai_client.py`

- [ ] 单文件 < 80 行,依赖 `openai>=1.0`
- [ ] API Key 走环境变量 `OPENAI_API_KEY`(写入 `.env.example`)
- [ ] 模型默认 `gpt-4o-mini`(可通过 `OPENAI_MODEL` 覆盖)
- [ ] 失败时降级:不调 LLM,直接返回结构化摘要的纯文本格式
- [ ] 内置超时(30s)与重试(2 次)

### 5. Prompt 模板 `prompts/daily_report.md`

- [ ] 输入变量: `{today_summary}`、`{yesterday_summary}`、`{problem_accounts}`
- [ ] 输出要求: 飞书 Markdown 卡片格式
- [ ] 限定输出长度(避免飞书消息超限)

### 6. 飞书 Webhook `feishu_webhook.py`

- [ ] 单文件 < 60 行
- [ ] Webhook URL 走环境变量 `FEISHU_DAILY_REPORT_WEBHOOK`
- [ ] 暴露 `send_card(title: str, content_md: str)` 接口
- [ ] 内置签名计算(若启用密钥)与失败重试(3 次)
- [ ] 单测: mock httpx 验证 payload 结构

### 7. 主入口 `daily_report.py`

- [ ] 入参: `--date YYYY-MM-DD`(默认 T-1),便于补发
- [ ] 流程: 解析日志 → 更新状态 → 调 OpenAI → 推飞书
- [ ] 全程 try/except,失败时降级推送纯文本摘要
- [ ] 输出 stdout 完整执行日志便于排查

### 8. Cron 接入

- [ ] 新建 `services/live-crawler/cron.txt`(纯文档,不入 crontab),记录:
  ```
  0 10 * * * cd /opt/live-crawler && python -m scripts.daily_report
  ```
- [ ] `services/live-crawler/README.md` 末段新增「日报部署」章节

### 9. 验收

- [ ] 用历史日志手动跑一次:`python -m scripts.daily_report --date 2026-05-06`
- [ ] 飞书收到完整卡片,字段齐全
- [ ] 模拟日志缺失/OpenAI 超时,验证降级路径
- [ ] 连续运行 3 天,确认 `consecutive_logout_days` 累加正确
- [ ] 勾选 [`docs/ROADMAP.md`](../ROADMAP.md) 对应条目
- [ ] PR 标题: `feat(live-crawler): 日志驱动的每日采集报告 Agent`

---

## 验收清单

- [ ] `scripts/daily_report.py` 主流程跑通(过滤 → OpenAI → 飞书)
- [ ] `account_status.json` 状态文件正确累加
- [ ] OpenAI 失败时降级为纯文本摘要,飞书仍能收到
- [ ] cron 接入文档化到 `README.md`
- [ ] 连续运行 3+ 天稳定无崩溃

---

## 风险与回滚

| 风险 | 缓解 | 回滚 |
|---|---|---|
| OpenAI API 不可用/超额 | 失败降级为纯文本摘要 | 切换备用模型或暂停日报 |
| 日志格式变化导致 parser 失败 | 单测覆盖关键正则,parser 失败时输出原始关键行 | 修复正则后补发 |
| `account_status.json` 损坏 | 每次运行前备份 + JSON schema 校验 | 从最近 30 天日志重建 |
| 飞书消息超长被截断 | Prompt 限定输出长度,异常 Top 5 而非全量 | 拆分成多条消息 |

---

## 完成后

- [ ] 本 plan 移到 `docs/archive/2026-05-28-phase4a-daily-report-agent.md`
- [ ] 启动 Phase 4B(删除 SQLite/补采/前端)
- [ ] 更新 `services/live-crawler/CLAUDE.md` 监控章节
