# TikTok HTTP 重构 — P2 技术债待办清单

> 来源：2026-05-29 实施完整性校验报告（docs/verification-report-2026-05-29.html）
> 状态：P0 + P1（除忽略项）已修复并提交（commit f04cb85）
> 本清单为 **P2 低优先级技术债**，按项目规则在 plan 完成时统一处理。

## 处理原则

按 `.claude/rules/update-docs-on-structure-change.md`：ROADMAP / CLAUDE.md / README 的同步更新发生在 **plan 完成（移入 archive）时**，而非实施过程中。因此下列文档类待办**不单独提交**，待 `2026-05-28-tiktok-http-refactor.md` 灰度验证通过、plan 收尾时一次性处理。

---

## 一、已决定忽略（用户确认）

- [ ] ~~中途登出检测（401/403 不置 login_status=False）~~ — 交养号解耦那边统一处理
- [ ] ~~飞书 webhook 硬编码明文（config_base.py:259）~~ — 用户接受当前风险

---

## 一·五、登出恢复全量（2026-06-02 已实现）

> 对齐 `.claude/rules/logout-recovery-flow.md`，让 HTTP 版与浏览器版登出恢复行为一致。

- [x] **adapter 集成 send_login_callback**（crawlers/http/tiktok/adapter.py）
  - 验证通过发 `success` 回调，内部检测 logout→login 即时恢复 → 当轮切 `full_collection=True`
  - 登录态失效（LoginRequired）发 `logout` 回调并写登出事件，供下一轮 `resolve_collection_mode` 判定
  - 返回值新增 `login_recovery` 透传给 main.py 补写 full_recovery_started/succeeded 事件
- [x] **collector 抽出 setup_session**（crawlers/http/tiktok/collector.py）
  - 验证阶段（load_credentials + 建会话 + account_info）独立，使「验证→回调→决定 full」先于数据采集 generator
  - `collect_tiktok` 增加 cred/session/login_result 注入参数（缺省时自动 setup，向后兼容）
- [x] **单元测试**（tests/crawlers/http/test_tiktok_adapter_recovery.py）
  - logout→login 触发全量 / 正常登录保持增量 / LoginRequired 发 logout 回调，3 项通过
- 说明：HTTP 回调是否真发出由 `LOGIN_CALLBACK_CONFIG.enabled` 控制；本地事件写入与恢复检测无条件执行。与上面"中途登出检测（401/403 实时置 login_status）"是不同议题，后者仍按原决定交养号侧。
- 即时恢复（2 轮）链路本次打通；Fallback（3 轮）依赖 main.py 现有 `resolve_collection_mode`，因 HTTP 版现已写 logout/login 事件而自动生效。

---

## 二、文档同步（待 plan 完成时统一处理）

- [ ] **CLAUDE.md 补录 5 项重要技术决策**（services/live-crawler/CLAUDE.md）
  - account_credentials 统一公共凭据表（替代 cookies 表、跨平台共用）
  - group_name 与 region 两个正交维度，严禁从 group_name 反推 region
  - TIKTOK_CRAWLER_MODE 环境变量 + 账号级 crawler_mode 字段的双重灰度路由
  - HTTP 版 _format_message 必须与浏览器版 format_api_message 字段级一致
  - 养号/采集解耦（adspower-server 写凭据，live-crawler 纯 HTTP 读）
- [ ] **ROADMAP 登记**（docs/ROADMAP.md）
  - Phase 4A 日报 Agent 加入「最近完成」
  - TikTok HTTP 重构 plan 完成后加入「最近完成」+ 移 plan 到 archive/
- [ ] **README 更新**（services/live-crawler/README.md）
  - 功能特性「TikTok 浏览器采集」→ 体现 HTTP 双轨
  - 补 TIKTOK_CRAWLER_MODE / crawler_mode 灰度开关说明
  - 补 jobs/refresh_tiktok_credentials.py 运行/cron 方式
  - 修复 README:166 悬空引用「见规则七」→「见规则五」
- [ ] **lazada-http-crawler-spec.md** 目录树更新已删除结构（Phase 4B 删的 db.py/recrawl/ 等）
- [ ] 按需补 services/live-crawler/.env.example，或在 README 注明「无 dotenv，配置走 export」的取舍

---

## 三、清理遗漏（可独立小 commit，低风险）

- [ ] **删除死配置 RECRAWL_CONFIG**（core/config_base.py:277-284）— Phase 4B 已删补采系统，配置无消费方
- [ ] **确认孤儿模块去留**（monitor/classifier.py、monitor/registry.py）— 补采/监控 API 删除后无生产调用，仅测试引用；确认是否作为监控重建扩展点保留
- [ ] **清理 ReCrawl 残留**（services/live-monitor/ReCrawl/）— git rm 后磁盘残留空目录 + __pycache__/*.pyc
- [ ] **改回直白写法**（monitor/__init__.py:13-14）— `_sq+lite3` / `monitor+.db` 字符串拼接（疑似规避 grep 的混淆，降低可读性）

---

## 四、代码整洁度（无功能风险，可选）

- [ ] **凭据加载去重**（live_crawler.py:66 / adapter.py:52 / collector.py:381）— 单账号单轮重复读库 3 次，工厂层 cred 透传给 adapter/collector 复用
- [ ] **migrate 脚本 DDL 去重**（scripts/migrate_account_credentials.py）— CREATE_TABLE_SQL 与 utils/credentials.py 重复，改为 import 复用
- [ ] **fixture 真实化**（tests/fixtures/tiktok_browser_message.json）— 手写 fixture 换成真实浏览器版 format_api_message 输出（plan 第 873 行要求）

---

## 五、放量前必做（虽非 P2，但提醒）

- [ ] **stats_types 结构变更需真实响应核验** — 本次 commit f04cb85 已按接口文档 §2.1 修正 live/stats 的 stats_types 集合与 params[0]+is_live_type 结构，但建议灰度时用字段 diff 工具拿一份真实响应再核一遍
- [ ] **curl_cffi 版本对齐** — 当前环境 curl_cffi 0.13.0 不含代码 import 的 RetryStrategy，CI/部署前需确认版本（与本次改动无关，预存问题）
