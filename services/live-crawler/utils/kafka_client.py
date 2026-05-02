#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Kafka 生产者工具

职责：
- 读取配置，构建 KafkaProducer
- 提供 send_crawl_result 的便捷方法（仅汇总）
- 统一 JSON 序列化：支持 datetime、Decimal、pydantic BaseModel
"""

from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, Optional

from kafka import KafkaProducer

from core.config import Settings
from utils.logger import logger


def _default_json_encoder(obj: Any):
    # pydantic BaseModel
    try:
        from pydantic import BaseModel  # 延迟导入
        if isinstance(obj, BaseModel):
            return obj.dict()
    except Exception:
        pass

    if isinstance(obj, datetime):
        return obj.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(obj, Decimal):
        return float(obj)
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


class KafkaProducerClient:
    """Kafka 生产者客户端封装"""

    def __init__(self):
        self._enabled: bool = bool(Settings.KAFKA_CONFIG.get("enabled", False))
        self._topics: Dict[str, str] = Settings.KAFKA_CONFIG.get("topics", {})
        self._producer: Optional[KafkaProducer] = None

        if not self._enabled:
            logger.warning("Kafka 已禁用，发送操作将被跳过")
            return

        if KafkaProducer is None:
            raise RuntimeError("未安装 kafka-python，请先安装: pip install kafka-python")

        bootstrap_servers = [s.strip() for s in str(Settings.KAFKA_CONFIG.get("bootstrap_servers", "")).split(",") if s.strip()]
        security_protocol = Settings.KAFKA_CONFIG.get("security_protocol", "PLAINTEXT")
        sasl_mechanism = Settings.KAFKA_CONFIG.get("sasl_mechanism")
        sasl_plain_username = Settings.KAFKA_CONFIG.get("sasl_username")
        sasl_plain_password = Settings.KAFKA_CONFIG.get("sasl_password")

        logger.info(f"初始化 KafkaProducer | servers={bootstrap_servers} | security={security_protocol}")

        producer_kwargs: Dict[str, Any] = dict(
            bootstrap_servers=bootstrap_servers,
            acks=Settings.KAFKA_CONFIG.get("acks", "all"),
            retries=int(Settings.KAFKA_CONFIG.get("retries", 3)),
            linger_ms=int(Settings.KAFKA_CONFIG.get("linger_ms", 5)),
            batch_size=int(Settings.KAFKA_CONFIG.get("batch_size", 32768)),
            client_id=str(Settings.KAFKA_CONFIG.get("client_id", "xiaomi_ads_crawler")),
            value_serializer=lambda v: json.dumps(v, default=_default_json_encoder, separators=(",", ":")).encode("utf-8"),
            key_serializer=lambda v: json.dumps(v).encode("utf-8") if v is not None else None,
        )

        if security_protocol and security_protocol != "PLAINTEXT":
            producer_kwargs.update(security_protocol=security_protocol)
        if sasl_mechanism:
            producer_kwargs.update(sasl_mechanism=sasl_mechanism)
        if sasl_plain_username and sasl_plain_password:
            producer_kwargs.update(
                sasl_plain_username=sasl_plain_username,
                sasl_plain_password=sasl_plain_password,
            )

        try:
            self._producer = KafkaProducer(**producer_kwargs)
            logger.info("KafkaProducer 创建成功")
        except Exception as e:
            logger.exception(f"KafkaProducer 创建失败: {e}")
            self._producer = None

    def is_enabled(self) -> bool:
        return self._enabled and self._producer is not None

    def _send(self, topic_key: str, value: Dict[str, Any]) -> None:
        if not self.is_enabled():
            logger.debug(f"跳过发送，Kafka 未启用或 Producer 不可用 | topic_key={topic_key}")
            return
        topic = self._topics.get(topic_key)
        if not topic:
            logger.error(f"Kafka topic 未配置: {topic_key}")
            return
        try:
            assert self._producer is not None
            self._producer.send(topic, value=value)
        except Exception as e:
            logger.exception(f"Kafka 发送失败 | topic={topic} | err={e}")

    def send_datas(self, result_models: Any) -> None:
        for result_model in result_models:
            data_dict = result_model.dict() if hasattr(result_model, "dict") else result_model
            try:
                account_id = data_dict.get("account_id")
                # logger.debug(f"发送账户数据 | account_id={account_id}")
            except Exception:
                logger.debug("发送汇总消息 | 统计字段不可用，跳过概览日志")
            self._send("google_ads", data_dict)

    # 仅保留结果统计发送方法

    def send_snapchat_campaigns_result(self, result_model: Any) -> None:
        """发送 Snapchat Campaigns 结果统计"""
        try:
            from schemas.xiaomi_item import KafkaMessageModel
            data_dict = result_model.dict() if hasattr(result_model, "dict") else result_model
            payload = KafkaMessageModel(
                message_type="crawl_result",
                source="snapchat_ads_crawler",
                data=data_dict,
            )
            self._send("snapchat_campaigns_result", payload.dict())
            logger.info("发送 Snapchat Campaigns 结果统计 成功")
        except Exception as e:
            logger.exception(f"发送 Snapchat Campaigns 结果统计 失败: {e}")

    def send_snapchat_adsets_result(self, result_model: Any) -> None:
        """发送 Snapchat AdSets 结果统计"""
        try:
            from schemas.xiaomi_item import KafkaMessageModel
            data_dict = result_model.dict() if hasattr(result_model, "dict") else result_model
            payload = KafkaMessageModel(
                message_type="crawl_result",
                source="snapchat_ads_crawler",
                data=data_dict,
            )
            self._send("snapchat_adsets_result", payload.dict())
            logger.info("发送 Snapchat AdSets 结果统计 成功")
        except Exception as e:
            logger.exception(f"发送 Snapchat AdSets 结果统计 失败: {e}")

    def flush(self) -> None:
        if not self.is_enabled():
            return
        try:
            assert self._producer is not None
            self._producer.flush()
            logger.debug("Kafka flush 完成")
        except Exception as e:
            logger.exception(f"Kafka flush 失败: {e}")

    def close(self) -> None:
        if not self.is_enabled():
            return
        try:
            assert self._producer is not None
            self._producer.flush()
            self._producer.close()
            logger.info("KafkaProducer 已关闭")
        except Exception as e:
            logger.exception(f"Kafka 关闭失败: {e}")

    # Joybuy 抓取结果发送
    def send_crawl_result(self, result: Any) -> None:
        try:
            data_dict = result.dict() if hasattr(result, "dict") else result
            self._send("crawl_result", data_dict)
            logger.info(f"发送抓取结果成功 | skuId={data_dict.get('skuId')}")
        except Exception as e:
            logger.exception(f"发送抓取结果失败: {e}")


    def push_crawl_result(self, result: Any) -> None:
        try:
            data_dict = result.dict() if hasattr(result, "dict") else result
            self._send("crawl_task", data_dict)
        except Exception as e:
            logger.exception(f"发送抓取结果失败: {e}")

    def send_plugin_data(self, data_dict: Dict[str, Any]) -> None:
        """发送插件格式的数据（直播采集数据）

        Args:
            data_dict: 插件格式的数据字典，包含以下字段：
                - params: 参数
                - cookies: cookies JSON字符串
                - fromUrl: 来源URL
                - extra: 请求体
                - sign: 签名
                - userType: 用户类型
                - updateTime: 更新时间戳
                - request: 包含response和url的字典
        """
        try:
            self._send("plugin_data", data_dict)
            # logger.debug(f"发送插件数据成功 | fromUrl={data_dict.get('fromUrl', '')[:100]}...")
        except Exception as e:
            logger.exception(f"发送插件数据失败: {e}")

    def send_to_topic(self, topic: str, data_dict: Dict[str, Any]) -> bool:
        """直接发送数据到指定 topic

        Args:
            topic: Kafka topic 名称
            data_dict: 要发送的数据字典

        Returns:
            bool: 发送是否成功
        """
        if not self.is_enabled():
            logger.debug(f"跳过发送，Kafka 未启用 | topic={topic}")
            return False
        try:
            assert self._producer is not None
            self._producer.send(topic, value=data_dict)
            logger.info(f"Kafka 发送成功 | topic={topic}")
            return True
        except Exception as e:
            logger.exception(f"Kafka 发送失败 | topic={topic} | err={e}")
            return False


# 单例便捷访问
producer_client = KafkaProducerClient()


if __name__ == '__main__':
    sku_list = [10010717,10031055,10017416,10023265,10025019,10044517,10001429,10004737,10027487,10010301,10018728,10004372,10001517,10003425,10030363,10020258,10001315,10027221,10001356,10034224,10023808,10025896,10001579,10016068,10000383,10022452,10010111,10001598,10001525,10020498,10001515,10001001,10017107,10013538,10004127,10003930,10000208,10015531,10009246,10001350,10017690,10021383,10014793,10018030,10001355,10015859,10021805,10014158,10039474,10044077,10035099,10035621,10035542,10006143,10017536,10034149,10031098,10003981,10001246,10001421,10023593,10000760,10001353,10001352,10001670,10028886,10006044,10010349,10023285,10001198,10019793,10028555,10025566,10001212,10098781,10023901,10000229,10024946,10005198,10023426,10007340,10022524,10018810,10028904,10012393,10002245,10022517,10038720,10036801,10036536,10039462,10010071,10035173,10043421,10017502,10003333,10012735,10002147,10025207,10005755,10021567,10033427,10002338,10003484,10040011,10001744,10039040,10025070,10026843,10004289,10039375,10000707,10003567,10039098,10276247,10284984,10313120,10368635,10326062,10356608,10358973,10326056,10363059,10350525,10337388,10359279,10416303,10412461,10432991,10427555,10409969,10421528,10427141,10431548,10427774,10009415,10014034,10036762,10036393,10018007,10030415,10013933,10014186,10014265,10025074,10036740,10014568,10013984,10030925,10046349,10046379,10018206,10014379,10018110,10009528,10014443,10031292,10031176,10030344,10030219,10018077,10045712,10014413,10042943,10025216,10045714,10014195,10046311,10030941,10014152,10004319,10030396,10010339,10006728,10031326,10034570,10045824,10014380,10012547,10006081,10009432,10018067,10031166,10030620,10014358,10030977,10010304,10018021,10014131,10008287,10018091,10013975,10031122,10017953,10014603,10008344,10006154,10031031,10007265,10025095,10043496,10026564,10031272,10018184,10014335,10031346,10014069,10043450,10014575,10014209,10014169,10038768,10026286,10019061,10014851,10014477,10027935,10030225,10031248,10045990,10014662,10013805,10010431,10014311,10031164,10018092,10014484,10026141,10031102,10030493,10031186,10025071,10009604,10014674,10013955,10025284,10006730,10014071,10015008,10031140,10031101,10009139,10013869,10000748,10014749,10022976,10014381,10014549,10014758,10018079,10000932,10010673,10031234,10014355,10026144,10030449,10046323,10014476,10046315,10030157,10014535,10014472,10030879,10030981,10014246,10026455,10025046,10018158,10043575,10031270,10027554,10099146,10014559,10014314,10007982,10031059,10010737,10031364,10010326,10045756,10031095,10017034,10031123,10030929,10045313,10014320,10030434,10009488,10030951,10010299,10019133,10004518,10030442,10014566,10030477,10025129,10046870,10014799,10044475,10031019,10031288,10018123,10030518,10014400,10015879,10014773,10043509,10031298,10014354,10019008,10036786,10031344,10027967,10045179,10031310,10006206,10014173,10014779,10014610,10030899,10014066,10014028,10013761,10030189,10030430,10044054,10005929,10038147,10014055,10014640,10046936,10036089,10014805,10031005,10031128,10018174,10099138,10046910,10009522,10014828,10010382,10003965,10030881,10010596,10014499,10031240,10031021,10018101,10009486,10028006,10009544,10014706,10018172,10027585,10025048,10009391,10031226,10013911,10046295,10009306,10014164,10030320,10004466,10018081,10031330,10007894,10000259,10014631,10030999,10025162,10003604,10014896,10026232,10044533,10030915,10030242,10030726,10026162,10014341,10046353,10014076,10031320,10015002,10036788,10030505,10027953,10018167,10030295,10043410,10026120,10046425,10014088,10004281,10014438,10010484,10014361,10014588,10010534,10014083,10018039,10005907,10044038,10030690,10046351,10036083,10047158,10014563,10031051,10030399,10030973,10030508,10036049,10036329,10031258,10044042,10043583,10036702,10031148,10099140,10031136,10041143,10026221,10007874,10000225,10013833,10005905,10027978,10043585,10036552,10029933,10030913,10010578,10008133,10045121,10028024,10009344,10031290,10026273,10030901,10014813,10014224,10027922,10014321,10026332,10030237,10018115,10031276,10014174,10022739,10025130,10036115,10025248,10036828,10018075,10026121,10014572,10028008,10014171,10025065,10018118,10030945,10008317,10001878,10045750,10014107,10014203,10013821,10031198,10026276,10031334,10007917,10003893,10030436,10025031,10031009,10031304,10018182,10030893,10030299,10030283,10015032,10031099,10014547,10014276,10010871,10025220,10017941,10031180,10030896,10003271,10026361,10031232,10027933,10013865,10028627,10030993,10030718,10045243,10026314,10030316,10026138,10025264,10043565,10045722,10005927,10040577,10003927,10030319,10044086,10028014,10030898,10044066,10044014,10007746,10030653,10098787,10026357,10045315,10012628,10026583,10031114,10013807,10031154,10030722,10014091,10018069,10031077,10030955,10098755,10030051,10014267,10003875,10010447,10018128,10026635,10014635,10014558,10014743,10014788,10045223,10045149,10019000,10030429,10046329,10030710,10042889,10026426,10043980,10031106,10045081,10046180,10014720,10031184,10014234,10031266,10043465,10004664,10026037,10031170,10036742,10031015,10014645,10031260,10025183,10014170,10009450,10018037,10014712,10031250,10014673,10027976,10028010,10038750,10025108,10013953,10030311,10018033,10010433,10031007,10014711,10026440,10013909,10031087,10014347,10014022,10014750,10046892,10030476,10014135,10008139,10045119,10031033,10044673,10030481,10025011,10007896,10018082,10003254,10030692,10030049,10014796,10014111,10014618,10031278,10036530,10041124,10014577,10045209,10038859,10006764,10014252,10004012,10046373,10026701,10044527,10014840,10018164,10031100,10031322,10031318,10010363,10046972,10018122,10009574,10014343,10031274,10036103,10008484,10043571,10010280,10031023,10009203,10031083,10099148,10014632,10008369,10031194,10030821,10031017,10014414,10014346,10014140,10031242,10014681,10036007,10031156,10018922,10046004,10030921,10045207,10036850,10018113,10030686,10014039,10030640,10031174,10018047,10014369,10018124,10031328,10018130,10025204,10046874,10030668,10040459,10014092,10046347,10030059,10018145,10014435,10014185,10008315,10031286,10030923,10025096,10018065,10031338,10030943,10009355,10031312,10014323,10009433,10030927,10031300,10025111,10014904,10014990,10031168,10014012,10043001,10046862,10031053,10031208,10030395,10030284,10036524,10010562,10031218,10031134,10046367,10014699,10014372,10014992,10031047,10004148,10016006,10018137,10014856,10030630,10098785,10030931,10014730,10030321,10035654,10014795,10031111,10031091,10031001,10046948,10018156,10043519,10045335,10014068,10031254,10018107,10018178,10030366,10014944,10014075,10014659,10046924,10045736,10018141,10044461,10043563,10031264,10030534,10017939,10036814,10014584,10045189,10031089,10031027,10014243,10030969,10018138,10008520,10014175,10031172,10014194,10030872,10018103,10006190,10031282,10043597,10030325,10026019,10027982,10007994,10030435,10045976,10005931,10018116,10030935,10038135,10014527,10030985,10013819,10018125,10031206,10008766,10038145,10009060,10014280,10014892,10014862,10030987,10017937,10010458,10046305,10100949,10213162,10295491,10213184,10295479,10206554,10294833,10212975,10206502,10381590,10377390,10397440,10388223,10313204,10312213,10313114,10389669,10312153,10324732,10389180,10389162,10396573,10392464,10369394,10377372,10376395,10376379,10388159,10378877,10312161,10399119,10382196,10368837,10392376,10390346,10392422,10381159,10396593,10393932,10312225,10379988,10389224,10378893,10391565,10312205,10397442,10390278,10379912,10377384,10313170,10390280,10377314,10379880,10388173,10389202,10379936,10389411,10391567,10313166,10389443,10313140,10388201,10389208,10389160,10378123,10392468,10326202,10313168,10313174,10376381,10388161,10378695,10313158,10313156,10410766,10426401,10406898,10409961,10406916,10426728,10411026,10400082,10402870,10400050,10400018,10410273,10410660,10426726,10412107,10410992,10410003,10410728,10400084,10409997,10432363,10426712,10410764,10400080,10426736,10400042,10410658,10410784,10410990,10410726,10410253,10406986,10410744,10410221,10409975,10410219,10426686,10410958,10432321]

    result = [
        {
            "skuId": i,
            "skuUrl": f"https://www.joybuy.co.uk/dp/{i}"
        }
        for i in sku_list

]
    producer_client.push_crawl_result(result)
    producer_client.flush()
