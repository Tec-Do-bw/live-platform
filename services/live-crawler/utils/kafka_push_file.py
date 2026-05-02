#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""临时脚本：读取本地 JSON 文件并发送到 Kafka
$env:PYTHONPATH="D:\SpiderCode\demo\Temp_tasks"

用法示例：
  python utils/kafka_push_file.py --file resource/google_ads_parse.json --topic-key google_ads
  python utils/kafka_push_file.py --file resource/snapchat_adsets_result.json     --topic-key snapchat_adsets_result

如果未指定 --topic-key，将尝试根据文件名自动判断（包含 "campaigns" 或 "adsets"）。
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, List

from utils.kafka_client import producer_client
from utils.logger import logger


def _load_json_file(path: Path) -> Any:
    """尽量鲁棒地读取 JSON 文件：
    - 优先按单个 JSON（对象/数组）整体加载
    - 若失败，则按行尝试逐行解析（NDJSON），合并为列表
    """
    text = path.read_text(encoding="utf-8")
    text_stripped = text.strip()
    if not text_stripped:
        raise ValueError(f"文件为空：{path}")
    # 先整体解析
    try:
        return json.loads(text_stripped)
    except Exception:
        pass

    # 再尝试按行解析（NDJSON）
    items: List[Any] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            items.append(json.loads(line))
        except Exception as e:
            raise ValueError(f"无法解析为 JSON：{path} | 无法解析的行：{line[:120]} | err={e}")
    if not items:
        raise ValueError(f"未解析到有效 JSON：{path}")
    return items


def _infer_topic_key_from_filename(path: Path) -> str | None:
    name = path.name.lower()
    if "campaign" in name:
        return "snapchat_campaigns_result"
    if "adset" in name:
        return "snapchat_adsets_result"
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="读取本地 JSON 并发送到 Kafka 指定 topic")
    parser.add_argument("--file", required=True, help="JSON 文件路径")
    parser.add_argument(
        "--topic-key",
        help="Kafka topic 的逻辑 key（不填则尝试根据文件名自动判断）",
    )
    args = parser.parse_args()

    file_path = Path(args.file)
    if not file_path.exists():
        raise FileNotFoundError(f"文件不存在：{file_path}")

    topic_key = args.topic_key or _infer_topic_key_from_filename(file_path)
    if not topic_key:
        raise SystemExit("请通过 --topic-key 指定，或使用包含 'campaigns'/'adsets' 的文件名以自动判断")

    data = _load_json_file(file_path)
    logger.info(f"读取 JSON 完成 | path={file_path} | type={type(data).__name__}")

    # 复用现有封装，确保消息结构符合消费端契约
    try:
        if topic_key == "google_ads":
            producer_client.send_datas(data)
        elif topic_key == "snapchat_adsets_result":
            producer_client.send_snapchat_adsets_result(data)
        elif topic_key == "crawl_result":
            producer_client.send_crawl_result(data)
        else:
            # 理论上到不了这里（choices 已限制），留作兜底
            producer_client._send(topic_key, data)  # type: ignore[attr-defined]

        producer_client.flush()
        logger.success(f"Kafka 发送完成 | topic_key={topic_key}")
    finally:
        producer_client.close()


if __name__ == "__main__":
    main()


