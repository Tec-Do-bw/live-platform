# Rules 改造方案与上下文加载指引

**编制日期**：2026-05-20  
**依据**：《现状报告.md》、《方法论摘要.md》、`.claude/rules/` 现状  
**整顿方案交叉检查**：任务 8 尚未交付，暂无矛盾点可标注

---

## 一、4 个 rules 的 paths frontmatter 设计

### 现状确认

4 个 rules 文件**均已有** paths frontmatter（现状报告第 109 行确认）。以下为现状与改造对比。

---

### 1. `read-before-write.md` — 编辑前必读子项目 CLAUDE.md

**现状 paths**：
```yaml
paths:
  - "services/**/*.py"
  - "services/**/*.ts"
  - "services/**/*.vue"
```

**改造 paths**：保持不变（无需修改）

**理由**（回应 DA#2、DA#6）：
- ~~原提议新增 `services/**/*.js`~~：撤回。本项目前端使用 Vite，构建配置为 `vite.config.ts`（已被 `*.ts` 覆盖）。`services/` 下 `.js` 文件主要是 `node_modules/` 依赖和编译产物，编辑场景极为罕见，无法举出具体的 `.js` 编辑需要先读 CLAUDE.md 的场景。
- ~~原提议新增 `services/**/Dockerfile` / `docker-compose*.yml`~~：撤回。规则正文指向 CLAUDE.md，但 CLAUDE.md 无 Docker 相关约束。触发后「加载了但没用」，属于 token 浪费。如未来需要「编辑部署配置前先读上下文」，应新建独立规则指向部署文档。
- 不加 `services/**/*.md`：文档编辑由 `single-source-of-truth.md` 覆盖，避免重叠

**援引依据**：采纳《方法论摘要》第 a 条「避免过宽的根匹配」+ 反例条款 3「触发了但无法产生有效行动」的精神

---

### 2. `update-docs-on-structure-change.md` — 结构变更更新 README

**现状 paths**：
```yaml
paths:
  - "services/**/*.py"
  - "services/**/*.ts"
  - "services/**/*.vue"
  - "services/**/README.md"
```

**改造 paths**：保持不变（无需修改）

**理由**：
- 当前 glob 已精确覆盖源码文件 + README.md
- `README.md` 条目确保编辑 README 时也能看到此规则（自引用提醒）
- 不加 `*.js`：JS 文件变更极少涉及目录结构变化，加入会过度触发

**援引依据**：采纳《方法论摘要》第 a 条「避免过宽的根匹配」— 当前粒度已合适，不扩大

---

### 3. `chinese-comments.md` — 中文注释与提交信息

**现状 paths**：
```yaml
paths:
  - "**/*.py"
  - "**/*.ts"
  - "**/*.vue"
  - "**/*.js"
```

**改造 paths**：
```yaml
paths:
  - "**/*.py"
  - "**/*.ts"
  - "**/*.vue"
  - "**/*.js"
  - "**/*.sh"
```

**改造理由**：
- 新增 `*.sh`：shell 脚本中也有注释，应遵循中文规范
- 不加 `*.md`：markdown 文档不属于"代码注释"范畴，由 single-source-of-truth 管辖
- 不加 `*.yml`/`*.json`：配置文件注释极少，加入会过度触发

**援引依据**：采纳《方法论摘要》第 a 条「具体扩展名优先」+ 第 c 条拆分策略「按文件类型拆分，配合 paths frontmatter」

---

### 4. `single-source-of-truth.md` — 单一权威源原则

**现状 paths**：
```yaml
paths:
  - "**/*.md"
  - "**/docs/**/*"
  - "**/.claude/**/*"
```

**改造 paths**：保持不变（无需修改）

**理由**（回应 DA#5）：
- `**/*.md` 已完整覆盖所有 CLAUDE.md 文件，无需额外添加 `**/CLAUDE.md`（冗余条目违反方法论第 a 条「glob 列表应精确且无冗余」）
- `**/docs/**/*` 覆盖所有文档目录
- `**/.claude/**/*` 覆盖所有 Claude 配置文件
- 三条 glob 组合已完整覆盖所有文档场景，粒度合适

**援引依据**：采纳《方法论摘要》第 a 条「避免过宽的根匹配」— `**/*.md` 是文档规则的合理粒度

---

## 二、上下文按需加载指引（回应 DA#3）

> **修正说明**：原方案提议将指引表格直接粘贴到根 CLAUDE.md 末尾。DA#3 指出这与既有「工作流规则」表格存在重叠，违反 single-source-of-truth 规则，且膨胀根文件（113→133 行）。接受此反对意见，改为独立文件方案。

### 修正后方案

1. **创建独立文件**：`.claude/docs/context-loading-guide.md`
2. **根 CLAUDE.md 仅加一行引用**（插入「文档管理规则」段末尾）：
   ```markdown
   - **上下文加载策略**：详见 `.claude/docs/context-loading-guide.md`
   ```

### `.claude/docs/context-loading-guide.md` 内容草案

```markdown
# 上下文按需加载指引

> 原则：能用 paths 路径作用域确定性触发的，绝不依赖自然语言判断。
> 子项目 CLAUDE.md 由 Claude 懒加载机制自动触发，无需 @import。

## 任务场景 → 应读文档映射

| 任务场景 | 应先读取的文档 | 触发方式 |
|----------|---------------|----------|
| 编辑某服务代码 | `services/<服务名>/CLAUDE.md` | 自动（懒加载） |
| 修改采集业务逻辑 | `.claude/references/` 下对应规则文件 | 手动读取 |
| 修改文档 | 根 CLAUDE.md「文档管理规则」段 | 自动（rule 触发） |
| 修改 rules 文件 | `.claude/rules/` 下目标文件 + 本指引 | 手动读取 |
| 跨服务联调 | 两端服务的 CLAUDE.md + 根 CLAUDE.md「子项目」表 | 手动读取 |
| 调试某 bug | 对应服务 CLAUDE.md + `docs/designs/` 相关设计文档 | 手动读取 |
| 新增服务/模块 | 根 CLAUDE.md 全文 + 最相似服务的 CLAUDE.md | 手动读取 |
| 部署/运维操作 | `services/<服务名>/docs/specs/deployment-guide.md` | 手动读取 |
| 查看历史决策 | `docs/designs/` 或 `docs/archive/` 下对应文档 | 手动读取 |

## 懒加载说明

- **自动触发**：Claude 读取 `services/X/` 下任何文件时，`services/X/CLAUDE.md` 自动加载
- **手动触发**：在对话中指示「请先读 XXX」或由 `.claude/rules/` 的 paths 匹配触发
- **不 @import 子 CLAUDE.md**：避免启动时全部展开消耗 token（详见 rules-改造方案.md 第三节）

## 与根 CLAUDE.md「工作流规则」表格的关系

根 CLAUDE.md 的「工作流规则」表格描述 rules 的触发条件和核心要求（面向规则维护者）。
本文件描述任务场景到文档的映射关系（面向任务执行者）。两者视角不同，不构成重复。
```

---

## 三、为何不 @import 子 CLAUDE.md

**结论**：根 CLAUDE.md 不应 @import 任何子项目 CLAUDE.md。

**援引依据**：《方法论摘要》第 b 条「懒加载 vs 强制加载的决策矩阵」：

> | 场景 | 选择 | 理由 |
> |------|------|------|
> | 模块级背景知识 | 懒加载 | 仅当读该模块文件时触发，节省 token |

**具体论证**：

1. **token 经济性**：本项目 5 个子 CLAUDE.md 合计 206 行。若全部 @import，根文件启动时展开为 319 行（含根自身 113 行），远超 200 行危险阈值（方法论第 c 条：> 200 行遵从度 < 60%）

2. **任务相关性低**：绝大多数任务只涉及 1 个服务。@import 5 个子文件意味着 80% 的内容是噪音

3. **懒加载已足够**：Claude 读取 `services/X/` 下文件时自动加载 `services/X/CLAUDE.md`，无需人工干预

4. **paths 规则兜底**：`read-before-write.md` 的 paths 确保编辑服务代码时提醒先读 CLAUDE.md，形成双重保障

**反例参照**：方法论「反例 1：过度 @import」明确指出——
> 启动时全部展开，token 消耗翻倍；大多数任务只需要其中 1-2 个模块，其他都是噪音；遵从度反而下降

---

## 四、漏触发/过度触发风险自检

### 4.1 `read-before-write.md`（保持不变，回应 DA#2、DA#6）

| paths glob | 可能漏触发 | 可能过度触发 |
|-----------|-----------|-------------|
| `services/**/*.py` | — | — |
| `services/**/*.ts` | — | — |
| `services/**/*.vue` | — | — |

**漏触发风险**：
- `services/**/*.js` 不触发 → 可接受（DA#6 论证：本项目前端配置为 ts，js 文件主要是依赖/产物）
- `services/**/*.json`（如 package.json）不触发 → 可接受，JSON 配置修改通常不需要读 CLAUDE.md
- `services/**/Dockerfile` 不触发 → 可接受（DA#2 论证：CLAUDE.md 无 Docker 约束，触发后无有效行动）

**过度触发风险**：低。所有 glob 限定在 `services/` 下，不影响根目录或 docs/ 操作。

---

### 4.2 `update-docs-on-structure-change.md`（保持不变）

| paths glob | 可能漏触发 | 可能过度触发 |
|-----------|-----------|-------------|
| `services/**/*.py` | — | 修改 py 内容（非新增/删除）也触发加载 |
| `services/**/*.ts` | — | 同上 |
| `services/**/*.vue` | — | 同上 |
| `services/**/README.md` | — | — |

**漏触发风险**：
- `services/` 下新增 `*.json`/`*.yml` 不触发 → 中等风险，但此类文件通常不需更新目录树

**过度触发风险**：中等。修改已有文件内容时也加载规则，但规则正文明确「新增、删除或重命名时」才需行动。paths 控制加载，正文控制执行——这是可接受的设计。

---

### 4.3 `chinese-comments.md`（改造后）

| paths glob | 可能漏触发 | 可能过度触发 |
|-----------|-----------|-------------|
| `**/*.py` | — | — |
| `**/*.ts` | — | — |
| `**/*.vue` | — | — |
| `**/*.js` | — | config 类 JS（如 vite.config.js） |
| `**/*.sh` | — | — |

**漏触发风险**：
- `Makefile` 不触发 → 可接受，本项目无 Makefile
- `*.yaml`/`*.toml` 不触发 → 可接受，配置文件注释极少

**过度触发风险**：低。`**/*.py` 等根级双星号匹配所有层级，这是预期行为——中文注释规范应全局生效。

---

### 4.4 `single-source-of-truth.md`（保持不变）

| paths glob | 可能漏触发 | 可能过度触发 |
|-----------|-----------|-------------|
| `**/*.md` | — | 所有 md 文件（含 CHANGELOG、README） |
| `**/docs/**/*` | — | docs/ 下非 md 文件（HTML、图片） |
| `**/.claude/**/*` | — | `.claude/settings.json` 等非文档文件 |

**漏触发风险**：无。三条 glob 已覆盖所有文档相关路径。

**过度触发风险**：中等但可接受。
- `.claude/settings.json` 编辑时触发 → 无害，规则正文限定了适用场景
- `docs/` 下图片查看时触发 → 极低概率
- 所有 md 文件编辑时触发 → 预期行为

---

## 总结

| 规则文件 | 改造动作 | 变更幅度 |
|----------|---------|---------|
| `read-before-write.md` | 保持不变（回应 DA#2、DA#6） | 无 |
| `update-docs-on-structure-change.md` | 保持不变 | 无 |
| `chinese-comments.md` | 新增 1 条 glob（sh） | 极小 |
| `single-source-of-truth.md` | 保持不变（回应 DA#5） | 无 |

**核心设计原则**：
1. 精确扩展名优先，拒绝 `**/*` 全匹配（采纳方法论第 a 条）
2. 子 CLAUDE.md 懒加载，不 @import（采纳方法论第 b 条）
3. 规则文件保持精简，paths 控制加载范围，正文控制执行条件（采纳方法论第 c 条）
4. 上下文加载指引独立为 `.claude/docs/context-loading-guide.md`，根 CLAUDE.md 仅加一行引用（回应 DA#3，遵守单一权威源）

**DA 回应汇总**：
| DA# | 反对意见 | 处置 |
|-----|---------|------|
| #2 | Dockerfile/docker-compose glob 过度触发 | 接受，撤回新增 |
| #3 | 按需加载指引违反单一权威源 | 接受，改为独立文件 |
| #5 | `**/CLAUDE.md` 语义噪音 | 接受，直接删除提议 |
| #6 | `*.js` glob 收益存疑 | 接受，撤回新增 |
