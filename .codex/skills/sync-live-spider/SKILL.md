---
name: sync-live-spider
description: 把 live-platform monorepo 的 services/live-stream/ 子目录覆盖式推送到独立仓库 live-spider 的 sync/live-platform 分支。仅公司 Windows 环境使用。触发词：同步 live-spider、sync-live-spider、把 live-stream 推到独立仓库、同步 live-stream 子仓库、推一份 live-stream 到 gitlab 独立仓库。
user-invocable: true
allowed-tools: "Read Bash Glob Grep"
---

# 同步 live-stream 到 live-spider 独立仓库

把 live-platform monorepo 的 `services/live-stream/` 子目录覆盖式推送到独立仓库
`https://git.tec-do.com/live/live-spider` 的 `sync/live-platform` 分支。

## 前置条件

- **仅公司 Windows 环境执行**（家里 Mac 不执行，与 live-platform 的 GitLab 同步策略一致）
- 当前工作目录在 live-platform 仓库根目录
- `services/live-stream/` 无未提交改动（脚本会自动检查并拦截）

## 工作流程

### 1. 确认在仓库根目录

```bash
test -f scripts/sync-live-spider.sh && echo "✅ 找到同步脚本" || echo "❌ 不在 live-platform 根目录，请先 cd 过去"
```

若不在 live-platform 根目录，提示用户先 `cd` 到 monorepo 根目录，不要继续。

### 2. 执行同步脚本（单一权威源）

```bash
bash scripts/sync-live-spider.sh
```

脚本会自动完成：检查工作树是否干净 → 幂等补 `live-spider` remote →
`git subtree split` 抽取子目录历史 → `git push --force` 覆盖推送到 `sync/live-platform` → 清理临时分支。

**不要**绕过脚本手写 git subtree / git push 命令；逻辑与配置只维护在 `scripts/sync-live-spider.sh` 内。

### 3. 呈现结果

把脚本输出转给用户。成功后可核对远端：

```bash
git ls-remote live-spider sync/live-platform
```

## 失败处理

依据脚本的中文报错判断：
- **「有未提交的改动」** → 让用户先提交或暂存 `services/live-stream/` 改动后重试
- **「推送失败」** → 确认在公司网络、有 GitLab 推送权限；脚本已自动清理临时分支，可直接重试

## 注意

- **覆盖式推送**：`sync/live-platform` 永远镜像 monorepo 当前 live-stream 内容，不累积历史
- **隔离性**：只动 `sync/live-platform`，不碰 live-spider 的 main/master 等老分支
- 本 skill 不接受参数；脚本逻辑见 repo 内 `scripts/sync-live-spider.sh` 注释
