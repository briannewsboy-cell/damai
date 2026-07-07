import requests

from config import Config
from retry import with_retry

# Retry config for the WeChat API call (spec: 3 retries, exp backoff).
RETRIES = 3
BACKOFF_BASE = 1.0
RETRY_EXCEPTIONS = (
    requests.exceptions.ConnectionError,
    requests.exceptions.Timeout,
    requests.exceptions.HTTPError,
)


class WeChatNotifier:
    def __init__(self, config: Config):
        self.config = config

    def send(self, title: str, url: str, status: str) -> None:
        text = f"[开票提醒] {title}"
        desp = f"状态：{'已开售' if status == 'on_sale' else status}\n\n链接：{url}"

        if self.config.wechat_provider == "serverchan":
            endpoint = f"https://sctapi.ftqq.com/{self.config.wechat_token}.send"
            payload = {"title": text, "desp": desp}
        elif self.config.wechat_provider == "pushplus":
            endpoint = "https://www.pushplus.plus/send"
            payload = {
                "token": self.config.wechat_token,
                "title": text,
                "content": desp,
            }
        else:
            raise ValueError(f"Unsupported wechat_provider: {self.config.wechat_provider}")

        def do() -> requests.Response:
            resp = requests.post(endpoint, data=payload, timeout=10)
            resp.raise_for_status()
            return resp

        with_retry(
            do,
            retries=RETRIES,
            backoff_base=BACKOFF_BASE,
            exceptions=RETRY_EXCEPTIONS,
            label=f"WeChat {self.config.wechat_provider} notify",
        )
