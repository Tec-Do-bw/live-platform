# AI Coding 执行流程手册

> 基于 Claude Code + Superpowers + Everything Claude Code 的项目开发工作流

---

## 一、总览：项目生命周期

```
想法 → 头脑风暴 → 设计文档 → 实施计划 → 逐 Phase 编码 → 交付
        Phase 0      Phase 0     Phase 0      Phase 1-5      Done
```

每个阶段对应的核心 Skill：

| 阶段 | 用什么 | 产出 |
|------|--------|------|
| 头脑风暴 | `/superpowers:brainstorming` | brainstorm 总结文档 |
| 设计文档 | brainstorming 流程内自动生成 | `docs/plans/YYYY-MM-DD-<topic>-design.md` |
| 实施计划 | `/superpowers:writing-plans` | `docs/plans/YYYY-MM-DD-<topic>-impl.md` |
| 逐 Phase 编码 | `/superpowers:executing-plans` | 代码 + 测试 + commit |

---

## 二、Phase 0：从想法到可执行计划

### Step 1：头脑风暴

```
/superpowers:brainstorming
<你的想法描述>
```

AI 会按以下流程推进（每次只问一个问题）：

1. 探索项目上下文（读文件、看 git log）
2. 逐个提问澄清需求
3. 提出 2-3 种方案 + 推荐
4. 分段展示设计，每段确认
5. 生成设计文档 → `docs/plans/`
6. 自动过渡到 writing-plans

### Step 2：生成实施计划

```
/superpowers:writing-plans
基于 docs/plans/YYYY-MM-DD-xxx-design.md 生成详细实施计划
```

AI 会生成包含以下内容的计划文件：
- 按 Phase 分组的 Task 列表
- 每个 Task 的具体 Step（含代码片段）
- 测试用例（TDD 模式的 Task）
- 验证标准
- git commit 消息

**关键：生成后审查计划，告诉 AI 调整不合理的部分**（如爬虫代码不适合 TDD）。

---

## 三、Phase 1-N：逐 Phase 编码

### 每个 Phase 的标准流程

```
┌─────────────────────────────────────────────────┐
│  1. 确认步骤                                      │
│     /everything-claude-code:plan                  │
│     或 /superpowers:executing-plans              │
│                                                   │
│  2. 编码（根据 Task 类型选择模式）                   │
│     纯逻辑代码 → /everything-claude-code:tdd      │
│     改现有代码 → 直接编码 + 手动验证                │
│     前端页面   → 直接编码 + 浏览器验证              │
│                                                   │
│  3. 代码审查                                      │
│     /review                                       │
│     或 /everything-claude-code:python-review      │
│                                                   │
│  4. 验证                                          │
│     /superpowers:verification-before-completion   │
│                                                   │
│  5. 提交                                          │
│     /smart-commit                                 │
└─────────────────────────────────────────────────┘
```

### 开始执行计划

有两种执行模式（AI 会让你选择）：

**模式 A：Subagent-Driven（推荐）**
```
/superpowers:subagent-driven-development
执行 Phase X 的 Tasks
```
- 当前会话内逐 Task 分发子 agent
- 每个 Task 之间有 review checkpoint
- 适合需要你参与验证的 Phase（如 Phase 2 改爬虫代码）

**模式 B：Executing-Plans**
```
/superpowers:executing-plans
执行 docs/plans/xxx-impl.md 中的 Phase X
```
- 按计划文件逐步执行
- 更自动化，适合 Phase 1（纯新建代码）

### 具体指令示例

**Phase 1（基础设施，纯新建代码，用 TDD）：**
```
/superpowers:executing-plans
执行 Phase 1 的 Tasks 1-3，使用 TDD 模式。
```

**Phase 2（爬虫集成，改现有代码，不用 TDD）：**
```
/superpowers:subagent-driven-development
执行 Phase 2 的 Tasks 4-6。
Task 4-5 不写单元测试，编码后手动采集验证。
Task 6 使用 TDD。
```

**Phase 3（后端 API，用 TDD）：**
```
/superpowers:executing-plans
执行 Phase 3 的 Tasks 7-8，使用 TDD（TestClient）。
```

**Phase 4（前端，浏览器验证）：**
```
/superpowers:executing-plans
执行 Phase 4 的 Tasks 9-12。
不写前端测试，每个 Task 完成后 npm run dev 浏览器验证。
```

---

## 四、TDD 判断标准

不是所有代码都适合 TDD。判断原则：

| 代码类型 | TDD? | 验证方式 |
|----------|------|---------|
| 纯函数/纯逻辑（分类器、报告器） | 用 TDD | pytest |
| 数据库操作（SQLite CRUD） | 用 TDD | pytest + 内存 DB |
| API 端点（FastAPI） | 用 TDD | pytest + TestClient |
| 改现有代码（爬虫 base.py） | 不用 | 手动运行 + 检查结果 |
| 前端页面（Vue 组件） | 不用 | npm run dev + 浏览器 |
| 集成联调 | 不用 | 端到端手动验证 |

使用 TDD 时：
```
/everything-claude-code:tdd
为 XXX 模块编写测试，然后实现。
```

---

## 五、代码审查

### 基础审查
```
/review
```
调用通用代码审查 agent，检查质量、安全、一致性。

### Python 专项审查
```
/everything-claude-code:python-review
```
检查 PEP 8、类型提示、Pythonic 写法、安全问题。

### 审查时机
- 每个 Task 编码完成后（必须）
- 修改现有核心代码后（如 base.py）
- Phase 完成时做整体审查

---

## 六、验证与提交

### 提交前验证
```
/superpowers:verification-before-completion
```
自动运行 pytest、lint、检查是否有遗漏，确认全部通过后才提交。

### 提交代码
```
/smart-commit
```
自动分析 git diff，生成规范的 commit message。

### 快速提交+推送
```
/git-quick
```
一步完成 commit + push。

### 创建 PR
```
/git-pr
```
推送并创建 GitHub Pull Request。

---

## 七、Skill 速查表

### Superpowers 插件（流程控制类）

| Skill | 触发场景 | 说明 |
|-------|---------|------|
| `/superpowers:brainstorming` | 新功能/新项目开始前 | 头脑风暴，从想法到设计 |
| `/superpowers:writing-plans` | 设计确认后 | 生成详细实施计划 |
| `/superpowers:executing-plans` | 有计划文件后 | 按计划逐 Task 执行 |
| `/superpowers:subagent-driven-development` | 有计划，想逐 Task 控制 | 子 agent 模式执行 |
| `/superpowers:test-driven-development` | 写纯逻辑代码时 | TDD 流程 |
| `/superpowers:systematic-debugging` | 遇到 bug 时 | 系统化调试 |
| `/superpowers:verification-before-completion` | 提交前 | 运行测试确认通过 |
| `/superpowers:requesting-code-review` | 完成大功能后 | 请求代码审查 |
| `/superpowers:receiving-code-review` | 收到审查反馈时 | 处理审查意见 |
| `/superpowers:finishing-a-development-branch` | 功能完成后 | 决定 merge/PR/cleanup |

### Everything Claude Code 插件（领域专项类）

| Skill | 触发场景 | 说明 |
|-------|---------|------|
| `/everything-claude-code:plan` | Phase 开始前 | 确认实施步骤 |
| `/everything-claude-code:tdd` | 写纯逻辑/API 代码 | TDD 模式编码 |
| `/everything-claude-code:python-review` | Python 代码完成后 | Python 专项审查 |
| `/everything-claude-code:security-review` | 涉及认证/输入处理时 | 安全审查 |
| `/everything-claude-code:api-design` | 设计 REST API 时 | API 设计模式 |
| `/everything-claude-code:postgres-patterns` | 数据库设计时 | 数据库最佳实践 |
| `/everything-claude-code:frontend-patterns` | 前端开发时 | 前端最佳实践 |
| `/everything-claude-code:verification-loop` | 持续验证 | 综合验证系统 |
| `/everything-claude-code:learn-eval` | Session 结束时 | 提取可复用模式 |

### 脚手架内置命令

| 命令 | 说明 |
|------|------|
| `/smart-commit` | 分析 diff，生成 commit message 并提交 |
| `/git-quick` | commit + push 一步到位 |
| `/git-feature` | 创建 feature 分支 |
| `/git-pr` | 推送并创建 PR |
| `/git-sync` | 同步远程代码 |
| `/review` | 通用代码审查 |
| `/plan` | 制定实现计划 |
| `/new-feature` | 新功能开发流程 |
| `/fix-bug` | Bug 修复流程 |
| `/update-docs` | 更新文档 |

---

## 八、跨 Session 工作

### 上下文恢复

每次新开 Claude Code 会话，AI 会自动读取：
- `CLAUDE.md` — 项目配置、技术栈、命令
- 各子项目的 `CLAUDE.md` — 子项目特有规则和架构

所以新 Session 不需要重复交代背景。

### 继续未完成的 Phase

直接告诉 AI：
```
继续执行 docs/plans/xxx-impl.md 中的 Phase X，从 Task N 开始。
```

### Session 建议拆分方式

| 方式 | 适用场景 |
|------|---------|
| 1 Session = 1 Phase | 大多数情况 |
| 1 Session = 多个简单 Phase | Phase 1 + Phase 3（都是纯新建） |
| 1 Session = 1 Task | Phase 2 改爬虫代码，每个 Task 独立确认 |

---

## 九、最佳实践

1. **先 Plan 再编码** — 复杂任务必须先用 brainstorming/plan，不要直接开写
2. **TDD 看场景** — 纯逻辑用 TDD，依赖外部环境的代码手动验证
3. **改核心代码必须 review** — 特别是改现有生产代码（如爬虫 base.py）
4. **每个 Task 一次 commit** — 保持 git 历史清晰，方便回滚
5. **提交前必须验证** — `/superpowers:verification-before-completion`
6. **遇到 bug 用 systematic-debugging** — 不要盲目猜测，按流程调试
7. **Session 结束用 learn-eval** — 提取可复用模式供后续 Session 使用
