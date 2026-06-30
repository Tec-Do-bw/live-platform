#!/usr/bin/env bash
# 同步 live-stream 子目录到独立仓库 live-spider
# 用途：公司 Windows 环境下，把 monorepo 的 services/live-stream/ 覆盖式推送到
#       https://git.tec-do.com/live/live-spider 的 sync/live-platform 分支
# 语义：force push，内容以 monorepo 为准，live-spider 那边是 monorepo 的最新镜像

set -euo pipefail

# 配置（单一权威源，不要在其他地方复制这些值）
PREFIX="services/live-stream"
REMOTE="live-spider"
REMOTE_URL="https://git.tec-do.com/live/live-spider"
TARGET_BRANCH="sync/live-platform"
SPLIT_BRANCH="_subtree-split-live-spider"

# 前置检查：确认在仓库根目录
if [[ ! -d ".git" ]]; then
    echo "❌ 错误：当前不在 git 仓库根目录，请先 cd 到 live-platform 根目录" >&2
    exit 1
fi

if [[ ! -d "$PREFIX" ]]; then
    echo "❌ 错误：未找到子目录 $PREFIX" >&2
    exit 1
fi

# 检查工作树是否干净（避免推送半成品）
if ! git diff-index --quiet HEAD -- "$PREFIX" 2>/dev/null; then
    echo "❌ 错误：$PREFIX 有未提交的改动，请先提交或暂存" >&2
    echo "提示：运行 git status 查看改动" >&2
    exit 1
fi

echo "🔍 检查 remote '$REMOTE'..."
# 幂等补 remote（若已存在则跳过）
if ! git remote get-url "$REMOTE" >/dev/null 2>&1; then
    echo "➕ 添加 remote: $REMOTE -> $REMOTE_URL"
    git remote add "$REMOTE" "$REMOTE_URL"
else
    echo "✅ remote '$REMOTE' 已存在"
fi

echo ""
echo "📦 抽取子目录历史: $PREFIX -> 临时分支 $SPLIT_BRANCH"
# 删除可能残留的旧临时分支
git branch -D "$SPLIT_BRANCH" 2>/dev/null || true

# 抽取子目录历史到临时分支
if ! git subtree split --prefix="$PREFIX" -b "$SPLIT_BRANCH"; then
    echo "❌ 错误：git subtree split 失败" >&2
    exit 1
fi

echo ""
echo "🚀 覆盖式推送到 $REMOTE/$TARGET_BRANCH (force push)..."
if ! git push --force "$REMOTE" "$SPLIT_BRANCH:$TARGET_BRANCH"; then
    echo "❌ 错误：推送失败，可能需要认证或网络问题" >&2
    echo "💡 提示：确认当前在公司网络环境，且有 GitLab 推送权限" >&2
    # 清理临时分支后退出
    git branch -D "$SPLIT_BRANCH" 2>/dev/null || true
    exit 1
fi

echo ""
echo "🧹 清理临时分支 $SPLIT_BRANCH..."
git branch -D "$SPLIT_BRANCH"

echo ""
echo "✅ 同步完成！"
echo "📍 远端分支：$REMOTE_URL (分支 $TARGET_BRANCH)"
echo "💡 验证：git ls-remote $REMOTE $TARGET_BRANCH"
