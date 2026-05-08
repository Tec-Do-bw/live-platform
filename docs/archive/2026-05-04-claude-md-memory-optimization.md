# CLAUDE.md 和 Memory 优化实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 解决"项目灵魂缺失"问题，建立可持续的进度跟踪机制，优化 Memory 结构（≤5 个文件），建立清晰的知识分层决策规则。

**Architecture:** 三阶段实施 — Phase 1 补全 P0 服务 CLAUDE.md + 修正环境信息（并行）；Phase 2 工作流规则转 skills/hooks（串行，依赖 Phase 1）；Phase 3 Memory 瘦身与知识分层（串行，依赖 Phase 2）。

**Tech Stack:** Markdown、Claude Code Skills、Hooks 配置

---

## 分阶段 Plan

### Phase 1: CLAUDE.md 增强（并行任务）

**目标**：补全 P0 服务文档，修正环境信息，建立子项目文档规范

**任务**：
- [ ] Task 1.1: 创建 live-monitor/CLAUDE.md
- [ ] Task 1.2: 创建 live-stream/CLAUDE.md
- [ ] Task 1.3: 修正根 CLAUDE.md 环境信息（Windows → macOS）
- [ ] Task 1.4: 建立子项目 CLAUDE.md 模板

**验收标准**：
- 4 个子项目均有 CLAUDE.md（live-monitor、live-stream、adspower-server、live-crawler）
- 根 CLAUDE.md 环境信息与实际一致（macOS Darwin 25.3.0）
- 子项目 CLAUDE.md 遵循层级继承原则（不重复根规则）
- 每个子项目 CLAUDE.md 包含：架构概览、关键文件、启动命令、测试命令

**风险**：子项目文档内容不一致 | **缓解**：先建立统一模板，再填充内容

---

### Phase 2: 工作流规则可执行化（串行任务）

**目标**：将泛化工作流规则转为可触发的 skills 和 hooks

**任务**：
- [ ] Task 2.1: 分析现有工作流规则的触发条件
- [ ] Task 2.2: 创建 `update-claude-md` skill（文件变更时自动更新 CLAUDE.md）
- [ ] Task 2.3: 配置 hooks（pre-commit 检查 CLAUDE.md 同步）
- [ ] Task 2.4: 更新根 CLAUDE.md 工作流规则章节（引用 skill 和 hooks）

**验收标准**：
- 工作流规则 1-6 均有明确触发条件
- `update-claude-md` skill 可用（通过 `/update-claude-md` 触发）
- Pre-commit hook 检查 CLAUDE.md 是否与代码同步
- 根 CLAUDE.md 工作流规则章节包含 skill 和 hooks 使用说明

**风险**：Hooks 配置复杂度高 | **缓解**：先实现 skill，hooks 作为可选增强

---

### Phase 3: Memory 瘦身与知识分层（串行任务）

**目标**：Memory 文件数 ≤5，建立清晰的知识分层决策规则

**任务**：
- [ ] Task 3.1: 审计现有 9 个 memory 文件，识别重复/类型错误
- [ ] Task 3.2: 合并 project 类型 memory（project_overview + project_integration_background → project_context.md）
- [ ] Task 3.3: 补充 feedback 类型 memory（从对话历史提取）
- [ ] Task 3.4: 建立知识分层决策规则（CLAUDE.md vs Memory vs references）
- [ ] Task 3.5: 更新 MEMORY.md 索引

**验收标准**：
- Memory 文件数 ≤5（user_profile、project_context、core_technical_issues、ddd_architecture_decision、feedback）
- 每个 memory 文件有正确的 frontmatter（name、description、type）
- 知识分层决策规则文档化（在根 CLAUDE.md 或 .claude/references/）
- MEMORY.md 索引清晰（每条 ≤150 字符）

**风险**：合并 memory 时丢失关键信息 | **缓解**：先备份，逐条迁移并验证

---

## 任务依赖图

```
Phase 1 (并行)
  ├─ Task 1.1: live-monitor/CLAUDE.md
  ├─ Task 1.2: live-stream/CLAUDE.md
  ├─ Task 1.3: 修正根 CLAUDE.md 环境
  └─ Task 1.4: 建立子项目模板
     └─ Phase 2 (串行，依赖 Phase 1)
        ├─ Task 2.1: 分析工作流规则
        ├─ Task 2.2: 创建 update-claude-md skill
        ├─ Task 2.3: 配置 hooks
        └─ Task 2.4: 更新工作流规则章节
           └─ Phase 3 (串行，依赖 Phase 2)
              ├─ Task 3.1: 审计 memory 文件
              ├─ Task 3.2: 合并 project memory
              ├─ Task 3.3: 补充 feedback memory
              ├─ Task 3.4: 建立知识分层规则
              └─ Task 3.5: 更新 MEMORY.md
```

---

## 风险点清单

| 阶段 | 风险 | 影响 | 缓解措施 |
|------|------|------|----------|
| Phase 1 | 子项目文档内容不一致 | 中 | 先建立统一模板，再填充内容 |
| Phase 1 | live-monitor/live-stream 架构不熟悉 | 高 | 先读代码（main.py、README），再写文档 |
| Phase 2 | Hooks 配置复杂度高 | 中 | 先实现 skill，hooks 作为可选增强 |
| Phase 2 | Skill 触发条件不明确 | 低 | 参考现有 skills（claude-md-improver）设计 |
| Phase 3 | 合并 memory 时丢失关键信息 | 高 | 先备份，逐条迁移并验证 |
| Phase 3 | 知识分层规则难以落地 | 中 | 参考 references/ 现有实践，提炼规则 |

---

## 详细任务步骤

### Task 1.1: 创建 live-monitor/CLAUDE.md

**Files:**
- Create: `services/live-monitor/CLAUDE.md`
- Read: `services/live-monitor/main.py`, `services/live-monitor/README.md`

- [ ] **Step 1: 读取 live-monitor 代码结构**

```bash
cd /Users/bw.xie/Documents/code/Tec-Do/VAT/live-platform/services/live-monitor
ls -la
cat main.py | head -50
```

Expected: 了解主备架构、房间检测、GMV 采集模块

- [ ] **Step 2: 创建 CLAUDE.md**

内容：
```markdown
# Live Monitor - 直播间监控服务

> 主备高可用架构，房间检测、状态管理、GMV 采集

## 架构概览
- **主备切换**：基于心跳检测
- **房间检测**：定时扫描直播间状态
- **GMV 采集**：实时采集 GMV 数据

## 关键文件
| 文件 | 职责 |
|------|------|
| `main.py` | 服务入口 |

## 启动命令
```bash
cd services/live-monitor && python main.py
```

## 测试命令
```bash
cd services/live-monitor && pytest tests/ -v
```
```

- [ ] **Step 3: Commit**

```bash
git add services/live-monitor/CLAUDE.md
git commit -m "docs(live-monitor): 添加 CLAUDE.md"
```

---

### Task 1.2: 创建 live-stream/CLAUDE.md

**Files:**
- Create: `services/live-stream/CLAUDE.md`

- [ ] **Step 1: 读取 live-stream 代码结构**

```bash
cd /Users/bw.xie/Documents/code/Tec-Do/VAT/live-platform/services/live-stream
ls -la && cat start.sh
```

- [ ] **Step 2: 创建 CLAUDE.md**

内容：
```markdown
# Live Stream - 直播流录制服务

> FFmpeg 推流、视频切割、OSS 上传

## 架构概览
- **FFmpeg 推流**：实时拉取直播流
- **视频切割**：按时间切割
- **OSS 上传**：上传到阿里云

## 启动命令
```bash
cd services/live-stream && bash start.sh
```
```

- [ ] **Step 3: Commit**

```bash
git add services/live-stream/CLAUDE.md
git commit -m "docs(live-stream): 添加 CLAUDE.md"
```

---

### Task 1.3: 修正根 CLAUDE.md 环境信息

**Files:**
- Modify: `CLAUDE.md:36`

- [ ] **Step 1: 修正环境信息**

将第 36 行：
```markdown
> **环境**：Windows 11 + CMD（.bat 启动）/ Git Bash（git 操作，使用 Unix 风格路径）。pytest 必须从各服务目录运行。
```

改为：
```markdown
> **环境**：macOS Darwin 25.3.0 + zsh。pytest 必须从各服务目录运行。
```

- [ ] **Step 2: 删除 Windows 特定章节**

删除第 94-99 行（gh CLI 路径问题章节）

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: 修正环境信息为 macOS"
```

---

### Task 1.4: 建立子项目 CLAUDE.md 模板

**Files:**
- Create: `.claude/templates/service-claude-md-template.md`

- [ ] **Step 1: 创建模板**

```markdown
# [Service Name] - [服务简介]

> [一句话描述]

## 架构概览
- **[模块]**：[职责]

## 关键文件
| 文件 | 职责 |
|------|------|
| `main.py` | [职责] |

## 启动命令
```bash
cd services/[name] && python main.py
```

## 特有约束
> 仅记录本服务特有约束，通用规则参考根 CLAUDE.md
```

- [ ] **Step 2: Commit**

```bash
git add .claude/templates/service-claude-md-template.md
git commit -m "docs: 添加子项目 CLAUDE.md 模板"
```

---

### Task 2.1: 分析现有工作流规则的触发条件

**Files:**
- Read: `CLAUDE.md:85-92`

- [ ] **Step 1: 列出现有工作流规则并识别可自动化规则**

可自动化：
- 规则 2：文件变更 → `/update-claude-md`
- 规则 5：commit 前 → hook 检查测试

- [ ] **Step 2: 设计触发条件表**

| 规则 | 触发方式 | 实现方式 |
|------|----------|----------|
| 规则 2 | 文件变更后 | Skill |
| 规则 5 | Pre-commit | Hook |

---

### Task 2.2: 创建 update-claude-md skill

**Files:**
- Create: `.claude/skills/update-claude-md/SKILL.md`

- [ ] **Step 1: 创建 skill**

```bash
mkdir -p /Users/bw.xie/.claude/skills/update-claude-md
cat > /Users/bw.xie/.claude/skills/update-claude-md/SKILL.md << 'SKILL'
---
name: update-claude-md
description: 文件变更后提示更新 CLAUDE.md
---

检测文件变更，提示更新 CLAUDE.md。

## 步骤
1. 运行 git status 检测新增/删除文件
2. 识别文件所属子项目
3. 提示更新"关键文件"章节
SKILL
```

- [ ] **Step 2: Commit**

```bash
git add .claude/skills/update-claude-md/
git commit -m "feat: 添加 update-claude-md skill"
```

---

### Task 2.3: 配置 hooks（可选）

**Files:**
- Create: `.claude/hooks/pre-commit-check-tests.sh`

- [ ] **Step 1: 创建 hook 脚本**

```bash
cat > .claude/hooks/pre-commit-check-tests.sh << 'HOOK'
#!/bin/bash
changed_files=$(git diff --cached --name-only | grep '\.py$' | grep -v 'test_')
if [ -n "$changed_files" ]; then
  test_files=$(git diff --cached --name-only | grep 'test_.*\.py$')
  if [ -z "$test_files" ]; then
    echo "⚠️  检测到代码变更但无测试文件"
    exit 1
  fi
fi
HOOK
chmod +x .claude/hooks/pre-commit-check-tests.sh
```

- [ ] **Step 2: Commit**

```bash
git add .claude/hooks/
git commit -m "feat: 添加 pre-commit hook"
```

---

### Task 2.4: 更新根 CLAUDE.md 工作流规则

**Files:**
- Modify: `CLAUDE.md:85-92`

- [ ] **Step 1: 更新工作流规则章节**

在规则 2 后添加：`运行 /update-claude-md 更新`
在规则 5 后添加：`（pre-commit hook 会检查）`

添加新章节：
```markdown
### 可用工具
- `/update-claude-md` - 文件变更后提示
- `/writing-plans` - 生成实施计划
```

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: 更新工作流规则"
```

---

### Task 3.1: 审计现有 memory 文件

**Files:**
- Read: memory 目录所有文件

- [ ] **Step 1: 识别问题**

问题清单：
1. 重复：project_overview + project_integration_background
2. 缺 feedback 类型
3. 过时：output_documents

- [ ] **Step 2: 制定合并计划**

目标 5 个文件：
1. user_profile.md
2. project_context.md（合并 overview + background）
3. core_technical_issues.md
4. ddd_architecture_decision.md
5. feedback.md（新增）

---

### Task 3.2: 合并 project 类型 memory

**Files:**
- Create: `memory/project_context.md`
- Delete: `project_overview.md`, `project_integration_background.md`

- [ ] **Step 1: 备份**

```bash
cd /Users/bw.xie/.claude/projects/-Users-bw-xie-Documents-code-Tec-Do-VAT-live-platform/memory
cp project_overview.md project_overview.md.bak
```

- [ ] **Step 2: 创建 project_context.md**

```markdown
---
name: 项目背景与整合动机
description: 四大模块来源、业务规模、整合原因
type: project
---

## 四大模块来源
| 模块 | 来源 | 职责 |
|------|------|------|
| 监控 | liveSpider_Serverv3 | 主备高可用 |
| 录制 | live-straem | FFmpeg 推流 |
| 浏览器 | adspower-server | CDP 投屏 |
| 采集 | live_dp | 双轨采集 |

## 整合原因
**Why:** 独立仓库导致依赖混乱
**How to apply:** 统一技术栈、共享基础设施
```

- [ ] **Step 3: 删除旧文件**

```bash
rm project_overview.md project_integration_background.md
rm monitoring_system_design_reference.md output_documents.md
```

---

### Task 3.3: 补充 feedback 类型 memory

**Files:**
- Create: `memory/feedback.md`

- [ ] **Step 1: 创建 feedback.md**

```markdown
---
name: 协作反馈与偏好
description: 文档管理、中文优先、类型提示风格
type: feedback
---

## 文档管理
**规则**：单一权威源
**Why**：避免副本不同步
**How to apply**：新增前先搜索

## 中文优先
**规则**：注释、commit 用中文
**Why**：降低理解成本
**How to apply**：技术术语保持英文

## 类型提示
**规则**：用 str | None
**Why**：Python 3.10+ 原生支持
**How to apply**：新代码一律用此风格
```

---

### Task 3.4: 建立知识分层决策规则

**Files:**
- Create: `.claude/references/knowledge-layering-rules.md`

- [ ] **Step 1: 创建规则文档**

```markdown
# 知识分层决策规则

## 三层体系
| 层级 | 位置 | 内容 | 更新频率 |
|------|------|------|----------|
| CLAUDE.md | 项目根/服务目录 | 结构/命令/规范 | 代码变更时 |
| Memory | ~/.claude/projects/.../memory/ | 背景/决策/反馈 | 跨会话积累 |
| References | .claude/references/ | 业务规则/接口规范 | 业务变更时 |

## 决策流程
新知识 → 判断类型
  ├─ 代码相关 → CLAUDE.md
  ├─ 跨会话上下文 → Memory
  └─ 业务规则 → References

## 示例
| 知识 | 位置 | 原因 |
|------|------|------|
| 启动命令 | CLAUDE.md | 代码相关 |
| 用户背景 | Memory | 跨会话 |
| Shopee 规则 | References | 业务规则 |
```

- [ ] **Step 2: Commit**

```bash
git add .claude/references/knowledge-layering-rules.md
git commit -m "docs: 添加知识分层规则"
```

---

### Task 3.5: 更新 MEMORY.md 索引

**Files:**
- Modify: `memory/MEMORY.md`

- [ ] **Step 1: 更新索引**

```markdown
- [用户背景](user_profile.md) — 开发者，Python/FastAPI，中文沟通
- [项目背景](project_context.md) — 四大模块来源、整合原因
- [核心技术问题](core_technical_issues.md) — P0 断流、P1 架构
- [DDD 架构](ddd_architecture_decision.md) — 4 个限界上下文
- [协作反馈](feedback.md) — 文档管理、中文优先、类型提示
```

- [ ] **Step 2: 清理备份**

```bash
rm /Users/bw.xie/.claude/projects/-Users-bw-xie-Documents-code-Tec-Do-VAT-live-platform/memory/*.bak
```

---

## 验收检查清单

### Phase 1
- [ ] 4 个子项目均有 CLAUDE.md
- [ ] 环境信息正确（macOS）
- [ ] 模板文件可复用

### Phase 2
- [ ] `/update-claude-md` skill 可用
- [ ] 工作流规则更新

### Phase 3
- [ ] Memory 文件数 = 5
- [ ] 知识分层规则文档化
- [ ] MEMORY.md 索引清晰

---

## Challenger 审查要点

1. **项目灵魂缺失**：✅ 4 个子项目有 CLAUDE.md，知识分层清晰
2. **进度跟踪**：✅ skill + hooks 自动化
3. **Memory ≤5**：✅ 5 个文件
4. **知识分层规则**：✅ knowledge-layering-rules.md

