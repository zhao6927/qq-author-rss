# RSS 全文订阅源

把腾讯新闻作者主页、少数派官方 RSS 转成**全文版** RSS 订阅源，GitHub Actions 每小时自动更新。

| 订阅源 | 数据来源 | 订阅文件 |
|---|---|---|
| 邸钞（腾讯新闻作者） | 作者主页 | `dichao.xml` |
| 虎嗅APP（腾讯新闻作者） | 作者主页 | `huxiu.xml` |
| 少数派（全文版） | 官方 RSS（只给摘要，本仓库逐篇抓文章页补全文） | `sspai.xml` |

- 生成脚本: `generate_feeds.py`（标准库 only，无第三方依赖）
- 自动更新: `.github/workflows/update-feed.yml` 每小时第 7 分钟运行，只有 XML 变化时才提交

## 订阅地址

- 邸钞: `https://zhao6927.github.io/qq-author-rss/dichao.xml`
- 虎嗅APP: `https://zhao6927.github.io/qq-author-rss/huxiu.xml`
- 少数派全文版: `https://zhao6927.github.io/qq-author-rss/sspai.xml`

国内访问更快（jsDelivr CDN）: 把上面域名换成 `https://cdn.jsdelivr.net/gh/zhao6927/qq-author-rss@main/` 即可。

## 本地运行

```bash
python3 generate_feeds.py   # 在仓库根目录生成全部 XML
```
