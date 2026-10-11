"""Editorial travel preparation. Links are reviewed, never scraped or priced."""
from datetime import date
from ipaddress import ip_address
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def public_https(value: str) -> str:
    value = value.strip()
    if not value:
        return value
    try:
        u = urlsplit(value)
        host = (u.hostname or "").lower()
        if u.scheme != "https" or not host or u.username or u.password or u.port not in (None, 443):
            raise ValueError()
        if "." not in host or host.endswith((".local", ".localhost", ".internal")):
            raise ValueError()
        try:
            address = ip_address(host)
        except ValueError:
            address = None
        if address is not None or any(c.isspace() for c in value) or "\\" in value:
            raise ValueError()
    except ValueError as exc:
        raise ValueError("请填写有效的公开 HTTPS 网页地址（不支持 IP、账号密码或自定义协议）") from exc
    return value


class PreparationItem(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    title: str = Field(min_length=1, max_length=40)
    body: str = Field(default="", max_length=4000)
    url: str = Field(default="", max_length=2000)

    _url = field_validator("url")(public_https)

    @model_validator(mode="after")
    def nonempty(self):
        if not self.body and not self.url:
            raise ValueError("准备事项至少需要正文或链接")
        return self


class TravelPreparationInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    enabled: bool = False
    admission: Literal["unknown", "free", "reservation", "ticket"] = "unknown"
    channel_name: str = Field(default="", max_length=80)
    purchase_url: str = Field(default="", max_length=2000)
    launch_mode: Literal["in_app", "external"] = "in_app"
    source_url: str = Field(default="", max_length=2000)
    verified_on: date | None = None
    opening_hours: str = Field(default="", max_length=4000)
    opening_url: str = Field(default="", max_length=2000)
    transport: str = Field(default="", max_length=4000)
    transport_url: str = Field(default="", max_length=2000)
    notices: str = Field(default="", max_length=4000)
    notices_url: str = Field(default="", max_length=2000)
    extra_items: list[PreparationItem] = Field(default_factory=list, max_length=8)

    _urls = field_validator("purchase_url", "source_url", "opening_url", "transport_url", "notices_url")(public_https)

    @model_validator(mode="after")
    def reviewed_channel(self):
        if self.verified_on and self.verified_on > date.today():
            raise ValueError("核实日期不能晚于今天")
        if self.enabled and self.purchase_url:
            if self.admission not in ("ticket", "reservation"):
                raise ValueError("购票或预约入口须选择相应入园方式")
            if not self.channel_name or not self.source_url or not self.verified_on:
                raise ValueError("启用官方入口前，请填写渠道名称、来源网页和核实日期")
        return self
