#!/usr/bin/env python3
"""多作者 RSS 生成: 抓腾讯新闻作者接口, 为每个作者生成一个 XML。

作者列表见 FEEDS, 新增作者只需加一行 (guestSuid, 输出文件名),
无需改动 GitHub Actions workflow。
"""
import json
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from email.utils import format_datetime
from pathlib import Path
from xml.sax.saxutils import escape

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")
BEIJING = timezone(timedelta(hours=8))

# (guestSuid, 输出文件名) —— guestSuid 末尾的 = 是 ID 的一部分, 不要去掉
FEEDS = [
    ("8QIf3nxc64AYuDfe4wc=", "dichao.xml"),  # 邸钞
    ("8QMf13ld5I0VujvR", "huxiu.xml"),       # 虎嗅APP
]


def api_url(suid):
    return f"https://i.news.qq.com/getSubNewsMixedList?guestSuid={suid}&tabId=om_index"


def author_page(suid):
    return f"https://news.qq.com/omn/author/{suid}"


def fetch_articles(suid):
    req = urllib.request.Request(api_url(suid), headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    if data.get("ret") != 0:
        raise RuntimeError(f"API 返回异常: ret={data.get('ret')} errmsg={data.get('errmsg')}")
    return data.get("newslist") or []


def rfc822(ts):
    return format_datetime(datetime.fromtimestamp(ts, tz=BEIJING))


def build_rss(suid, articles):
    # 作者信息取第一篇的 card 字段, 兜底用已知值
    card = (articles[0].get("card") or {}) if articles else {}
    page = author_page(suid)
    author_name = card.get("chlname") or suid
    author_desc = card.get("desc") or ""
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
            f"      <link>{escape(page)}</link>\n"
            "    </image>\n"
        )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">\n'
        "  <channel>\n"
        f"    <title>{escape(author_name)} - 腾讯新闻</title>\n"
        f"    <link>{escape(page)}</link>\n"
        f"    <description>{escape(author_desc)}</description>\n"
        "    <language>zh-cn</language>\n"
        f"    <lastBuildDate>{now}</lastBuildDate>\n"
        f'    <atom:link href="{escape(page)}" rel="self" type="application/rss+xml" />\n'
        "    <generator>qq-author-rss (i.news.qq.com)</generator>\n"
        "    <ttl>60</ttl>\n"
        + channel_image
        + "\n".join(items)
        + "\n  </channel>\n</rss>\n"
    )


def old_ids(path):
    """读出现有 XML 的 guid 列表, 用于判断是否有新文章。"""
    if not path.exists():
        return None
    try:
        items = ET.parse(path).getroot().find("channel").findall("item")
        return [i.findtext("guid") for i in items]
    except Exception:
        return None


def main():
    base = Path(__file__).parent
    changed = []
    for suid, fname in FEEDS:
        out = base / fname
        articles = fetch_articles(suid)
        print(f"{fname}: 抓到 {len(articles)} 篇")
        new_ids = [str(a.get("id")) for a in articles]
        if new_ids == old_ids(out):
            print(f"{fname}: 无新文章, 跳过")
            continue
        out.write_text(build_rss(suid, articles), encoding="utf-8")
        print(f"{fname}: 有新文章, 已写入")
        changed.append(fname)
    if not changed:
        print("没有 feed 发生变化")


if __name__ == "__main__":
    main()
