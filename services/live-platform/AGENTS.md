# live-platform Agent 约束

通用规则见仓库根 `CLAUDE.md`；本服务设计约束见同目录 `CLAUDE.md`。本文只保留额外硬约束。

## 配置

- 业务配置必须且只能通过 `shared.config.settings` 读取。
- 只有 Apollo 启动参数可读环境变量：`APOLLOID`、`APOLLO_URL`、`DEPLOY_ENV`。
- 禁止引入 `.env`、配置文件、命令行参数、硬编码业务配置或第二套配置系统。
- Apollo 客户端使用 `core/apollo/` 团队模板；不要自写客户端、替换 SDK 或单独修改模板。
- 新增/修改配置：先补 Apollo key，再改 `shared/config.py`，最后验证读取正常。
- 配置清单以 `shared/config.py` 为准，不在本文重复维护。
- 日志禁止输出密码、secret、token、access key 等敏感值。
