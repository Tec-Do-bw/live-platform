# 代理质量探测器（ping0.cc + ipinfo.io）

批量测 socks5 代理的 **IP 类型、风控值、原生 IP 状态、TikTok 适用性**，外加 ASN/ISP 真实归属。

## 何时使用

显式调用：用户输入 `/probe-proxy` 后，把代理列表粘到 ARGUMENTS。

支持的输入形式（用户粘什么都能识别）：

1. **Python 字典片段**（最常见的复制粘贴场景）：
   ```python
   _PROXY_MAP = {
       "MY": "socks5://54.kookeey.info:23546:c822ee15:2169010a",
       "MX": ["socks5://mx565.kookeey.info:30067:c822ee15:2169010a",
              "socks5://mx351.kookeey.info:29961:c822ee15:2169010a"],
   }
   ```
2. **JSON**：`{"MY": "socks5://user:pass@host:port", ...}`
3. **URL 列表**：每行一个 `socks5://user:pass@host:port`（行内可加 `# 国家 标签` 注释）

URL 内部支持两种分隔风格：
- kookeey 风格 `socks5://host:port:user:pass`
- 标准风格 `socks5://user:pass@host:port`

## 工作流程

### 1. 把 ARGUMENTS 写入临时输入文件

ARGUMENTS 可能是多行代码片段，避免命令行转义问题，先落到 `.claude/scratch/proxies_input.txt`：

```bash
cat > .claude/scratch/proxies_input.txt <<'PROXY_EOF'
{ARGUMENTS 完整内容，原样保留缩进}
PROXY_EOF
```

如果 ARGUMENTS 为空，提示用户：「把代理列表/字典粘在 `/probe-proxy` 后面，例如 `/probe-proxy _PROXY_MAP = {...}`」并退出，不要继续。

### 2. 调用主脚本

```bash
python .claude/scripts/probe_proxies.py \
    --input .claude/scratch/proxies_input.txt \
    --output .claude/scratch/proxy_probe_$(date +%Y%m%d_%H%M%S)
```

主脚本会：
- 解析输入（自动识别 Python 字典 / JSON / URL 列表）
- 对每个代理：起独立 pproxy 中转端口 → 全新浏览器进程 → ipify 校验出口 IP → ipinfo.io 查 ASN/ISP → ping0.cc 拿 IP 类型/风控值/原生 IP/适用场景
- 失败自动重试 1 次
- 截图、JSONL、markdown 汇总落到 output 目录

预期耗时：每个代理约 30-60 秒（含浏览器启动 + Turnstile 通过）；10 个代理约 5-10 分钟。

### 3. 给用户呈现结果

脚本最后会把 `summary.md` 内容打印到 stdout，**直接把这段表格转给用户**，并补充以下解读维度：

- **风控值**：<25% 标「纯净」，25-50% 「中性」，>50% 警告
- **TikTok 场景**：全部 ☆☆☆☆☆ 时主动提示「这套代理整体不适合 TikTok，需要换 ISP 双归属/原生 IP」
- **IP 类型对照**：如果用户提供过采购记录（"群里说是 IDC"），列出实测与采购不一致的项
- **出口 IP 校验**：脚本会自动检查 N 个代理的出口 IP 是否全部不同；如果有重复，提示「代理可能没真正切换」
- **失败的项**：单独列出原因（`turnstile_timeout` 通常是代理慢，`ipify_failed` 是代理本身不通）

输出目录里的资源（按需告诉用户）：
- `summary.md` — markdown 汇总表
- `results.jsonl` — 结构化数据，便于二次处理
- `ping0_<节点>.png` — 每个代理的 ping0 全屏截图

## 系统依赖

首次使用前，确认这些已装：

```bash
pip install playwright pproxy requests
playwright install msedge   # 或 chromium
```

如果脚本启动报「缺少 playwright/requests」，按提示装即可。

环境变量（可选）：
- `IPINFO_TOKEN` — ipinfo.io 个人 token，免费额度 50k/月足够诊断使用

## 常见故障

- **Turnstile 持续超时**：脚本已自动重试 1 次仍失败会标 ERROR；常见原因是该代理节点连 Cloudflare 网速差，单独排查或换节点
- **chromium 启动崩溃（0xC0000005）**：脚本默认走 msedge channel 规避，无需处理
- **出口 IP 重复**：理论上不会发生（每代理独立端口），如果出现说明系统级 keepalive 缓存异常，重启脚本即可
- **pproxy 残留进程**：脚本 finally 兜底 kill；如果意外中断，手动 `pkill -f pproxy`

## 注意

- 这是一次性诊断工具，不要拿来做长期监控
- 主脚本保持单一权威源 `.claude/scripts/probe_proxies.py`，本命令文件只描述何时调用、怎么解读
- 探测期间会有 N 个浏览器窗口逐个弹出（headed 模式），可观察 Turnstile 是否真的在过；headless 跑加 `--no-headed` 参数

## ARGUMENTS

ARGUMENTS 由用户在 `/probe-proxy` 后传入，整段视为代理列表内容，不要拆分或重新解释。
