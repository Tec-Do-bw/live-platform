---
paths:
  - "services/**/*.py"
  - "services/**/*.ts"
  - "services/**/*.vue"
  - "services/**/CLAUDE.md"
---

# 文件结构变更时更新文档

## 触发条件

新增或删除文件时。

## 规则

当新增或删除文件后，必须同步更新对应子项目 CLAUDE.md 的"目录结构"章节，确保文档与代码一致。

## 更新内容

- **新增文件**：在目录树中添加文件路径和简要说明
- **删除文件**：从目录树中移除对应条目
- **重命名文件**：更新路径并保留说明
- **新增目录**：添加目录及其用途说明

## 示例

```bash
# 新增文件后
Write services/live-monitor/utils/cache.py
Edit services/live-monitor/CLAUDE.md  # 在目录结构中添加 cache.py

# 删除文件后
Bash rm services/live-monitor/deprecated.py
Edit services/live-monitor/CLAUDE.md  # 从目录结构中移除 deprecated.py
```

## 原因

保持文档与代码同步，避免新成员或 AI 助手基于过时的目录结构做出错误判断。
