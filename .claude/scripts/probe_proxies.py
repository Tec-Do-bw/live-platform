"""代理质量探测器 — 批量测 socks5 代理的风控值/IP 类型/原生 IP/适用场景

用法：
    python .claude/scripts/probe_proxies.py --input <file>
    python .claude/scripts/probe_proxies.py --input - < proxies.txt
    python .claude/scripts/probe_proxies.py --input proxies.json --output ./out

输入支持三种格式（自动识别）：
  1. Python 字典片段：含 `_PROXY_MAP = {...}` 或 `PROXIES = {...}` 的代码
     代理值支持 kookeey 风格 `socks5://host:port:user:pass`
     或标准 `socks5://user:pass@host:port`
     value 可以是字符串或字符串列表（主备多代理）
  2. JSON：{"MY": "socks5://...", "MX": ["...", "..."]} 或带 label 的对象
  3. URL 列表：每行一个 socks5 URL（可选 `# 国家代号 标签` 注释）

依赖：playwright, pproxy, requests
浏览器：默认走 msedge channel（更稳）
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("[ERROR] 缺少 playwright，请先 pip install playwright")
    sys.exit(1)

try:
    import requests
except ImportError:
    print("[ERROR] 缺少 requests，请先 pip install requests")
    sys.exit(1)

BASE_PORT = 18080  # 本地 HTTP 中转起始端口，每代理 +1

# 把 Image 之类无关 chunk 过滤掉的解析正则
_LABEL_RE = {
    "ip_type": re.compile(r"^IP\s*类型"),
    "risk":    re.compile(r"^风[险控]值"),
    "native":  re.compile(r"^原生\s*IP"),
    "scenes":  re.compile(r"^适用场景"),
}


@dataclass
class Proxy:
    """单个代理的标准化形式。"""
    country: str
    host: str
    port: int
    user: str
    password: str
    label: str = ""  # 主备区分，例如 "main" / "backup"

    @property
    def hp(self) -> str:
        return f"{self.host}:{self.port}"

    @property
    def display(self) -> str:
        return f"{self.country}{('-' + self.label) if self.label else ''}"


@dataclass
class Result:
    proxy: Proxy
    ipify_ip: str = ""
    ipinfo: dict = field(default_factory=dict)
    ping0_ip: str = ""
    ip_type: str = ""
    risk: str = ""
    native: str = ""
    scenes: str = ""
    error: str = ""
    attempt: int = 1

    def to_dict(self) -> dict:
        return {
            "country": self.proxy.country,
            "label": self.proxy.label,
            "host": self.proxy.host,
            "port": self.proxy.port,
            "ipify_ip": self.ipify_ip,
            "ping0_ip": self.ping0_ip,
            "ip_type": self.ip_type,
            "risk": self.risk,
            "native": self.native,
            "scenes": self.scenes,
            "ipinfo": self.ipinfo,
            "error": self.error,
            "attempt": self.attempt,
        }


# ---------- 输入解析 ----------

_SOCKS5_KOOKEEY = re.compile(r"socks5://([^:/\s]+):(\d+):([^:\s]+):([^\s\"',\]]+)")
_SOCKS5_STD = re.compile(r"socks5://([^:@/\s]+):([^@/\s]+)@([^:/\s]+):(\d+)")


def _parse_socks5(s: str) -> tuple[str, int, str, str] | None:
    """解析单个 socks5 URL，支持两种格式。返回 (host, port, user, pass)。"""
    s = s.strip().rstrip(",;")
    m = _SOCKS5_STD.search(s)
    if m:
        user, pwd, host, port = m.group(1), m.group(2), m.group(3), int(m.group(4))
        return host, port, user, pwd
    m = _SOCKS5_KOOKEEY.search(s)
    if m:
        host, port, user, pwd = m.group(1), int(m.group(2)), m.group(3), m.group(4)
        return host, port, user, pwd
    return None


def _from_dict_value(country: str, val) -> list[Proxy]:
    """处理 dict value：可能是字符串、list[str]、或 {label: url} 字典。"""
    out: list[Proxy] = []
    if isinstance(val, str):
        parsed = _parse_socks5(val)
        if parsed:
            out.append(Proxy(country, *parsed))
    elif isinstance(val, list):
        for i, item in enumerate(val):
            if isinstance(item, str):
                parsed = _parse_socks5(item)
                if parsed:
                    label = "main" if i == 0 and len(val) > 1 else (f"alt{i}" if len(val) > 1 else "")
                    out.append(Proxy(country, *parsed, label=label))
    elif isinstance(val, dict):
        for label, item in val.items():
            if isinstance(item, str):
                parsed = _parse_socks5(item)
                if parsed:
                    out.append(Proxy(country, *parsed, label=str(label)))
    return out


def parse_input(text: str) -> list[Proxy]:
    """识别输入格式并解析成 Proxy 列表。"""
    text = text.strip()
    if not text:
        return []

    # 优先尝试 JSON
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            out: list[Proxy] = []
            for country, val in data.items():
                out.extend(_from_dict_value(str(country), val))
            if out:
                return out
    except (json.JSONDecodeError, ValueError):
        pass

    # 尝试 Python 字典片段（_PROXY_MAP = {...}）
    if re.search(r"[A-Z_]+\s*[:=]\s*\{", text) or text.lstrip().startswith("{"):
        # 提取最外层的 {} 块
        start = text.find("{")
        if start >= 0:
            depth, end = 0, -1
            for i in range(start, len(text)):
                c = text[i]
                if c == "{":
                    depth += 1
                elif c == "}":
                    depth -= 1
                    if depth == 0:
                        end = i + 1
                        break
            if end > start:
                snippet = text[start:end]
                # 去掉行内注释
                snippet = re.sub(r"#[^\n]*", "", snippet)
                # 把单引号转双引号，去掉尾随逗号，转 JSON 化
                try:
                    # 用 ast.literal_eval 安全
                    import ast
                    obj = ast.literal_eval(snippet)
                    if isinstance(obj, dict):
                        out = []
                        for country, val in obj.items():
                            out.extend(_from_dict_value(str(country), val))
                        if out:
                            return out
                except (ValueError, SyntaxError):
                    pass

    # 兜底：按行扫描 socks5 URL
    out: list[Proxy] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # 行内可能有 `# CN-MY label` 注释提供国家
        comment = ""
        if "#" in line:
            url_part, comment = line.split("#", 1)
            url_part = url_part.strip()
            comment = comment.strip()
        else:
            url_part = line
        parsed = _parse_socks5(url_part)
        if parsed:
            country = "??"
            label = ""
            if comment:
                bits = comment.split()
                if bits:
                    country = bits[0]
                if len(bits) > 1:
                    label = " ".join(bits[1:])
            out.append(Proxy(country, *parsed, label=label))
    return out


# ---------- pproxy 中转 ----------

def start_pproxy(local_port: int, p: Proxy) -> subprocess.Popen:
    """起本地 HTTP 代理 → socks5(带认证)。Chromium 不支持 SOCKS5 auth，必须包一层。"""
    cmd = [
        sys.executable, "-m", "pproxy",
        "-l", f"http://:{local_port}",
        "-r", f"socks5://{p.hp}#{p.user}:{p.password}",
    ]
    flags = subprocess.CREATE_NEW_PROCESS_GROUP if hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP") else 0
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags)
    time.sleep(2.5)
    return proc


def stop_pproxy(proc: subprocess.Popen) -> None:
    try:
        proc.terminate()
        proc.wait(timeout=5)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


# ---------- 浏览器探测 ----------

PARSE_JS = r"""
() => {
  const out = { ip:'', ip_type:'', risk:'', native:'', scenes:'' };
  const ipBlock = document.querySelector('.content .ip')?.innerText || '';
  const m = ipBlock.match(/\d+\.\d+\.\d+\.\d+/);
  out.ip = m ? m[0] : '';

  const rows = [...document.querySelectorAll('div, li, tr')];
  for (const r of rows) {
    const t = (r.innerText || '').trim();
    if (!t || t.length > 600) continue;
    if (!out.ip_type && /^IP\s*类型/.test(t)) out.ip_type = t;
    else if (!out.risk && /^风[险控]值/.test(t)) out.risk = t;
    else if (!out.native && /^原生\s*IP/.test(t)) out.native = t;
    else if (!out.scenes && /^适用场景/.test(t)) out.scenes = t;
  }
  return out;
}
"""


def clean_field(text: str, label_re: re.Pattern) -> str:
    """从 ping0 抓回的原始多行文本里抽出真正的值。"""
    if not text:
        return ""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    out: list[str] = []
    skip_label = True
    for ln in lines:
        if skip_label and label_re.match(ln):
            skip_label = False
            continue
        if "(说明" in ln or ln.startswith("(说明") or ln == "(说明?)":
            continue
        if "为什么" in ln:
            break
        out.append(ln)
        if len(out) >= 3:
            break
    return " / ".join(out)


def _query_ipinfo(local_port: int, ipify_ip: str, token: str | None) -> dict:
    """通过本地 HTTP 中转查 ipinfo.io。失败不阻塞主流程。"""
    if not ipify_ip:
        return {}
    try:
        url = f"https://ipinfo.io/{ipify_ip}/json"
        if token:
            url += f"?token={token}"
        r = requests.get(
            url,
            proxies={"http": f"http://127.0.0.1:{local_port}", "https": f"http://127.0.0.1:{local_port}"},
            timeout=15,
        )
        if r.ok:
            return r.json()
    except Exception:
        pass
    return {}


def probe_one(p: Proxy, port: int, output_dir: Path, headed: bool, skip_ipinfo: bool, ipinfo_token: str | None) -> Result:
    r = Result(proxy=p)
    pproxy_proc = start_pproxy(port, p)

    try:
        with sync_playwright() as pw:
            try:
                browser = pw.chromium.launch(
                    channel="msedge",
                    headless=not headed,
                    proxy={"server": f"http://127.0.0.1:{port}"},
                    args=["--disable-blink-features=AutomationControlled"],
                )
            except Exception as e:
                r.error = f"browser_launch_failed: {e}"
                return r

            try:
                ctx = browser.new_context()
                page = ctx.new_page()

                # 1) ipify 校验出口 IP
                try:
                    page.goto("https://api.ipify.org?format=json", timeout=30000)
                    body = page.inner_text("body")
                    m = re.search(r"\d+\.\d+\.\d+\.\d+", body)
                    r.ipify_ip = m.group(0) if m else ""
                except Exception as e:
                    r.error = f"ipify_failed: {type(e).__name__}"
                    return r

                if not r.ipify_ip:
                    r.error = "ipify_no_ip"
                    return r

                # 2) ipinfo（可选，失败不阻塞）
                if not skip_ipinfo:
                    r.ipinfo = _query_ipinfo(port, r.ipify_ip, ipinfo_token)

                # 3) ping0
                try:
                    page.goto("https://ping0.cc/", timeout=45000, wait_until="domcontentloaded")
                except Exception as e:
                    r.error = f"ping0_goto_failed: {type(e).__name__}"
                    return r

                # 等 Turnstile 自动通过
                deadline = time.time() + 45
                while time.time() < deadline:
                    title = page.title()
                    if "归属地" in title:
                        break
                    time.sleep(1.5)
                else:
                    r.error = "turnstile_timeout"
                    return r

                time.sleep(1.5)
                data = page.evaluate(PARSE_JS)
                r.ping0_ip = data.get("ip") or ""
                r.ip_type = clean_field(data.get("ip_type") or "", _LABEL_RE["ip_type"])
                r.risk = clean_field(data.get("risk") or "", _LABEL_RE["risk"])
                r.native = clean_field(data.get("native") or "", _LABEL_RE["native"])
                r.scenes = clean_field(data.get("scenes") or "", _LABEL_RE["scenes"])

                shot = output_dir / f"ping0_{p.display}.png"
                try:
                    page.screenshot(path=str(shot), full_page=True)
                except Exception:
                    pass

            finally:
                browser.close()
    finally:
        stop_pproxy(pproxy_proc)
        time.sleep(1.0)

    return r


def probe_with_retry(p: Proxy, port: int, output_dir: Path, headed: bool, skip_ipinfo: bool, ipinfo_token: str | None, retries: int) -> Result:
    last: Optional[Result] = None
    for attempt in range(1, retries + 2):
        r = probe_one(p, port, output_dir, headed, skip_ipinfo, ipinfo_token)
        r.attempt = attempt
        if not r.error:
            return r
        last = r
        if attempt <= retries:
            print(f"  [retry {attempt}/{retries}] {p.display} 失败：{r.error}，重试...")
    return last  # 用尽次数仍失败


# ---------- 输出汇总 ----------

def write_summary(results: list[Result], output_dir: Path) -> Path:
    md = [
        "| 节点 | host:port | 出口 IP | IP 类型 | 风控值 | 原生 IP | TikTok 适用 | ASN / ISP |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for r in results:
        p = r.proxy
        ip = r.ipify_ip or "-"
        ip_type = r.ip_type or (r.error or "-")
        risk = r.risk or "-"
        native = r.native or "-"
        # 适用场景里 TikTok 的星级
        tk = "-"
        if r.scenes:
            m = re.search(r"TikTok\s*[\n ]+([★☆ ]+)", r.scenes)
            if m:
                tk = m.group(1).strip()
        isp = "-"
        if r.ipinfo:
            org = r.ipinfo.get("org") or ""
            isp = org if org else (r.ipinfo.get("isp") or "-")
        md.append(f"| {p.display} | {p.hp} | {ip} | {ip_type} | {risk} | {native} | {tk} | {isp} |")

    text = "\n".join(md)

    # 重复 IP 检测
    seen: dict[str, list[str]] = {}
    for r in results:
        if r.ipify_ip:
            seen.setdefault(r.ipify_ip, []).append(r.proxy.display)
    dups = {ip: ds for ip, ds in seen.items() if len(ds) > 1}
    if dups:
        text += f"\n\n⚠️ 重复出口 IP（代理可能没真正切换）：{dups}"
    else:
        ips_count = len([r for r in results if r.ipify_ip])
        text += f"\n\n✅ {ips_count} 个出口 IP 全部不同"

    summary = output_dir / "summary.md"
    summary.write_text(text, encoding="utf-8")
    return summary


# ---------- 主入口 ----------

def main() -> int:
    ap = argparse.ArgumentParser(description="代理质量探测器")
    ap.add_argument("--input", required=True, help="输入文件路径，- 表示 stdin")
    ap.add_argument("--output", default="", help="结果输出目录，默认 ./proxy_probe_<时间戳>/")
    ap.add_argument("--retries", type=int, default=1, help="失败重试次数（默认 1）")
    ap.add_argument("--headed", action="store_true", default=True, help="headed 模式（默认开）")
    ap.add_argument("--no-headed", dest="headed", action="store_false", help="headless 模式")
    ap.add_argument("--skip-ipinfo", action="store_true", help="跳过 ipinfo.io 查询")
    ap.add_argument("--ipinfo-token", default="", help="ipinfo.io token，否则用免费额度")
    args = ap.parse_args()

    # 读输入
    if args.input == "-":
        text = sys.stdin.read()
    else:
        text = Path(args.input).read_text(encoding="utf-8")

    proxies = parse_input(text)
    if not proxies:
        print("[ERROR] 没识别出任何代理，请检查输入格式")
        return 2

    # 输出目录
    if args.output:
        out_dir = Path(args.output)
    else:
        out_dir = Path.cwd() / f"proxy_probe_{time.strftime('%Y%m%d_%H%M%S')}"
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"识别到 {len(proxies)} 个代理，输出目录：{out_dir}")
    print("─" * 60)

    jsonl_path = out_dir / "results.jsonl"
    jsonl_path.write_text("", encoding="utf-8")
    results: list[Result] = []
    ipinfo_token = args.ipinfo_token or None

    for idx, p in enumerate(proxies, start=1):
        port = BASE_PORT + idx
        print(f"\n[{idx}/{len(proxies)}] {p.display} → {p.hp} (local :{port})")

        try:
            r = probe_with_retry(p, port, out_dir, args.headed, args.skip_ipinfo, ipinfo_token, args.retries)
        except Exception as e:
            r = Result(proxy=p, error=f"crash: {type(e).__name__}: {e}")

        results.append(r)
        with jsonl_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(r.to_dict(), ensure_ascii=False) + "\n")

        print(f"  ipify  : {r.ipify_ip or '-'}")
        print(f"  ping0  : {r.ping0_ip or '-'}")
        print(f"  类型   : {r.ip_type or '-'}")
        print(f"  风控   : {r.risk or '-'}")
        print(f"  原生   : {r.native or '-'}")
        if r.ipinfo:
            org = r.ipinfo.get("org") or r.ipinfo.get("isp") or "-"
            print(f"  ISP    : {org}")
        if r.error:
            print(f"  ERROR  : {r.error} (after {r.attempt} attempts)")

    summary = write_summary(results, out_dir)
    print(f"\n{'═' * 60}\n汇总：{summary}")
    print(summary.read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
