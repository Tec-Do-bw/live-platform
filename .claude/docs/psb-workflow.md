# PSB 工作流系统（Plan-Setup-Build）

> 来源: YouTube 教程 - Claude Code 高效 AI 编程工作流

---

## 一、Plan（计划阶段）

### 1.1 明确目标
- 区分原型验证 vs 生产级应用
- 定义 MVP，规划后续里程碑
- 不要试图一次开发所有功能

### 1.2 编写 Project Spec
- 产品需求：面向谁、解决什么问题、用户交互逻辑
- 工程技术规范：技术栈、架构、约束

### 1.3 明确技术栈
在文档中明确指定技术栈，防止 Claude 随意引入混乱工具。

参考技术栈（Web 全栈）：
| 层级 | 推荐 |
|------|------|
| 前端框架 | Next.js |
| 托管 | Vercel |
| UI 组件 | Tailwind CSS + Shadcn |
| 数据库 | MongoDB / Supabase |
| 服务器 | DigitalOcean |
| 身份验证 | Clerk |
| 支付 | Stripe |
| 邮件 | Resend |
| 对象存储 | Cloudflare R2 |
| AI 集成 | Anthropic（文本）, Gemini（图像） |

---

## 二、Setup（环境设置）— 7 步配置清单

### 2.1 初始化 GitHub 仓库
- 支持 Vercel 分支预览
- 支持 Issue 驱动开发和 PR 复审

### 2.2 配置环境变量
- 让 Claude 生成 `.env.example` 模板
- 填入实际 API Key，避免中途中断

### 2.3 精炼 claude.md
- 写入：架构概述、UI 规范、提交规则、构建命令
- 保持简短，用外链引用其他 Markdown 节省上下文

### 2.4 建立自动化文档机制
四个核心文档（开发时自动更新）：
- `architecture.md` — 架构图
- `changelog.md` — 变更日志
- 项目状态文档 — 已完成的里程碑
- 核心功能参考文档

### 2.5 安装插件
- Anthropic Front-end 插件（前端 UI 优化）
- Feature Dev 插件（功能开发指令）

### 2.6 接入 MCP 服务器
- 数据库 MCP（MongoDB/Supabase）→ 直接读写数据库
- Playwright/Puppeteer MCP → 端到端测试

### 2.7 Slash Commands 与 Sub-agents
- **Slash Commands**: 如 `/commit`，共享当前上下文
- **Sub-agents**: 并行且上下文隔离
  - 专写测试用例的 Agent
  - 每次写完代码后复盘优化的 Retro Agent

### 2.8 进阶：Hooks 自动化
- 预授权文件修改权限，防止挂起
- 生命周期 Hook：代码完成后自动跑测试，失败则强制修复

---

## 三、Build（实战构建）

### 3.1 构建 MVP
1. 让 Claude 读取项目文档
2. **先用 Plan Mode** 输出执行步骤
3. 开启 Parallel Sub-agents 加速

### 3.2 三大日常工作流

#### 通用单功能开发
调研 → 计划(Plan) → 实现 → 测试（严密闭环）

#### Issue 驱动开发
1. Bug/需求拆解到 GitHub Issues
2. Claude 扫描 Issue
3. 在独立分支完成
4. 提交 PR

#### 多智能体并发（Multi-clauding）
- 结合 **Git Worktrees**
- 同时 3 个终端跑 3 个 Claude 实例
- 在隔离工作树中并行开发
- 最后统一合并

### 3.3 四个避坑建议

| 建议 | 说明 |
|------|------|
| 动态切换模型 | Opus=复杂规划, Sonnet=代码实现, Haiku=小修小补 |
| 定期同步记忆 | 完成大功能后强制 Claude 更新 claude.md |
| 防止历史倒退 | 用 `#` 告诉 Claude 错误教训，写入项目记忆 |
| 善用 Checkpoint/Rewind | 死胡同时果断回退，重新 Prompt 比继续修补更快 |
