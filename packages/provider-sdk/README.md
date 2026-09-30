# Provider SDK

Python SDK 的唯一实现位于 `apps/api/src/jc/providers/base.py` 和 `contracts.py`。
安装根目录 Python 包后 `from jc.providers.base import OddsProvider`。
每个供应商实现 fetch_matches、fetch_odds、normalize；历史获取默认显式报告不支持。
FetchedPayload 保存来源、采集时间、HTTP 状态、Raw ID、mock 标记；OddsQuote 使用 Decimal。
业务层只依赖此接口。新增 Adapter 后通过 registry 注册，不改写业务采集逻辑。
