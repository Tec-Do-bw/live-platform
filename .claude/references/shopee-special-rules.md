# Shopee 特殊规则

## 规则一：page_urls 只用 com.my 作模板

`config_base.py` 中 shopee 的 `page_urls` 统一写 `shopee.com.my`。

`ShopeeLiveCrawler.__init__` 运行时深拷贝后替换域名，不要在配置文件里写其他国家域名。

## 规则二：时间参数必须使用对应国家时区的 T-1

Shopee API 请求中的 `endDate` 参数必须动态计算为对应国家时区的昨天日期，禁止硬编码。

### 时区映射（`ShopeeLiveCrawler.SHOPEE_TIMEZONE_MAP`）
- 马来西亚 (`com.my`): UTC+8
- 新加坡 (`com.sg`): UTC+8
- 印尼 (`co.id`): UTC+7
- 泰国 (`co.th`): UTC+7
- 越南 (`vn`): UTC+7
- 巴西 (`com.br`): UTC-3
- 墨西哥 (`com.mx`): UTC-6

### 实现方式
通过 `_get_country_yesterday()` 方法计算：
1. 根据 `country_domain` 获取时区偏移量
2. 计算该时区的当前时间
3. 返回昨天日期（YYYY-MM-DD 格式）

### 应用位置
- `_build_live_list_params()` - liveList/v2 接口的 `endDate` 参数
- `_build_overview_params()` - overview/v3 和 metricTrend/v2 接口的 `endDate` 参数

## 规则三：多国域名映射

`ShopeeLiveCrawler.SHOPEE_COUNTRY_MAP` 根据 AdsPower 分组名中的关键词匹配域名：

| 关键词 | 域名 |
|--------|------|
| 马来 | `com.my` |
| 印尼 | `co.id` |
| 泰国 | `co.th` |
| 新加坡 | `sg` |
| 越南 | `vn` |
| 巴西 | `com.br` |
| 墨西哥 | `com.mx` |
| 默认 | `com.my` |

## 规则四：JS 注入模式采集

通过 `run_js_fetch()` 在页面加载后直接调用 API，不依赖网络拦截。

接口规范详见 `services/live-crawler/docs/specs/shopee-数仓对接文档.md`。

## 规则五：补采自动跳过

Shopee 使用 JS 注入模式，不支持 HTTP 补采。

`gap_detector._is_shopee_gap()` 判断缺口是否属于 Shopee 账号，自动跳过补采。

## 规则六：登出恢复不触发即时全量

详见同目录下 `collection-mode-rules.md` 中的"特殊规则：Shopee 不触发即时恢复"章节。
