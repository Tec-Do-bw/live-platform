# Claude Code 官方最佳实践

> 来源: https://code.claude.com/docs/zh-CN/best-practices

## 核心原则

**上下文窗口是最重要的资源。** 上下文填满时 LLM 性能会下降。所有最佳实践都围绕这一约束展开。

---

## 1. 给 Claude 验证方式（最高杠杆）

- 提供测试用例、屏幕截图或预期输出
- 让 Claude 能自我检查，而非依赖你做反馈循环
- UI 变更可用 Chrome 扩展验证

## 2. 先探索，再规划，再编码

四阶段工作流：
1. **探索** → Plan Mode 读取文件，不做更改
2. **规划** → 创建详细实现计划（Ctrl+G 可编辑计划）
3. **实现** → Normal Mode 编码并验证
4. **提交** → 描述性消息 + PR

> 小任务（拼写错误、重命名）跳过规划直接执行。

## 3. 提供具体上下文

- 引用具体文件、约束和示例模式
- 使用 `@` 引用文件
- 粘贴图像/截图
- 管道数据: `cat error.log | claude`

## 4. CLAUDE.md 编写规范

### 应包含
- Claude 无法猜测的 Bash 命令
- 与默认值不同的代码风格规则
- 测试指令和首选测试运行器
- 仓库礼仪（分支命名、PR 约定）
- 项目特定的架构决策
- 环境怪癖（必需的环境变量）
- 常见陷阱或非显而易见行为

### 不应包含
- Claude 可以通过读代码找出的东西
- 标准语言约定
- 详细 API 文档（改为链接）
- 经常变化的信息
- 长解释或教程
- 逐个文件描述代码库
- 自明的实践（如"编写干净代码"）

### 关键技巧
- 使用 `@path/to/import` 引用其他文件，避免 CLAUDE.md 过长
- 域知识放到 skills 中按需加载，不要全塞进 CLAUDE.md
- 像对待代码一样对待 CLAUDE.md：定期修剪、测试效果
- 用强调词（"IMPORTANT"、"YOU MUST"）提升遵守率

### 放置位置
- `~/.claude/CLAUDE.md` → 全局，所有会话
- `./CLAUDE.md` → 项目根，提交 git 共享
- `./CLAUDE.local.md` → 本地，.gitignore
- 父/子目录 → monorepo 自动加载

## 5. 会话管理

- `/clear` 重置不相关任务间的上下文
- `/compact <instructions>` 自定义压缩
- `Esc` 中途停止，`Esc+Esc` 或 `/rewind` 倒带
- 2 次纠正失败后 → `/clear` + 更好的提示重新开始
- `claude --continue` 恢复最近对话
- `/rename` 给会话起描述性名称

## 6. Subagents 使用

- 研究任务委托给 subagent，保持主对话干净
- 实现完成后用 subagent 做代码审查
- 在 `.claude/agents/` 中定义专门助手

## 7. 常见失败模式

| 模式 | 修复 |
|------|------|
| 厨房水槽会话（混杂不相关任务） | 任务间 `/clear` |
| 反复纠正同一问题 | 2 次失败后 `/clear` + 更好提示 |
| CLAUDE.md 过长被忽略 | 无情修剪 |
| 信任但不验证 | 始终提供验证手段 |
| 无限探索填满上下文 | 限定调查范围或用 subagent |

## 8. 扩展模式

- **非交互模式**: `claude -p "prompt"` 用于 CI/脚本
- **多会话并行**: Writer/Reviewer 模式
- **跨文件扇出**: 循环调用 `claude -p` + `--allowedTools`
- **Git Worktrees**: 隔离并行开发
