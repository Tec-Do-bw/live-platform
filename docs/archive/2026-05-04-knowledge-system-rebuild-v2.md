# 项目知识体系重建实施方案 v2

> 基于 Scout 4 维度审计报告，优先处理高价值低成本项

## 方案原则

1. **高价值低成本优先**：删除重复、修正过时信息
2. **单人开发者友好**：无需 PR 流程、Issue 系统，直接 commit
3. **渐进式改进**：分 3 阶段，每阶段独立可验收
4. **务实可执行**：所有任务 ≤30 分钟

---

## Phase 1: 快速清理（高价值低成本）

**目标**：删除重复、修正过时信息、补全缺失文档

**预计时间**：1-2 小时

### Task 1.1: 修正根 CLAUDE.md 环境信息

- [ ] 删除第 94-99 行（gh CLI Windows 特定章节）
- [ ] 修改第 36 行环境描述：`Windows 11 + CMD` → `macOS Darwin 25.3.0 + zsh`
- [ ] Commit: `docs: 修正环境信息为 macOS`

**验收**：根 CLAUDE.md 环境描述与实际一致

---

### Task 1.2: 补全 P0 服务 CLAUDE.md

- [ ] 创建 `services/live-monitor/CLAUDE.md`（参考 live-crawler/CLAUDE.md 结构）
  - 架构概览：主备高可用、房间检测、GMV 采集
  - 启动命令：`cd services/live-monitor && python main.py`
  - 健康检查：`curl http://localhost:8080/health`
- [ ] 创建 `services/live-stream/CLAUDE.md`
  - 架构概览：FFmpeg 推流、视频切割、OSS 上传
  - 启动命令：`cd services/live-stream && bash start.sh`
- [ ] Commit: `docs: 补全 live-monitor 和 live-stream CLAUDE.md`

**验收**：4 个子项目均有 CLAUDE.md

---

### Task 1.3: 删除 AGENTS.md 重复文件

- [ ] 对比 `AGENTS.md` 和 `CLAUDE.md` 内容
- [ ] 将 AGENTS.md 独有的"调用点表格"迁移到 CLAUDE.md
- [ ] 删除 `AGENTS.md` 和 `services/live-crawler/AGENTS.md`
- [ ] Commit: `docs: 删除 AGENTS.md 重复文件`

**验收**：无 AGENTS.md 文件，CLAUDE.md 包含所有必要信息

---

### Task 1.4: 引用未使用的 references 文件

- [ ] 在根 CLAUDE.md 第 14-17 行添加：
  ```markdown
  - 登出恢复流程：`logout-recovery-flow.md`
  - 补采 HTTP 规格：`recrawl-http-spec.md`
  ```
- [ ] Commit: `docs: 引用 logout-recovery-flow 和 recrawl-http-spec`

**验收**：所有 references 文件被引用

---

### Task 1.5: 删除孤岛文档

- [ ] 检查 `docs/archive/AI-Coding执行流程手册.md` 是否有引用
- [ ] 若无引用，移动到 `docs/archive/`
- [ ] Commit: `docs: 归档孤岛文档 AI-Coding执行流程手册.md`

**验收**：无未被引用的活跃文档

---

## Phase 2: Memory 精简（中价值中成本）

**目标**：Memory 文件数从 8 个精简到 5 个

**预计时间**：1 小时

### Task 2.1: 合并 project 类型 memory

- [ ] 备份现有文件：
  ```bash
  cd /Users/bw.xie/.claude/projects/-Users-bw-xie-Documents-code-Tec-Do-VAT-live-platform/memory
  cp project_overview.md project_overview.md.bak
  cp project_integration_background.md project_integration_background.md.bak
  ```
- [ ] 创建 `project_context.md`（合并 overview + background）：
  ```markdown
  ---
  name: 项目背景与整合动机
  description: 四大模块来源、业务规模、整合原因
  type: project
  ---
  
  ## 四大模块来源
  | 模块 | 来源仓库 | 职责 |
  |------|----------|------|
  | 直播间监控 | liveSpider_Serverv3 | 主备高可用，房间检测、GMV 采集 |
  | 直播流录制 | live-straem | FFmpeg 推流、视频切割、OSS 上传 |
  | 浏览器管理 | livelab/adspower-server | AdsPower 管理、CDP 投屏 |
  | 数据采集 | livelab/live_dp | TikTok/Shopee/Lazada 双轨采集 |
  
  ## 业务规模
  - 监控 100+ 直播间
  - 日均采集 10K+ 商品数据
  - 支持 TikTok/Shopee/Lazada 三平台
  
  ## 整合原因
  **Why:** 四个独立仓库导致依赖管理混乱、部署复杂、代码复用困难
  
  **How to apply:** 
  - 统一技术栈（Python 3.12 + FastAPI）
  - 共享基础设施（Kafka、OSS）
  - 统一监控与日志
  ```
- [ ] 删除旧文件：`rm project_overview.md project_integration_background.md`

**验收**：project_context.md 包含所有关键信息

---

### Task 2.2: 删除可推断的 memory

- [ ] 删除 `output_documents.md`（文档路径可从代码推断）
- [ ] 删除备份文件：`rm *.bak`

**验收**：删除 1 个 memory 文件

---

### Task 2.3: 修正 memory 类型错误

- [ ] 修改 `ddd_architecture_decision.md` frontmatter：
  ```markdown
  ---
  name: DDD 架构设计决策
  description: 4 个限界上下文及职责边界
  type: project
  ---
  ```

**验收**：所有 memory 文件 type 正确

---

### Task 2.4: 补充 feedback 类型 memory

- [ ] 创建 `feedback.md`：
  ```markdown
  ---
  name: 协作反馈与偏好
  description: 文档管理、中文优先、类型提示风格
  type: feedback
  ---
  
  ## 文档管理
  **规则**：单一权威源，每份文档只在一个位置维护
  **Why**：避免副本不同步导致信息冲突
  **How to apply**：新增文档前先搜索是否已存在，需要引用时用路径不复制内容
  
  ## 中文优先
  **规则**：所有代码注释、docstring、commit message 使用中文（技术术语保持英文）
  **Why**：团队中文沟通，降低理解成本
  **How to apply**：函数注释用中文描述职责，commit message 用中文（如 `feat: 添加 XXX 功能`）
  
  ## 类型提示风格
  **规则**：Python 3.12 使用 `str | None` 风格，不用 `Optional[str]`
  **Why**：Python 3.10+ 原生支持，更简洁
  **How to apply**：新代码一律用 `str | None`，重构时顺手改旧代码
  ```

**验收**：有 feedback 类型 memory

---

### Task 2.5: 更新 MEMORY.md 索引

- [ ] 修正重复条目（team_squad_config.md 只保留一条）
- [ ] 更新索引为 5 个文件：
  ```markdown
  - [用户背景](user_profile.md) — 直播平台开发者，Python/FastAPI 技术栈，中文沟通
  - [项目背景与整合动机](project_context.md) — 四大模块来源、业务规模、整合原因
  - [核心技术问题与优先级](core_technical_issues.md) — P0 断流问题、P1 架构优化
  - [DDD 架构设计决策](ddd_architecture_decision.md) — 4 个限界上下文及职责边界
  - [协作反馈与偏好](feedback.md) — 文档管理、中文优先、类型提示风格
  ```

**验收**：MEMORY.md 索引清晰，无重复条目，每条 ≤150 字符

---

## Phase 3: 知识分层规则（中价值高成本）

**目标**：建立清晰的知识分层决策规则

**预计时间**：30 分钟

### Task 3.1: 创建知识分层决策规则文档

- [ ] 创建 `.claude/references/knowledge-layering-rules.md`：
  ```markdown
  # 知识分层决策规则
  
  ## 三层知识体系
  
  | 层级 | 位置 | 内容 | 更新频率 | 示例 |
  |------|------|------|----------|------|
  | **CLAUDE.md** | 项目根目录 + 各服务目录 | 项目结构、技术栈、命令、代码规范 | 代码变更时 | 服务启动命令、测试命令 |
  | **Memory** | `~/.claude/projects/.../memory/` | 用户背景、项目背景、技术决策、协作反馈 | 跨会话积累 | 用户是数据科学家、DDD 架构决策 |
  | **References** | `.claude/references/` | 业务规则、接口规范、对接文档 | 业务变更时 | Shopee 登出恢复流程、补采 HTTP 规格 |
  
  ## 决策流程图
  
  ```
  新知识 → 判断类型
    ├─ 代码相关（结构/命令/规范）→ CLAUDE.md
    ├─ 跨会话上下文（背景/决策/反馈）→ Memory
    └─ 业务规则（接口/流程/规范）→ References
  ```
  
  ## 冲突处理
  
  - **CLAUDE.md vs Memory**：CLAUDE.md 记录"是什么"，Memory 记录"为什么这样设计"
  - **References vs Memory**：References 记录业务规则（外部约束），Memory 记录技术决策（内部选择）
  - **重复内容**：优先保留在最常查阅的位置，其他位置通过路径引用
  
  ## 反例（避免）
  
  | 错误做法 | 正确做法 |
  |----------|----------|
  | 在 CLAUDE.md 和 Memory 中重复记录四大模块来源 | CLAUDE.md 记录表格，Memory 记录整合动机 |
  | 在多个 references 文件中重复登出恢复流程 | 统一到 logout-recovery-flow.md，其他文件引用 |
  | 在 Memory 中记录服务启动命令 | 启动命令属于代码相关，应在 CLAUDE.md |
  ```
- [ ] Commit: `docs: 添加知识分层决策规则`

**验收**：有清晰的知识分层决策规则文档

---

### Task 3.2: 在根 CLAUDE.md 中引用知识分层规则

- [ ] 在根 CLAUDE.md "文档管理规则"章节末尾添加：
  ```markdown
  - **知识分层规则**：参考 `.claude/references/knowledge-layering-rules.md` 决定信息应放在哪一层
  ```
- [ ] Commit: `docs: 在 CLAUDE.md 中引用知识分层规则`

**验收**：根 CLAUDE.md 引用知识分层规则

---

## Phase 4: 进度跟踪优化（低价值，可选）

**目标**：建立轻量级进度跟踪机制（单人开发者友好）

**预计时间**：30 分钟（可选）

### Task 4.1: 归档未勾选的历史计划

- [ ] 将 91 个未勾选 checkbox 的计划文件移到 `docs/archive/`
- [ ] 在文件头部添加归档说明：
  ```markdown
  > **归档原因**：部分功能已实现但未勾选，计划已过时。实际实现状态参考代码。
  ```
- [ ] Commit: `docs: 归档未勾选的历史计划`

**验收**：活跃计划文件 ≤2 个

---

### Task 4.2: 建立轻量级进度跟踪规则

- [ ] 在根 CLAUDE.md "工作流规则"章节添加：
  ```markdown
  7. **进度跟踪**（单人开发者模式）：
     - 新功能：在 `docs/plans/` 创建计划文件，完成后移到 `docs/archive/`
     - Bug 修复：直接 commit，message 中说明问题和解决方案
     - 不使用 GitHub Issues（单人开发无需 Issue 系统）
  ```
- [ ] Commit: `docs: 添加单人开发者进度跟踪规则`

**验收**：有明确的进度跟踪规则

---

## 验收检查清单

### Phase 1: 快速清理
- [ ] 根 CLAUDE.md 环境信息正确（macOS）
- [ ] 4 个子项目均有 CLAUDE.md
- [ ] 无 AGENTS.md 重复文件
- [ ] 所有 references 文件被引用
- [ ] 无孤岛文档

### Phase 2: Memory 精简
- [ ] Memory 文件数 = 5
- [ ] 所有 memory 文件 type 正确
- [ ] MEMORY.md 索引清晰，无重复

### Phase 3: 知识分层规则
- [ ] 有知识分层决策规则文档
- [ ] 根 CLAUDE.md 引用知识分层规则

### Phase 4: 进度跟踪优化（可选）
- [ ] 历史计划已归档
- [ ] 有单人开发者进度跟踪规则

---

## 预计总时间

- Phase 1: 1-2 小时
- Phase 2: 1 小时
- Phase 3: 30 分钟
- Phase 4: 30 分钟（可选）

**总计**：2.5-4 小时

---

## Challenger 审查要点

1. **是否解决"项目灵魂缺失"**：
   - ✅ 4 个子项目有 CLAUDE.md
   - ✅ 知识分层清晰（CLAUDE.md / Memory / References）
   - ✅ 无重复文档

2. **进度跟踪机制是否可持续**：
   - ✅ 单人开发者友好（无需 Issue 系统）
   - ✅ 轻量级规则（计划文件 + commit message）

3. **Memory 文件数是否 ≤5**：
   - ✅ 5 个文件（user_profile、project_context、core_technical_issues、ddd_architecture_decision、feedback）

4. **是否有清晰的知识分层决策规则**：
   - ✅ `.claude/references/knowledge-layering-rules.md`
   - ✅ 决策流程图 + 示例 + 冲突处理

---

