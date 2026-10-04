#!/usr/bin/env python3
"""多源 RSS 生成: 腾讯新闻作者 + 少数派, 统一生成全文版 XML。

腾讯作者列表见 FEEDS, 新增作者只需加一行 (guestSuid, 输出文件名),
无需改动 GitHub Actions workflow。
少数派见 SSPAI_FILE, 抓官方 RSS 再逐篇抓文章页全文。

正文抓取:
- 腾讯: 文章页 window.DATA -> originContent.text (全文 HTML),
  <!--IMG_N--> 占位符用 originAttribute 里的真实图片地址替换。
- 少数派: 文章页 div.article-body 的 innerHTML, 白名单清洗后保留。
抓不到正文时回退为摘要。
"""
import json
import re
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from email.utils import format_datetime
from html import unescape as html_unescape
from html.parser import HTMLParser
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


def extract_window_data(html):
    """从文章页 HTML 里抠出 window.DATA 的 JSON 对象。"""
    s = html.find("window.DATA = ")
    if s < 0:
        return None
    s += len("window.DATA = ")
    depth, instr, esc, i = 0, False, False, s
    end = None
    while i < len(html):
        c = html[i]
        if instr:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                instr = False
        else:
            if c == '"':
                instr = True
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        i += 1
    if not end:
        return None
    return json.loads(html[s:end])


def fetch_fulltext(article_url):
    """抓文章全文 HTML, 图片占位符替换为真实地址。失败返回 None。"""
    try:
        req = urllib.request.Request(article_url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=30) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
        data = extract_window_data(html)
        if not data:
            return None
        oc = data.get("originContent") or {}
        text = oc.get("text") or ""
        if not text.strip():
            return None
        attrs = data.get("originAttribute") or {}

        def img_tag(m):
            info = attrs.get(m.group(1)) or {}
            url = (info.get("imgurl641") or info.get("imgurl0")
                   or info.get("bigOrigUrl") or "")
            if not url:
                return ""
            return f'<img src="{escape(url, {"\"": "&quot;"})}" />'

        return re.sub(r"<!--(IMG_\d+)-->", img_tag, text)
    except Exception:
        return None


# ---------------- 少数派全文源 ----------------
SSPAI_FEED_URL = "https://sspai.com/feed"
SSPAI_FILE = "sspai.xml"
SSPAI_SITE = "https://sspai.com"

# 正文清洗白名单
SSPAI_KEEP_TAGS = {
    "p", "br", "h1", "h2", "h3", "h4", "h5", "h6",
    "blockquote", "ul", "ol", "li", "pre", "code",
    "a", "img", "strong", "b", "em", "i", "u", "del", "s",
    "hr", "figure", "figcaption",
    "table", "thead", "tbody", "tr", "td", "th",
    "div", "span", "section",
}
SSPAI_VOID_TAGS = {"img", "br", "hr"}
SSPAI_DROP_TAGS = {"script", "style", "iframe", "form", "input", "button",
                   "select", "textarea", "noscript"}
# 正文里不要的元素 (class 关键字匹配): 打赏卡片等
SSPAI_DROP_CLASS = ("article__charge__card", "article__share__panel")


class _SspaiBodyParser(HTMLParser):
    """抠出 div.article-body 的 innerHTML, 白名单清洗后输出干净 HTML。"""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.in_body = False
        self.depth = 0
        self.drop_depth = 0
        self.stack = []
        self.out = []

    @staticmethod
    def _abs(url):
        url = (url or "").strip()
        if url.startswith("//"):
            return "https:" + url
        if url.startswith("/"):
            return SSPAI_SITE + url
        return url

    def handle_starttag(self, tag, attrs):
        d = dict(attrs)
        if not self.in_body:
            if tag == "div" and "article-body" in d.get("class", ""):
                self.in_body = True
                self.depth = 1
            return
        self.depth += 1
        if self.drop_depth:
            return
        if tag in SSPAI_DROP_TAGS or any(
                k in d.get("class", "") for k in SSPAI_DROP_CLASS):
            self.drop_depth = self.depth
            return
        if tag not in SSPAI_KEEP_TAGS:
            return
        if tag == "img":
            src = self._abs(d.get("src") or d.get("data-src") or "")
            if not src:
                return
            alt = escape(d.get("alt") or "", {'"': "&quot;"})
            self.out.append(
                f'<img src="{escape(src, {"\"": "&quot;"})}" alt="{alt}"/>')
        elif tag == "a":
            href = self._abs(d.get("href") or "")
            self.out.append(f'<a href="{escape(href, {"\"": "&quot;"})}">')
            self.stack.append("a")
        elif tag in SSPAI_VOID_TAGS:
            self.out.append(f"<{tag}/>")
        else:
            self.out.append(f"<{tag}>")
            self.stack.append(tag)

    def handle_endtag(self, tag):
        if not self.in_body:
            return
        if self.drop_depth:
            if self.depth == self.drop_depth:
                self.drop_depth = 0
            self.depth -= 1
            return
        self.depth -= 1
        if self.depth <= 0:
            self.in_body = False
            while self.stack:
                self.out.append(f"</{self.stack.pop()}>")
            return
        if self.stack and self.stack[-1] == tag:
            self.out.append(f"</{tag}>")
            self.stack.pop()

    def handle_data(self, data):
        if self.in_body and not self.drop_depth and data.strip():
            self.out.append(escape(data))


def fetch_sspai_feed():
    """抓少数派官方 RSS, 返回 (channel信息, 文章列表)。"""
    req = urllib.request.Request(SSPAI_FEED_URL, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as resp:
        xml_text = resp.read().decode("utf-8")
    channel = ET.fromstring(xml_text).find("channel")
    items = []
    for it in channel.findall("item"):
        link = (it.findtext("link") or "").strip()
        if not link:
            continue
        items.append({
            "title": (it.findtext("title") or "").strip(),
            "link": link,
            "guid": link,
            "pub_date": (it.findtext("pubDate") or "").strip(),
            "author": (it.findtext("author") or "").strip(),
            "excerpt": (it.findtext("description") or "").strip(),
        })
    info = {
        "title": (channel.findtext("title") or "少数派").strip(),
        "link": (channel.findtext("link") or SSPAI_SITE).strip(),
        "description": (channel.findtext("description") or "").strip(),
    }
    return info, items


def fetch_sspai_fulltext(url):
    """抓少数派文章页全文 HTML (清洗后)。失败返回 None。"""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=30) as resp:
            html_text = resp.read().decode("utf-8", errors="ignore")
        p = _SspaiBodyParser()
        p.feed(html_text)
        body = "".join(p.out).strip()
        text_len = len(re.sub(r"<[^>]+>", "", body).strip())
        if text_len < 100:  # 正文过短, 视为抓取失败
            return None
        return body
    except Exception:
        return None


def build_sspai_rss(channel, items):
    rss_items = []
    for a in items:
        full = a.get("full")
        if full:
            desc = full + f'<p><a href="{escape(a["link"])}">阅读原文</a></p>'
        else:
            # 官方摘要已是转义后的 HTML, 解开后直接用
            desc = html_unescape(a.get("excerpt") or "")
        # 每段首行缩进两格
        desc = indent_paragraphs(desc)
        rss_items.append(
            "    <item>\n"
            f"      <title>{escape(a['title'])}</title>\n"
            f"      <link>{escape(a['link'])}</link>\n"
            f'      <guid isPermaLink="false">{escape(a["guid"])}</guid>\n'
            + (f"      <pubDate>{escape(a['pub_date'])}</pubDate>\n"
               if a.get("pub_date") else "")
            + (f"      <description><![CDATA[{desc}]]></description>\n"
               if desc else "")
            + (f"      <author>{escape(a['author'])}</author>\n"
               if a.get("author") else "")
            + "    </item>"
        )
    now = format_datetime(datetime.now(tz=BEIJING))
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">\n'
        "  <channel>\n"
        f"    <title>{escape(channel['title'])}（全文版）</title>\n"
        f"    <link>{escape(channel['link'])}</link>\n"
        f"    <description>{escape(channel['description'])}</description>\n"
        "    <language>zh-cn</language>\n"
        f"    <lastBuildDate>{now}</lastBuildDate>\n"
        f'    <atom:link href="{SSPAI_SITE}/feed" rel="self"'
        ' type="application/rss+xml" />\n'
        "    <generator>qq-author-rss (sspai.com)</generator>\n"
        "    <ttl>60</ttl>\n"
        + "\n".join(rss_items)
        + "\n  </channel>\n</rss>\n"
    )


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
        ts = a.get("timestamp") or 0
        pub_date = rfc822(ts) if ts else ""

        # 全文优先, 失败回退摘要
        full = fetch_fulltext(link) if link else None
        if full:
            desc_html = full + f'<p><a href="{escape(link)}">阅读原文</a></p>'
        else:
            abstract = a.get("abstract") or ""
            thumbs = a.get("thumbnails_qqnews") or a.get("thumbnails") or []
            desc_html = ""
            if thumbs:
                desc_html += f'<p><img src="{escape(thumbs[0], {"\"" : "&quot;"})}" /></p>'
            if abstract:
                desc_html += f"<p>{escape(abstract)}</p>"
        # 每段首行缩进两格
        desc_html = indent_paragraphs(desc_html)

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


def indent_paragraphs(html):
    """给所有 <p> 段落加首行缩进两个汉字 (text-indent:2em)。"""
    def repl(m):
        attrs = m.group(1) or ""
        if "text-indent" in attrs:
            return m.group(0)
        sm = re.search(r'style="([^"]*)"', attrs)
        if sm:
            new_style = sm.group(1).rstrip(";") + ";text-indent:2em;"
            new_attrs = (attrs[:sm.start()] + 'style="' + new_style + '"'
                         + attrs[sm.end():])
            return "<p" + new_attrs + ">"
        return '<p' + attrs + ' style="text-indent:2em;">'
    return re.sub(r"<p(\s[^>]*)?>", repl, html)


def has_indent(path):
    """判断现有 XML 是否已带段落缩进 (首篇 description 含 text-indent)。"""
    if not path.exists():
        return False
    try:
        items = ET.parse(path).getroot().find("channel").findall("item")
        if not items:
            return False
        d = items[0].findtext("description") or ""
        return "text-indent" in d
    except Exception:
        return False


def has_fulltext(path):
    """判断现有 XML 是否已是全文版 (首篇 description 含全文标记)。"""
    if not path.exists():
        return False
    try:
        items = ET.parse(path).getroot().find("channel").findall("item")
        if not items:
            return False
        d = items[0].findtext("description") or ""
        return "阅读原文" in d
    except Exception:
        return False


def main():
    base = Path(__file__).parent
    changed = []
    for suid, fname in FEEDS:
        out = base / fname
        articles = fetch_articles(suid)
        print(f"{fname}: 抓到 {len(articles)} 篇", flush=True)
        new_ids = [str(a.get("id")) for a in articles]
        # ID 没变、已有全文且已带缩进 -> 跳过; 否则重写
        if new_ids == old_ids(out) and has_fulltext(out) and has_indent(out):
            print(f"{fname}: 无新文章, 跳过", flush=True)
            continue
        print(f"{fname}: 生成全文 RSS...", flush=True)
        out.write_text(build_rss(suid, articles), encoding="utf-8")
        print(f"{fname}: 已写入", flush=True)
        changed.append(fname)

    # ---------- 少数派全文源 ----------
    out = base / SSPAI_FILE
    try:
        sspai_channel, sspai_items = fetch_sspai_feed()
        print(f"{SSPAI_FILE}: 抓到 {len(sspai_items)} 篇", flush=True)
    except Exception as e:
        print(f"{SSPAI_FILE}: 官方源抓取失败: {e}", flush=True)
        sspai_items = []
    if sspai_items:
        new_ids = [a["guid"] for a in sspai_items]
        if new_ids == old_ids(out) and has_fulltext(out) and has_indent(out):
            print(f"{SSPAI_FILE}: 无新文章, 跳过", flush=True)
        else:
            print(f"{SSPAI_FILE}: 生成全文 RSS...", flush=True)
            for a in sspai_items:
                a["full"] = fetch_sspai_fulltext(a["link"])
                mark = "全文" if a["full"] else "摘要回退"
                print(f"  [{mark}] {a['title'][:26]}", flush=True)
            out.write_text(build_sspai_rss(sspai_channel, sspai_items),
                           encoding="utf-8")
            print(f"{SSPAI_FILE}: 已写入", flush=True)
            changed.append(SSPAI_FILE)

    if not changed:
        print("没有 feed 发生变化")


if __name__ == "__main__":
    main()
