# 项目知识体系重建 — 分阶段实施方案

> **状态**：待 Challenger 复审
> **日期**：2026-05-04
> **作者**：planner
> **目标**：解决"项目灵魂缺失"——让 Claude Code 在任何 session 都能快速理解项目全貌，做出正确决策

---

## 一、现状诊断摘要

| 问题 | 严重度 | 现状 |
|------|--------|------|
| 2 个 P0 服务（live-monitor、live-stream）无 CLAUDE.md | **高** | Claude 对这两个核心服务完全无上下文 |
| 根 CLAUDE.md 环境信息过时 | **中** | 写的 Windows 11，实际 macOS Darwin |
| 工作流规则不可执行 | **中** | 6 条规则全是散文，无触发机制 |
| `.claude/rules/` 不存在 | **中** | 官方规则引擎完全未启用 |
| `.claude/settings.json` 不存在 | **低** | 无 hooks、无权限配置 |
| Memory 9 个文件（目标 ≤5） | **中** | 有重复、类型错误、缺 feedback |
| `.claude/docs/` 3 个文件未被引用 | **低** | 孤立知识，不产生价值 |

---

## 二、知识分层决策规则

> **核心原则**：每条知识只放一个地方，放在最合适的层级。

```
┌─────────────────────────────────────────────────────────┐
│  层级 1: CLAUDE.md（项目灵魂）                            │
│  放什么：项目定位、技术栈、目录结构、启动命令、代码规范      │
│  特征：每次 session 自动加载，必须精简                      │
├─────────────────────────────────────────────────────────┤
│  层级 2: .claude/rules/（可执行规则）                      │
│  放什么：必须强制执行的行为约束                              │
│  特征：条件触发，自动注入上下文，替代 CLAUDE.md 中的散文规则  │
├─────────────────────────────────────────────────────────┤
│  层级 3: .claude/references/（业务规则参考）                │
│  放什么：复杂业务逻辑、接口规格、平台特殊规则                │
│  特征：按需读取，CLAUDE.md 中用路径引用                     │
├─────────────────────────────────────────────────────────┤
│  层级 4: Memory（跨 session 记忆）                         │
│  放什么：用户偏好、项目动态、外部引用、行为反馈              │
│  特征：不放代码可推导的信息，不放 CLAUDE.md 已有的信息       │
│  硬约束：≤5 个文件                                         │
├─────────────────────────────────────────────────────────┤
│  层级 5: docs/（人类文档）                                 │
│  放什么：PRD、设计方案、实施计划                            │
│  特征：给人看的，Claude 按需读取                            │
└─────────────────────────────────────────────────────────┘
```

**决策流程图**（一条知识该放哪里）：

```
这条知识是...
├─ 每次 session 都需要？ → CLAUDE.md
├─ 必须强制执行的行为约束？ → .claude/rules/
├─ 复杂业务逻辑/接口规格？ → .claude/references/
├─ 跨 session 需要记住的动态信息？ → Memory
├─ 给人看的长文档？ → docs/
└─ 代码/git 可推导？ → 不存储
```

---

## 三、分阶段实施计划

### Phase 1：地基修复（CLAUDE.md 增强）

> **目标**：让 Claude 在任何 session 对所有 4 个服务都有基本上下文
> **预计工作量**：中等
> **可并行**：1A/1B/1C 三个任务互不依赖

#### 任务 1A：修正根 CLAUDE.md

- [ ] 环境信息从 `Windows 11 + CMD` 改为 `macOS Darwin + zsh`
- [ ] 删除 `gh CLI 路径问题` 章节（Windows 特有，不再适用）
- [ ] 工作流规则章节标注"详见 `.claude/rules/`"（Phase 2 创建后回填）
- [ ] 验证 `.claude/references/` 引用列表与实际文件一致（当前缺 `recrawl-http-spec.md` 和 `logout-recovery-flow.md` 的引用）

**验收标准**：根 CLAUDE.md 中无过时环境信息，references 引用完整

#### 任务 1B：补建 live-monitor CLAUDE.md

参照 `services/adspower-server/CLAUDE.md` 的结构（已验证为优秀模板）：

- [ ] 项目定位（主备高可用直播间监控）
- [ ] 目录结构（读代码生成）
- [ ] 运行命令（`python main.py`，健康检查 `curl localhost:8080/health`）
- [ ] 核心架构（主备切换、房间检测、状态管理、GMV 采集）
- [ ] API 接口清单（`/get_roominfo` 等关键接口）
- [ ] 必须遵守的规则（与 live-stream 的交互契约、主备切换逻辑）
- [ ] 首行写 `> 通用编码规范见根目录 CLAUDE.md。以下仅记录 live-monitor 特有规则。`

**验收标准**：新 session 中 Claude 能正确描述 live-monitor 的架构和关键接口

#### 任务 1C：补建 live-stream CLAUDE.md

同样参照 adspower-server 模板：

- [ ] 项目定位（FFmpeg 推流录制，防摸鱼视频）
- [ ] 目录结构（读代码生成）
- [ ] 运行命令（`bash start.sh`）
- [ ] 核心架构（FFmpeg 推流、断流重连、视频切割、OSS 上传）
- [ ] P0 断流问题的已知约束（超时参数、重连机制、健康检查间隔）
- [ ] 与 live-monitor 的交互规则（轮询 `/get_roominfo`）
- [ ] 首行写 `> 通用编码规范见根目录 CLAUDE.md。以下仅记录 live-stream 特有规则。`

**验收标准**：新 session 中 Claude 能正确描述断流问题的根因和重连机制

---

### Phase 2：规则引擎启用（工作流可执行化）

> **目标**：将散文规则转为可触发的 `.claude/rules/` 文件
> **前置依赖**：Phase 1A 完成（根 CLAUDE.md 已修正）
> **预计工作量**：中等

#### 任务 2A：创建 `.claude/rules/` 规则文件

将根 CLAUDE.md 中 6 条工作流规则拆分为独立规则文件：

| 规则文件 | 触发条件 | 内容 |
|----------|----------|------|
| `read-before-write.md` | 编辑 `services/*/` 下文件时 | 先读对应子项目 CLAUDE.md |
| `update-docs-on-structure-change.md` | 新增/删除文件时 | 更新对应 CLAUDE.md 架构章节 |
| `chinese-comments.md` | 写代码时 | 注释、docstring、commit message 用中文 |
| `test-before-done.md` | 完成实现时 | 必须运行 pytest 验证 |
| `single-source-of-truth.md` | 创建/编辑文档时 | 禁止复制副本，用路径引用 |

- [ ] 创建上述 5 个规则文件
- [ ] 根 CLAUDE.md 工作流章节精简为"详见 `.claude/rules/`"+ 规则文件列表

**验收标准**：`.claude/rules/` 目录包含 5 个规则文件，每个文件有明确的触发条件描述

#### 任务 2B：清理 `.claude/docs/` 孤立文件

- [ ] 评估 `psb-workflow.md`、`claude-code-best-practices.md`、`prompting-patterns.md` 是否仍有价值
- [ ] 有价值的内容合并到对应 CLAUDE.md 或 rules 中
- [ ] 无价值的移入 `docs/archive/`
- [ ] 确保 `.claude/docs/` 不再有孤立文件

**验收标准**：`.claude/docs/` 中每个文件都被某个 CLAUDE.md 或 rule 引用，或已归档

#### 任务 2C：补全 references 引用

- [ ] 根 CLAUDE.md 的 references 列表补充 `recrawl-http-spec.md` 和 `logout-recovery-flow.md`
- [ ] 确认 5 个 references 文件内容与实际业务逻辑一致

**验收标准**：根 CLAUDE.md 中 references 列表与 `.claude/references/` 目录完全一致

---

### Phase 3：Memory 瘦身（≤5 个文件）

> **目标**：从 9 个文件精简到 ≤5 个，修正类型错误，补充 feedback
> **前置依赖**：Phase 1 完成（CLAUDE.md 已承接部分知识）
> **预计工作量**：小

#### 任务 3A：合并与删除

当前 9 个文件的处置方案：

| 文件 | 处置 | 理由 |
|------|------|------|
| `user_profile.md` | **保留** | 用户背景，不可从代码推导 |
| `project_overview.md` | **删除** | 与 `project_integration_background.md` 高度重复，且 CLAUDE.md 已有子项目表 |
| `project_integration_background.md` | **保留，精简** | 保留业务规模、核心流程等 CLAUDE.md 未覆盖的动态信息 |
| `core_technical_issues.md` | **保留，更新** | P0/P1 优先级是动态信息，但需检查是否已过时 |
| `ddd_architecture_decision.md` | **修正类型** feedback→project，**保留** | DDD 决策是项目级信息 |
| `monitoring_system_design_reference.md` | **删除** | 纯路径引用，CLAUDE.md 或 references 可承接 |
| `output_documents.md` | **删除** | 文档路径可从 `docs/` 目录推导 |
| `team_squad_config.md` | **保留** | 团队配置需跨 session 持久化 |

- [ ] 删除 `project_overview.md`（与 integration_background 重复）
- [ ] 删除 `monitoring_system_design_reference.md`（纯路径引用）
- [ ] 删除 `output_documents.md`（可从 docs/ 推导）
- [ ] 修正 `ddd_architecture_decision.md` 的 type: feedback → project
- [ ] 精简 `project_integration_background.md`，去除与 CLAUDE.md 重复的内容

**结果**：5 个文件 — `user_profile` / `project_integration_background` / `core_technical_issues` / `ddd_architecture_decision` / `team_squad_config`

#### 任务 3B：补充 feedback 类型 Memory

当前 0 个 feedback 记忆。从已知信息中提取：

- [ ] 创建 1 个 feedback memory，合并以下已确认的行为偏好：
  - 中文沟通、中文注释（已在 CLAUDE.md 但属于用户偏好）
  - 先 Plan 再编码（用户确认的工作方式）
  - 单一 PR 优于拆分（如适用）

**注意**：feedback 文件内容必须来自用户实际确认的偏好，不可臆造

#### 任务 3C：更新 MEMORY.md 索引

- [ ] 重写 MEMORY.md，仅保留 ≤5 个文件的索引
- [ ] 去除重复条目（当前 team_squad_config 出现两次）
- [ ] 每行 <150 字符

**验收标准**：MEMORY.md 索引 ≤5 条，无重复，每条 <150 字符

---

### Phase 4：验证与收尾

> **目标**：确认整个知识体系可用
> **前置依赖**：Phase 1-3 全部完成

#### 任务 4A：端到端验证

- [ ] 模拟新 session：Claude 能否正确描述 4 个服务的架构？
- [ ] 模拟编辑场景：编辑 live-monitor 代码时，rules 是否提示先读 CLAUDE.md？
- [ ] 模拟知识查找：问"断流问题怎么解决"，Claude 能否定位到 live-stream CLAUDE.md + references？

#### 任务 4B：提交 PR

- [ ] 所有变更提交到 `refactor/docs-consolidation` 分支
- [ ] PR 描述包含变更清单和验证结果

**验收标准**：PR 通过 reviewer 审查

---

## 四、任务依赖图

```
Phase 1（地基修复）          Phase 2（规则引擎）       Phase 3（Memory 瘦身）    Phase 4
┌──────┐                   ┌──────┐                 ┌──────┐
│  1A  │──────────────────→│  2A  │                 │  3A  │
│根 MD │                   │rules │                 │合并删│
└──────┘                   └──────┘                 └──────┘
┌──────┐                   ┌──────┐                 ┌──────┐
│  1B  │                   │  2B  │                 │  3B  │
│monitor│                  │清理  │                 │补feedback│
└──────┘                   └──────┘                 └──────┘
┌──────┐                   ┌──────┐                 ┌──────┐              ┌──────┐
│  1C  │                   │  2C  │                 │  3C  │─────────────→│  4A  │
│stream│                   │补引用│                 │更新索引│             │验证  │
└──────┘                   └──────┘                 └──────┘              └──────┘
                                                                          ┌──────┐
                                                                          │  4B  │
                                                                          │提交PR│
                                                                          └──────┘

并行关系：
  - 1A / 1B / 1C 可完全并行
  - 2A 依赖 1A；2B / 2C 可与 2A 并行
  - 3A / 3B / 3C 依赖 Phase 1 完成（知识迁移后才能安全删除 Memory）
  - Phase 3 与 Phase 2 可并行
  - 4A 依赖 Phase 1-3 全部完成
  - 4B 依赖 4A
```

---

## 五、风险清单

| # | 风险 | 影响 | 概率 | 缓解措施 |
|---|------|------|------|----------|
| R1 | live-monitor/live-stream 代码结构不清晰，CLAUDE.md 写出来不准确 | 高 | 中 | architect 读代码生成，reviewer 交叉验证 |
| R2 | `.claude/rules/` 触发条件写法不对，规则不生效 | 中 | 中 | Phase 4 验证环节专门测试规则触发 |
| R3 | Memory 删除后丢失有价值信息 | 中 | 低 | 删除前确认信息已迁移到 CLAUDE.md 或 references |
| R4 | feedback memory 内容臆造（非用户实际确认） | 中 | 中 | 仅从对话历史中提取用户明确确认的偏好，不确定的不写 |
| R5 | 根 CLAUDE.md 修改影响现有工作流 | 低 | 低 | 只做修正和精简，不改变已有的正确内容 |
| R6 | `.claude/docs/` 文件归档后被其他流程依赖 | 低 | 低 | 归档前 grep 全项目确认无引用 |

---

## 六、进度跟踪机制

1. **任务粒度**：每个子任务（1A/1B/...）对应一个 Task，完成即标记
2. **门禁检查**：
   - Phase 1 完成后 → reviewer 检查 4 个 CLAUDE.md 的一致性
   - Phase 2 完成后 → 验证 rules 文件格式正确
   - Phase 3 完成后 → 确认 MEMORY.md ≤5 条
   - Phase 4 → challenger 做最终验收
3. **回滚策略**：所有变更在 `refactor/docs-consolidation` 分支，不影响 main
