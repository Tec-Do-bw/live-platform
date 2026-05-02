"""
向后兼容层：转发到新的 crawlers.browser.live_crawler

此文件保留用于向后兼容，所有新代码应直接使用 crawlers.browser.live_crawler
"""
from crawlers.browser.live_crawler import LiveCrawler

__all__ = ['LiveCrawler']
