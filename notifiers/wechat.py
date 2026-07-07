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

# API-level success codes. ServerChan/PushPlus can return HTTP 200 with a
# nonzero JSON ``code``; raise_for_status() alone misses those.
SUCCESS_CODES = {
    "serverchan": 0,
    "pushplus": 200,
}


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

        provider = self.config.wechat_provider

        def do() -> requests.Response:
            resp = requests.post(endpoint, data=payload, timeout=10)
            resp.raise_for_status()
            # raise_for_status only catches HTTP errors. ServerChan/PushPlus
            # return HTTP 200 with a nonzero JSON ``code`` on API-level
            # failures (bad token, rate limit, etc.). Parse the body and
            # raise so run_once can flag the failure and retry next run.
            try:
                data = resp.json()
            except ValueError as e:
                raise RuntimeError(
                    f"WeChat {provider} returned non-JSON response: "
                    f"{resp.text[:200]!r}"
                ) from e
            expected = SUCCESS_CODES[provider]
            code = data.get("code")
            if code != expected:
                msg = data.get("message") or data.get("msg") or data
                raise RuntimeError(
                    f"WeChat {provider} API error: code={code}, message={msg}"
                )
            return resp

        with_retry(
            do,
            retries=RETRIES,
            backoff_base=BACKOFF_BASE,
            exceptions=RETRY_EXCEPTIONS,
            label=f"WeChat {self.config.wechat_provider} notify",
        )
