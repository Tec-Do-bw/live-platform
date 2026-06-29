# 同步 live-stream 到 live-spider 独立仓库

把 monorepo 的 `services/live-stream/` 子目录覆盖式推送到独立仓库
`https://git.tec-do.com/live/live-spider` 的 `sync/live-platform` 分支。

## 何时使用

用户输入 `/sync-live-spider`,或说「同步 live-spider」「把 live-stream 推到独立仓库」「同步 live-stream 子仓库」时触发。

## 前置条件

- **仅公司 Windows 环境执行**(家里 Mac 不执行,与 AGENTS.md GitLab 同步策略一致)
- 当前在 live-platform 仓库根目录
- `services/live-stream/` 无未提交改动(脚本会自动检查并拦截)

## 工作流程

### 1. 确认环境与位置

执行前先确认在仓库根目录:

```bash
test -f scripts/sync-live-spider.sh && echo "✅ 找到同步脚本" || echo "❌ 不在 live-platform 根目录"
```

若 `services/live-stream/` 有未提交改动,提示用户先提交,不要继续(脚本也会拦截)。

### 2. 执行同步脚本

```bash
bash scripts/sync-live-spider.sh
```

脚本会自动完成:幂等补 `live-spider` remote → `git subtree split` 抽取子目录历史 →
`git push --force` 覆盖推送到 `sync/live-platform` → 清理临时分支。

### 3. 给用户呈现结果

把脚本输出转给用户。成功时确认远端分支已更新:

```bash
git ls-remote live-spider sync/live-platform
```

## 失败处理

依据脚本的中文报错判断:
- **「有未提交的改动」** → 让用户先 `git commit` 或暂存 `services/live-stream/` 改动
- **「推送失败」** → 确认当前在公司网络、有 GitLab 推送权限;脚本已自动清理临时分支,可直接重试

## 注意

- **覆盖式推送**:`sync/live-platform` 永远镜像 monorepo 当前 live-stream 内容,不累积历史
- **隔离性**:只动 `sync/live-platform`,不碰 live-spider 的 main/master 等老分支
- 脚本是单一权威源,本命令文件只描述何时调用、怎么处理结果;脚本逻辑与配置见
  `scripts/sync-live-spider.sh` 内注释
- 本命令不接受参数
