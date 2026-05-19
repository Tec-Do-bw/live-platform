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
- **不 @import 子 CLAUDE.md**：避免启动时全部展开消耗 token

## 与根 CLAUDE.md「工作流规则」表格的关系

根 CLAUDE.md 的「工作流规则」表格描述 rules 的触发条件和核心要求（面向规则维护者）。
本文件描述任务场景到文档的映射关系（面向任务执行者）。两者视角不同，不构成重复。
