"""Bounded, public-HTTPS ticket discovery. No site-specific adapters or checkout."""
import http.client
import json
import re
import socket
import ssl
from datetime import datetime, timezone
from html.parser import HTMLParser
from ipaddress import ip_address
from urllib.parse import urljoin, urlsplit

from travel_preparation import TicketOption, public_https

MAX_BYTES = 2_000_000


class _PinnedHTTPS(http.client.HTTPSConnection):
    def connect(self):
        addresses = socket.getaddrinfo(self.host, 443, type=socket.SOCK_STREAM)
        if not addresses or any(not ip_address(a[4][0]).is_global for a in addresses):
            raise ValueError("购票链接必须指向公开网站")
        # Connect to the validated IP; TLS still verifies the original hostname.
        sock = socket.create_connection((addresses[0][4][0], 443), self.timeout)
        try:
            self.sock = ssl.create_default_context().wrap_socket(sock, server_hostname=self.host)
        except Exception:
            sock.close()
            raise


def fetch_page(url):
    for _ in range(4):
        public_https(url)
        parsed = urlsplit(url)
        connection = _PinnedHTTPS(parsed.hostname, timeout=4)
        try:
            path = parsed.path or "/"
            if parsed.query:
                path += "?" + parsed.query
            connection.request("GET", path, headers={"User-Agent": "Jiandi-TicketPreview/1.0", "Accept": "text/html,application/ld+json", "Accept-Encoding": "identity"})
            response = connection.getresponse()
            if response.status in (301, 302, 303, 307, 308):
                location = response.getheader("Location")
                if not location:
                    raise ValueError("购票页面未提供跳转地址")
                url = urljoin(url, location)
                continue
            if response.status != 200:
                raise ValueError("购票页面暂不能读取")
            content_type = response.getheader("Content-Type", "").lower()
            if not any(t in content_type for t in ("text/html", "application/ld+json", "application/json")):
                raise ValueError("链接不是可解析的购票网页")
            if response.getheader("Content-Encoding", "identity") != "identity":
                raise ValueError("网页压缩格式暂不支持")
            body = response.read(MAX_BYTES + 1)
            if len(body) > MAX_BYTES:
                raise ValueError("购票网页过大，保留官方入口")
            return body.decode("utf-8", errors="replace"), url
        finally:
            connection.close()
    raise ValueError("购票链接跳转过多")


class _Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.blocks, self.buffer, self.active = [], [], False
        self.tables, self.rows, self.row, self.cell = [], None, None, None

    def handle_starttag(self, tag, attrs):
        if tag == "table": self.rows = []
        if tag == "tr" and self.rows is not None: self.row = []
        if tag in ("td", "th") and self.row is not None: self.cell = []
        if tag == "script":
            self.active = (dict(attrs).get("type") or "").lower() == "application/ld+json"
            self.buffer = []

    def handle_data(self, data):
        if self.cell is not None: self.cell.append(data)
        if self.active:
            self.buffer.append(data)

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self.cell is not None and self.row is not None:
            self.row.append(" ".join("".join(self.cell).split()))
            self.cell = None
        if tag == "tr" and self.row is not None and self.rows is not None:
            self.rows.append(self.row)
            self.row = None
        if tag == "table" and self.rows is not None:
            self.tables.append(self.rows)
            self.rows = None
        if tag == "script" and self.active:
            self.blocks.append("".join(self.buffer))
            self.active = False


def extract_tickets(html, source_url):
    page = _Page()
    page.feed(html)
    blocks = page.blocks or ([html] if html.lstrip().startswith(("{", "[")) else [])
    found, seen = [], set()

    def visit(node, depth=0):
        if depth > 30 or len(found) >= 30:
            return
        if isinstance(node, list):
            for item in node:
                visit(item, depth + 1)
        elif isinstance(node, dict):
            kinds = node.get("@type", [])
            kinds = [kinds] if isinstance(kinds, str) else kinds
            if isinstance(kinds, list) and {k for k in kinds if isinstance(k, str)} & {"Product", "Event", "TouristTrip", "Service"}:
                offers = node.get("offers", [])
                if isinstance(offers, dict):
                    offers = offers.get("offers", offers)
                offers = offers if isinstance(offers, list) else [offers]
                for offer in offers:
                    if not isinstance(offer, dict):
                        continue
                    name = offer.get("name") or node.get("name")
                    if not isinstance(name, str) or not name.strip():
                        continue
                    raw_url = offer.get("url") or node.get("url") or source_url
                    if not isinstance(raw_url, str):
                        continue
                    try:
                        url = public_https(urljoin(source_url, raw_url))
                        price = str(offer.get("price", ""))
                        currency = str(offer.get("priceCurrency", ""))
                        # Price ranges/aggregate lowPrice are not individual ticket prices.
                        if currency != "CNY":
                            price = ""
                        description = node.get("description", "")
                        ticket = TicketOption(title=name[:80], subtitle="", price=price,
                            description=description[:4000] if isinstance(description, str) else "",
                            purchase_url=url, source_url=source_url,
                            checked_at=datetime.now(timezone.utc).isoformat())
                    except (ValueError, TypeError):
                        continue
                    key = (ticket.title, ticket.purchase_url, ticket.price)
                    if key not in seen:
                        seen.add(key)
                        found.append(ticket.model_dump())
            for value in node.values():
                if isinstance(value, (dict, list)):
                    visit(value, depth + 1)
    for block in blocks:
        try:
            visit(json.loads(block))
        except (ValueError, RecursionError):
            continue
    # Common ticket tables are parsed only when they explicitly name ticket and
    # RMB price columns. Marketing paragraphs and arbitrary numbers are ignored.
    if not found:
        for rows in page.tables:
            if len(rows) < 2: continue
            header = rows[0]
            title_col = next((i for i, h in enumerate(header) if re.fullmatch(r"票种|票型|票类|门票名称|门票类型", h)), None)
            price_col = next((i for i, h in enumerate(header) if re.fullmatch(r"(?:门票价格|票价|价格)(?:[（(]元[）)])?", h)), None)
            if title_col is None or price_col is None: continue
            for row in rows[1:31]:
                if max(title_col, price_col) >= len(row): continue
                match = re.fullmatch(r"[¥￥]?\s*([0-9]{1,6}(?:\.[0-9]{1,2})?)\s*元?(?:/人)?", row[price_col])
                if not row[title_col] or not match: continue
                found.append(TicketOption(title=row[title_col][:80], price=match.group(1), purchase_url=source_url,
                    source_url=source_url, checked_at=datetime.now(timezone.utc).isoformat()).model_dump())
    return found[:30]


def discover_tickets(url):
    try:
        html, final_url = fetch_page(url)
        tickets = extract_tickets(html, final_url)
        return {"tickets": tickets, "status": "parsed" if tickets else "link_only",
                "message": "已提取票务，请核对票种、来源和价格后保存" if tickets else "未发现公开票种信息，将保留官方购票入口"}
    except (ValueError, OSError, http.client.HTTPException):
        return {"tickets": [], "status": "link_only", "message": "网页暂不能解析，将保留官方购票入口"}
