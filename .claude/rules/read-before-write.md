---
paths:
  - "services/**/*.py"
  - "services/**/*.ts"
  - "services/**/*.vue"
---

# 编辑前必读子项目 CLAUDE.md

## 触发条件

编辑 `services/*/` 下任何文件时。

## 规则

在修改子项目代码前，必须先阅读对应子项目的 CLAUDE.md 文件，了解：
- 项目定位与职责边界
- 目录结构与模块划分
- 核心架构与设计约束
- 与其他服务的交互规则
- 特殊约束与已知问题

## 示例

```bash
# ❌ 错误：直接修改代码
Edit services/live-monitor/main.py

# ✅ 正确：先读 CLAUDE.md
Read services/live-monitor/CLAUDE.md
Edit services/live-monitor/main.py
```

## 原因

子项目 CLAUDE.md 记录了该服务的特有规则和约束，直接修改代码可能违反架构设计或破坏服务间契约。
