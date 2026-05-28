---
paths:
  - "services/**/*.py"
  - "services/**/*.ts"
  - "services/**/*.vue"
  - "services/**/README.md"
  - "docs/plans/**/*.md"
  - "docs/ROADMAP.md"
---

# 文件结构变更时更新 README 目录树

## 触发条件

新增、删除或重命名子项目内的源码文件/目录时。

## 规则

子项目的目录结构维护在 **`README.md`** 中（给人类同事看），**不要**写到 `CLAUDE.md`。

文件结构变更后，必须同步更新对应子项目 `README.md` 的"项目结构"章节，确保文档与代码一致。

## 为什么不再放在 CLAUDE.md

CLAUDE.md 只承载**代码读不出的约束与决策**（红线规则、跨服务接口约定、反直觉的设计取舍等）。目录树、文件清单、API 路由这些信息 AI 通过 `ls` / `Glob` / `grep` 当场就能拿到，**写进 CLAUDE.md 就是冗余**，且每次新增文件都要改一次，维护成本高。

给人看的接入信息（目录结构、启动命令、接口清单、环境变量）放 `README.md`。

## 更新内容

- **新增文件**：在 `README.md` 目录树中添加路径和简要说明
- **删除文件**：从 `README.md` 目录树中移除对应条目
- **重命名文件**：更新路径并保留说明
- **新增目录**：添加目录及其用途说明

## 示例

```bash
# 新增文件后
Write services/live-monitor/utils/cache.py
Edit services/live-monitor/README.md   # 在目录结构中添加 cache.py（不动 CLAUDE.md）

# 删除文件后
Bash rm services/live-monitor/deprecated.py
Edit services/live-monitor/README.md   # 从目录结构中移除 deprecated.py
```

## 何时仍需更新 CLAUDE.md

只有当结构变更**伴随约束/决策变更**时才动 CLAUDE.md，例如：

- 新增 API 路由且**该路由有特殊调用约束**（例如"只允许节点间内部调用"）
- 新增模块且**引入跨服务交互约定**
- 重构带来**新的红线规则**（"X 函数禁止在 Y 场景调用"）

纯目录调整、纯文件增删，不动 CLAUDE.md。

## 原因

让 CLAUDE.md 保持稳定、信息密度高，只在真正需要"提醒 AI"的时刻被读取；让 README.md 承担给人和给 AI 共享的"项目地图"职责。

---

# 完成 plan 时同步维护 ROADMAP

## 触发条件

`docs/plans/<plan-name>.md` 中的任务全部完成,或 plan 被废弃时。

## 规则

完成或废弃 plan 时,必须三件事一起做(缺一不可):

1. **更新 `docs/ROADMAP.md`**:把对应条目从「进行中」移到「最近完成」,标完成日期(`YYYY-MM-DD`);只保留最近 10 项,更早的删除即可(archive 仍可追溯)
2. **移动 plan 文件到 archive**:`git mv docs/plans/<plan-name>.md docs/archive/<plan-name>.md` (用 `git mv` 保留历史)
3. **同步检查 specs**:看 `docs/specs/` 下是否有此 plan 关联的过期规格(架构图、ADR),若已被新 plan 取代则一并归档到 `docs/archive/`

## 为什么三件事捆绑

- 只勾 ROADMAP 不移文件 → `plans/` 堆积,失去"在做的事"的语义
- 只移文件不勾 ROADMAP → 入口找不到完成记录,看似没做完
- 不查 specs → 过期架构留在长期参考,误导后续阅读者

## 示例

```bash
# Phase 1 上线稳定后,完成 plan
# 1. 编辑 docs/ROADMAP.md:勾选 + 标日期,移到「最近完成」
# 2. 归档 plan 文件
git mv docs/plans/2026-05-07-live-platform-phase1.md \
       docs/archive/2026-05-07-live-platform-phase1.md
# 3. 检查关联 specs(若 ADR 已过期则一并归档)
ls docs/specs/2026-05-10-mediamtx-deployment-adr.md
```
