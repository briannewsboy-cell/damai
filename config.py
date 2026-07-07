from dataclasses import dataclass
import os


@dataclass(frozen=True)
class Config:
    concert_keyword: str
    smtp_host: str
    smtp_port: int
    smtp_user: str
    smtp_password: str
    email_to: str
    wechat_token: str
    wechat_provider: str  # "serverchan" or "pushplus"


def load_config() -> Config:
    return Config(
        concert_keyword=os.environ.get("CONCERT_KEYWORD", "刘宪华 苏州 演唱会"),
        smtp_host=os.environ["SMTP_HOST"],
        smtp_port=int(os.environ["SMTP_PORT"]),
        smtp_user=os.environ["SMTP_USER"],
        smtp_password=os.environ["SMTP_PASSWORD"],
        email_to=os.environ["EMAIL_TO"],
        wechat_token=os.environ["WECHAT_TOKEN"],
        wechat_provider=os.environ.get("WECHAT_PROVIDER", "serverchan"),
    )
