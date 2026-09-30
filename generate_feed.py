#!/usr/bin/env python3
"""把腾讯新闻作者「邸钞」的主页文章列表转成 RSS 2.0 feed.

数据源: https://i.news.qq.com/getSubNewsMixedList?guestSuid=...&tabId=om_index
用法: python3 generate_feed.py [输出路径, 默认 ./dichao.xml]
"""
import html
import json
import sys
import urllib.request
from datetime import datetime, timezone, timedelta
from email.utils import format_datetime
from pathlib import Path
from xml.sax.saxutils import escape

AUTHOR_SUID = "8QIf3nxc64AYuDfe4wc="
AUTHOR_PAGE = f"https://news.qq.com/omn/author/{AUTHOR_SUID}"
API_URL = f"https://i.news.qq.com/getSubNewsMixedList?guestSuid={AUTHOR_SUID}&tabId=om_index"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")
BEIJING = timezone(timedelta(hours=8))


def fetch_articles():
    req = urllib.request.Request(API_URL, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    if data.get("ret") != 0:
        raise RuntimeError(f"API 返回异常: ret={data.get('ret')} errmsg={data.get('errmsg')}")
    return data.get("newslist") or []


def rfc822(ts: int) -> str:
    return format_datetime(datetime.fromtimestamp(ts, tz=BEIJING))


def build_rss(articles) -> str:
    # 作者信息取第一篇的 card 字段, 兜底用已知值
    card = (articles[0].get("card") or {}) if articles else {}
    author_name = card.get("chlname") or "邸钞"
    author_desc = card.get("desc") or "分享有价值的文章,拓宽眼界视野。"
    icon = card.get("icon") or ""

    items = []
    for a in articles:
        title = a.get("title") or a.get("longtitle") or ""
        link = a.get("url") or a.get("surl") or ""
        guid = a.get("id") or link
        abstract = a.get("abstract") or ""
        ts = a.get("timestamp") or 0
        pub_date = rfc822(ts) if ts else ""
        thumbs = a.get("thumbnails_qqnews") or a.get("thumbnails") or []
        # 描述里附上首图, 方便阅读器展示
        desc_html = ""
        if thumbs:
            desc_html += f'<p><img src="{escape(thumbs[0], {"\"" : "&quot;"})}" /></p>'
        if abstract:
            desc_html += f"<p>{escape(abstract)}</p>"

        items.append(
            "    <item>\n"
            f"      <title>{escape(title)}</title>\n"
            f"      <link>{escape(link)}</link>\n"
            f'      <guid isPermaLink="false">{escape(str(guid))}</guid>\n'
            + (f"      <pubDate>{pub_date}</pubDate>\n" if pub_date else "")
            + (f"      <description><![CDATA[{desc_html}]]></description>\n" if desc_html else "")
            + f"      <author>{escape(author_name)}</author>\n"
            "    </item>"
        )

    now = format_datetime(datetime.now(tz=BEIJING))
    channel_image = ""
    if icon:
        channel_image = (
            "    <image>\n"
            f"      <url>{escape(icon)}</url>\n"
            f"      <title>{escape(author_name)}</title>\n"
            f"      <link>{escape(AUTHOR_PAGE)}</link>\n"
            "    </image>\n"
        )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">\n'
        "  <channel>\n"
        f"    <title>{escape(author_name)} - 腾讯新闻</title>\n"
        f"    <link>{escape(AUTHOR_PAGE)}</link>\n"
        f"    <description>{escape(author_desc)}</description>\n"
        "    <language>zh-cn</language>\n"
        f"    <lastBuildDate>{now}</lastBuildDate>\n"
        f'    <atom:link href="{escape(AUTHOR_PAGE)}" rel="self" type="application/rss+xml" />\n'
        f"    <generator>qq-author-rss (i.news.qq.com)</generator>\n"
        f"    <ttl>60</ttl>\n"
        + channel_image
        + "\n".join(items)
        + "\n  </channel>\n</rss>\n"
    )


def main():
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent / "dichao.xml"
    articles = fetch_articles()
    print(f"抓到 {len(articles)} 篇文章")
    rss = build_rss(articles)
    out.write_text(rss, encoding="utf-8")
    print(f"已写入 {out} ({len(rss)} 字符)")


if __name__ == "__main__":
    main()
