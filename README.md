# 邸钞 · 腾讯新闻作者 RSS

把腾讯新闻作者「邸钞」的主页文章转成 RSS 订阅源，每小时自动更新。

- 作者主页: https://news.qq.com/omn/author/8QIf3nxc64AYuDfe4wc=
- 数据接口: `https://i.news.qq.com/getSubNewsMixedList?guestSuid=8QIf3nxc64AYuDfe4wc=&tabId=om_index`（免登录 GET 即可）
- 生成脚本: `generate_feed.py`（标准库 only，无第三方依赖）
- 订阅文件: `dichao.xml`（RSS 2.0，每小时刷新一次）

## 订阅地址

- `https://zhao6927.github.io/qq-author-rss/dichao.xml`
- 国内访问更快（jsDelivr CDN）: `https://cdn.jsdelivr.net/gh/zhao6927/qq-author-rss@main/dichao.xml`

## 本地运行

```bash
python3 generate_feed.py            # 输出到 ./dichao.xml
python3 generate_feed.py /tmp/feed.xml
```
