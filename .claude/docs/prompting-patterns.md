# 高效 Prompting 模式

## 任务启动模式

### 采访式需求收集
```
I want to build [brief description]. Interview me in detail using the AskUserQuestion tool.
Ask about technical implementation, UI/UX, edge cases, concerns, and tradeoffs.
Don't ask obvious questions, dig into the hard parts I might not have considered.
Keep interviewing until we've covered everything, then write a complete spec to SPEC.md.
```

### 计划模式启动
```
read /src/auth and understand how we handle sessions and login.
also look at how we manage environment variables for secrets.
```
然后：
```
I want to add Google OAuth. What files need to change? What's the session flow? Create a plan.
```

## 验证模式

### 带测试的功能开发
```
编写一个 validateEmail 函数。
示例测试用例：user@example.com 为真，invalid 为假，user@.com 为假。
实现后运行测试。
```

### UI 视觉验证
```
[粘贴截图] 实现此设计。
对结果进行截图并与原始设计比较。列出差异并修复它们。
```

### 根因分析
```
构建失败，出现此错误：[粘贴错误]。
修复它并验证构建成功。解决根本原因，不要抑制错误。
```

## 调研模式

### 用 Subagent 调研
```
Use subagents to investigate how our authentication system handles token refresh,
and whether we have any existing OAuth utilities I should reuse.
```

### Subagent 代码审查
```
use a subagent to review this code for edge cases
```

## Issue 驱动开发模式

```
查看 GitHub Issue #123 的详情，分析问题根因。
在独立分支上修复，编写测试验证，提交 PR。
```

## 迁移/批量模式

```bash
for file in $(cat files.txt); do
  claude -p "Migrate $file from React to Vue. Return OK or FAIL." \
    --allowedTools "Edit,Bash(git commit *)"
done
```

## 纠正模式

- 发现错误 → 用 `#` 标记并让 Claude 学习
- 2 次纠正失败 → `/clear` + 重写更好的提示
- 死胡同 → `Esc+Esc` 或 `/rewind` 回退
