"""Real RSS/Atom parsing and finite feed discovery, with SSRF protection."""
import html
import ipaddress
import re
import socket
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from html.parser import HTMLParser


def url(value):
    u = urllib.parse.urlsplit(value.strip())
    if u.scheme not in ('http', 'https') or not u.hostname or u.username or u.password:
        raise ValueError('请提供有效的 http(s) 地址，不能嵌入账号或密码')
    return urllib.parse.urlunsplit((u.scheme.lower(), u.netloc.lower(), u.path or '/', u.query, ''))


def check_public(value):
    value = url(value)
    u = urllib.parse.urlsplit(value)
    if any(not ipaddress.ip_address(a[4][0]).is_global for a in socket.getaddrinfo(u.hostname, u.port or (443 if u.scheme == 'https' else 80), type=socket.SOCK_STREAM)):
        raise ValueError('信息源只支持公开互联网地址；已拒绝本地、内网和保留地址')
    return value


class Redirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return super().redirect_request(req, fp, code, msg, headers, check_public(newurl))


def fetch(value):
    value = check_public(value)
    req = urllib.request.Request(value, headers={'User-Agent': 'ProjectFlow/0.2 (local RSS reader)', 'Accept': 'application/rss+xml, application/atom+xml, text/html, application/xml'})
    try:
        with urllib.request.build_opener(Redirect()).open(req, timeout=20) as r:
            data = r.read(4 * 1024 * 1024 + 1)
            final = r.url
        if len(data) > 4 * 1024 * 1024:
            raise ValueError('内容超过 4MB')
        return data, final
    except (OSError, urllib.error.URLError):
        raise ValueError('无法获取信息源，请检查公开网址和网络；可改为手动添加文章') from None


def plain(value):
    value = re.sub(r'<(script|style)\b[^>]*>.*?</\1>', '', value, flags=re.S | re.I)
    return html.unescape(re.sub('<[^>]+>', '', value)).strip()


def parse_feed(data, base=''):
    if b'<!DOCTYPE' in data.upper() or b'<!ENTITY' in data.upper():
        raise ValueError('不接受带 DTD / 实体定义的订阅文件')
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        raise ValueError('不是有效 RSS / Atom；请使用订阅链接或发现入口') from None
    local = lambda tag: tag.rsplit('}', 1)[-1]
    if local(root.tag).lower() not in ('rss', 'feed', 'rdf'):
        raise ValueError('不是 RSS / Atom')
    articles = []
    for item in root.iter():
        if local(item.tag) not in ('item', 'entry'):
            continue
        values, link = {}, ''
        for child in item:
            key = local(child.tag)
            values[key] = ''.join(child.itertext()).strip()
            if key == 'link' and child.attrib.get('rel', 'alternate') == 'alternate':
                link = child.attrib.get('href') or child.text or ''
        title = plain(values.get('title', ''))
        text = plain(values.get('encoded') or values.get('content') or values.get('description') or values.get('summary', ''))
        try:
            link = url(urllib.parse.urljoin(base, link.strip())) if link else ''
        except ValueError:
            link = ''
        if title:
            articles.append({'title': title, 'url': link, 'content': text[:50000], 'excerpt': True,
                             'external_id': values.get('guid') or values.get('id') or link or title})
        if len(articles) >= 50:
            break
    return articles


class FeedLinks(HTMLParser):
    def __init__(self, base):
        super().__init__()
        self.base, self.links = base, []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == 'link' and 'alternate' in a.get('rel', '').split() and a.get('type', '') in ('application/rss+xml', 'application/atom+xml'):
            try:
                self.links.append({'title': a.get('title') or '发现的订阅源', 'url': url(urllib.parse.urljoin(self.base, a.get('href', '')))})
            except ValueError:
                pass


def discover(address):
    raw, final = fetch(address)
    try:
        parse_feed(raw, final)
        return [{'title': '已验证的 RSS / Atom', 'url': final}]
    except ValueError:
        parser = FeedLinks(final)
        parser.feed(raw.decode('utf-8', errors='replace'))
        found = []
        for item in parser.links[:6]:
            try:
                body, verified = fetch(item['url'])
                parse_feed(body, verified)
                if not any(x['url'] == verified for x in found):
                    found.append({**item, 'url': verified})
            except ValueError:
                continue
        return found
