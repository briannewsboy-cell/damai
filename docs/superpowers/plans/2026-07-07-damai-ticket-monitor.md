# Damai Ticket Monitor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python-based GitHub Actions monitor that checks Damai.cn for Liu Xianhua's Suzhou concert ticket availability and sends email + WeChat notifications when sales open.

**Architecture:** A GitHub Actions cron job runs a Python controller every 5 minutes. The controller checks the current time window and date, selects the appropriate polling mode, delegates status checking to a pluggable Damai checker (HTTP first, Playwright fallback), compares results against persisted state, and triggers independent email and WeChat notifiers only on state transitions.

**Tech Stack:** Python 3.11+, pytest, requests, python-dateutil, pytz. Optional: playwright (fallback checker).

## Global Constraints

- Deployment: GitHub Actions on a **public repository** (free minutes).
- Runtime window: 9:00–20:00 Asia/Shanghai only.
- Polling frequency: every 5 minutes before July 20; every 1 minute from July 20 through July 31.
- Scope: monitoring + notification only; no auto-purchase.
- Notifications: email via SMTP + WeChat via ServerChan or PushPlus.
- State persistence: `state.json` committed back to the repo by the workflow.
- Sensitive config: injected via GitHub Secrets as environment variables.
- Status values: `not_on_sale` and `on_sale`.
- Sale indicators: button text such as "立即购买", "购票", "选座购买".

---

## File Structure

```
/
├── .github/workflows/monitor.yml
├── checkers/
│   ├── __init__.py
│   ├── base.py          # DamaiChecker abstract protocol
│   └── http.py          # HttpDamaiChecker
├── notifiers/
│   ├── __init__.py
│   ├── email.py         # SmtpEmailNotifier
│   └── wechat.py        # WeChatNotifier (ServerChan/PushPlus)
├── tests/
│   ├── __init__.py
│   ├── test_config.py
│   ├── test_state.py
│   ├── test_email.py
│   ├── test_wechat.py
│   ├── test_checker.py
│   ├── fixtures/
│   │   ├── search_result.html
│   │   └── detail_on_sale.html
│   │   └── detail_not_sale.html
│   └── test_main.py
├── config.py            # Environment-based configuration
├── state.py             # state.json read/write + transition logic
├── main.py              # Controller and entry point
├── state.json           # Runtime state file
├── pyproject.toml       # Project metadata + pytest config
├── requirements.txt     # Runtime dependencies
├── requirements-dev.txt # Dev dependencies
└── README.md            # Setup and deployment guide
```

---

### Task 1: Configuration Module

**Files:**
- Create: `config.py`
- Create: `tests/test_config.py`
- Create: `pyproject.toml`
- Create: `requirements.txt`
- Create: `requirements-dev.txt`

**Interfaces:**
- Produces: `Config` dataclass with fields matching GitHub Secrets; `load_config()` returns a populated instance.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_config.py
import os
import pytest
from config import load_config


def test_load_config_with_required_values(monkeypatch):
    monkeypatch.setenv("CONCERT_KEYWORD", "刘宪华 苏州 演唱会")
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_USER", "sender@example.com")
    monkeypatch.setenv("SMTP_PASSWORD", "secret")
    monkeypatch.setenv("EMAIL_TO", "receiver@example.com")
    monkeypatch.setenv("WECHAT_TOKEN", "wx_token")
    monkeypatch.setenv("WECHAT_PROVIDER", "serverchan")

    config = load_config()
    assert config.concert_keyword == "刘宪华 苏州 演唱会"
    assert config.smtp_host == "smtp.example.com"
    assert config.smtp_port == 587
    assert config.email_to == "receiver@example.com"
    assert config.wechat_provider == "serverchan"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_config.py -v`

Expected: FAIL with "ModuleNotFoundError: No module named 'config'" or similar.

- [ ] **Step 3: Write minimal implementation**

```python
# config.py
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
```

```toml
# pyproject.toml
[project]
name = "damai-ticket-monitor"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "requests>=2.31.0",
    "python-dateutil>=2.8.0",
    "pytz>=2023.3",
]

[project.optional-dependencies]
playwright = ["playwright>=1.40.0"]
dev = ["pytest>=7.4.0", "pytest-mock>=3.12.0", "responses>=0.24.0"]
```

```txt
# requirements.txt
requests>=2.31.0
python-dateutil>=2.8.0
pytz>=2023.3
```

```txt
# requirements-dev.txt
-r requirements.txt
pytest>=7.4.0
pytest-mock>=3.12.0
responses>=0.24.0
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_config.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add config.py tests/test_config.py pyproject.toml requirements.txt requirements-dev.txt
git commit -m "feat: add configuration module and project scaffolding

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 2: State Management

**Files:**
- Create: `state.py`
- Create: `tests/test_state.py`
- Modify: `state.json` (create initial empty file if absent)

**Interfaces:**
- Consumes: `Config` (for `state_file` path, default `state.json`).
- Produces: `State` dataclass; `load_state(path)`, `save_state(path, state)`, `should_notify(old, new)`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_state.py
import json
import pytest
from state import State, load_state, save_state, should_notify


def test_load_state_returns_default_when_file_missing(tmp_path):
    missing = tmp_path / "missing.json"
    state = load_state(str(missing))
    assert state.last_status == "not_on_sale"
    assert state.notified is False


def test_save_and_load_state_roundtrip(tmp_path):
    path = tmp_path / "state.json"
    original = State(
        last_status="on_sale",
        last_title="刘宪华演唱会-苏州站",
        last_url="https://detail.damai.cn/item.htm?id=123",
        last_checked_at="2026-07-07T10:00:00+08:00",
        notified=True,
    )
    save_state(str(path), original)
    loaded = load_state(str(path))
    assert loaded == original


def test_should_notify_on_transition_to_on_sale():
    old = State(last_status="not_on_sale", notified=False)
    new = State(last_status="on_sale", notified=False)
    assert should_notify(old, new) is True


def test_should_not_notify_when_already_notified():
    old = State(last_status="on_sale", notified=True)
    new = State(last_status="on_sale", notified=True)
    assert should_notify(old, new) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_state.py -v`

Expected: FAIL with import or attribute errors.

- [ ] **Step 3: Write minimal implementation**

```python
# state.py
from dataclasses import asdict, dataclass
import json
import os
from typing import Optional


@dataclass
class State:
    last_status: str = "not_on_sale"  # "not_on_sale" | "on_sale"
    last_title: Optional[str] = None
    last_url: Optional[str] = None
    last_checked_at: Optional[str] = None
    notified: bool = False


def load_state(path: str = "state.json") -> State:
    if not os.path.exists(path):
        return State()
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return State(**data)


def save_state(path: str, state: State) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(asdict(state), f, ensure_ascii=False, indent=2)


def should_notify(old: State, new: State) -> bool:
    return new.last_status == "on_sale" and (
        old.last_status != "on_sale" or not old.notified
    )
```

```json
{
  "last_status": "not_on_sale",
  "last_title": null,
  "last_url": null,
  "last_checked_at": null,
  "notified": false
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_state.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add state.py tests/test_state.py state.json
git commit -m "feat: add state management

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 3: Email Notifier

**Files:**
- Create: `notifiers/__init__.py`
- Create: `notifiers/email.py`
- Create: `tests/test_email.py`

**Interfaces:**
- Consumes: `Config`.
- Produces: `EmailNotifier.send(title, url, status) -> None`, raising on failure.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_email.py
from unittest.mock import Mock, patch
import pytest
from config import Config
from notifiers.email import EmailNotifier


@pytest.fixture
def config():
    return Config(
        concert_keyword="刘宪华 苏州 演唱会",
        smtp_host="smtp.example.com",
        smtp_port=587,
        smtp_user="sender@example.com",
        smtp_password="secret",
        email_to="receiver@example.com",
        wechat_token="wx_token",
        wechat_provider="serverchan",
    )


def test_send_email(config):
    notifier = EmailNotifier(config)
    with patch("notifiers.email.smtplib.SMTP") as mock_smtp:
        instance = Mock()
        mock_smtp.return_value.__enter__ = Mock(return_value=instance)
        mock_smtp.return_value.__exit__ = Mock(return_value=False)

        notifier.send(
            title="刘宪华演唱会-苏州站",
            url="https://detail.damai.cn/item.htm?id=123",
            status="on_sale",
        )

        instance.starttls.assert_called_once()
        instance.login.assert_called_once_with("sender@example.com", "secret")
        call_args = instance.send_message.call_args[0][0]
        assert call_args["To"] == "receiver@example.com"
        assert call_args["From"] == "sender@example.com"
        assert "刘宪华演唱会-苏州站" in call_args.get_payload()[0].get_payload()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_email.py -v`

Expected: FAIL with import or attribute errors.

- [ ] **Step 3: Write minimal implementation**

```python
# notifiers/__init__.py
```

```python
# notifiers/email.py
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import smtplib
from config import Config


class EmailNotifier:
    def __init__(self, config: Config):
        self.config = config

    def send(self, title: str, url: str, status: str) -> None:
        subject = f"[开票提醒] {title} 已开售"
        body = (
            f"演出：{title}\n"
            f"状态：{'已开售' if status == 'on_sale' else status}\n"
            f"链接：{url}\n"
        )

        msg = MIMEMultipart()
        msg["From"] = self.config.smtp_user
        msg["To"] = self.config.email_to
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain", "utf-8"))

        with smtplib.SMTP(self.config.smtp_host, self.config.smtp_port) as server:
            server.starttls()
            server.login(self.config.smtp_user, self.config.smtp_password)
            server.send_message(msg)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_email.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add notifiers/__init__.py notifiers/email.py tests/test_email.py
git commit -m "feat: add email notifier

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 4: WeChat Notifier

**Files:**
- Create: `notifiers/wechat.py`
- Create: `tests/test_wechat.py`

**Interfaces:**
- Consumes: `Config`.
- Produces: `WeChatNotifier.send(title, url, status) -> None`, raising on failure.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_wechat.py
import responses
import pytest
from config import Config
from notifiers.wechat import WeChatNotifier


@pytest.fixture
def config_serverchan():
    return Config(
        concert_keyword="刘宪华 苏州 演唱会",
        smtp_host="smtp.example.com",
        smtp_port=587,
        smtp_user="sender@example.com",
        smtp_password="secret",
        email_to="receiver@example.com",
        wechat_token="sckey123",
        wechat_provider="serverchan",
    )


@responses.activate
def test_send_serverchan(config_serverchan):
    responses.add(
        responses.POST,
        "https://sctapi.ftqq.com/sckey123.send",
        json={"code": 0, "message": "success"},
        status=200,
    )

    notifier = WeChatNotifier(config_serverchan)
    notifier.send(
        title="刘宪华演唱会-苏州站",
        url="https://detail.damai.cn/item.htm?id=123",
        status="on_sale",
    )

    assert len(responses.calls) == 1
    body = responses.calls[0].request.body
    assert "刘宪华演唱会-苏州站" in body
    assert "detail.damai.cn" in body
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_wechat.py -v`

Expected: FAIL with import or attribute errors.

- [ ] **Step 3: Write minimal implementation**

```python
# notifiers/wechat.py
import urllib.parse
import requests
from config import Config


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

        response = requests.post(endpoint, data=payload, timeout=10)
        response.raise_for_status()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_wechat.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add notifiers/wechat.py tests/test_wechat.py
git commit -m "feat: add wechat notifier

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 5: Damai Checker Base + HTTP Implementation

**Files:**
- Create: `checkers/__init__.py`
- Create: `checkers/base.py`
- Create: `checkers/http.py`
- Create: `tests/test_checker.py`
- Create: `tests/fixtures/search_result.html`
- Create: `tests/fixtures/detail_on_sale.html`
- Create: `tests/fixtures/detail_not_sale.html`

**Interfaces:**
- Consumes: `Config` (for keyword).
- Produces: `ConcertResult` dataclass; `HttpDamaiChecker.check()` returns it.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_checker.py
import responses
import pytest
from config import Config
from checkers.http import HttpDamaiChecker


@pytest.fixture
def config():
    return Config(
        concert_keyword="刘宪华 苏州 演唱会",
        smtp_host="smtp.example.com",
        smtp_port=587,
        smtp_user="sender@example.com",
        smtp_password="secret",
        email_to="receiver@example.com",
        wechat_token="wx_token",
        wechat_provider="serverchan",
    )


@responses.activate
def test_http_checker_finds_on_sale(config):
    with open("tests/fixtures/detail_on_sale.html", "r", encoding="utf-8") as f:
        detail_html = f.read()

    responses.add(
        responses.GET,
        "https://search.damai.cn/searchajax.html",
        json={
            "data": {
                "list": [
                    {
                        "url": "/item.htm?id=123",
                        "name": "刘宪华演唱会-苏州站",
                        "cityname": "苏州",
                    }
                ]
            }
        },
        status=200,
    )
    responses.add(
        responses.GET,
        "https://detail.damai.cn/item.htm?id=123",
        body=detail_html,
        status=200,
    )

    checker = HttpDamaiChecker(config)
    result = checker.check()

    assert result.on_sale is True
    assert result.title == "刘宪华演唱会-苏州站"
    assert "detail.damai.cn" in result.url
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_checker.py -v`

Expected: FAIL with import or attribute errors.

- [ ] **Step 3: Write minimal implementation**

```python
# checkers/base.py
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol


@dataclass
class ConcertResult:
    title: str
    url: str
    status: str  # "not_on_sale" | "on_sale"
    on_sale: bool
    checked_at: str


class DamaiChecker(Protocol):
    def check(self) -> ConcertResult:
        ...
```

```python
# checkers/__init__.py
from checkers.base import ConcertResult, DamaiChecker
from checkers.http import HttpDamaiChecker

__all__ = ["ConcertResult", "DamaiChecker", "HttpDamaiChecker"]
```

```python
# checkers/http.py
from datetime import datetime, timezone
import re
import requests
from urllib.parse import urljoin
from config import Config
from checkers.base import ConcertResult, DamaiChecker


class HttpDamaiChecker:
    def __init__(self, config: Config):
        self.config = config
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                "Accept-Language": "zh-CN,zh;q=0.9",
            }
        )

    def check(self) -> ConcertResult:
        search_url = "https://search.damai.cn/searchajax.html"
        params = {
            "keyword": self.config.concert_keyword,
            "cty": "苏州",
        }
        response = self.session.get(search_url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        items = data.get("data", {}).get("list", [])
        if not items:
            raise RuntimeError("No search results found")

        item = self._pick_best_item(items)
        detail_url = urljoin("https://detail.damai.cn/", item.get("url", ""))
        title = item.get("name", "")

        detail_response = self.session.get(detail_url, timeout=10)
        detail_response.raise_for_status()
        on_sale = self._parse_sale_status(detail_response.text)

        return ConcertResult(
            title=title,
            url=detail_url,
            status="on_sale" if on_sale else "not_on_sale",
            on_sale=on_sale,
            checked_at=datetime.now(timezone.utc).isoformat(),
        )

    def _pick_best_item(self, items: list[dict]) -> dict:
        keyword = self.config.concert_keyword.replace(" ", "")
        best = items[0]
        best_score = 0
        for item in items:
            name = item.get("name", "")
            city = item.get("cityname", "")
            score = sum(1 for term in keyword if term in name)
            if "苏州" in city:
                score += 10
            if score > best_score:
                best_score = score
                best = item
        return best

    def _parse_sale_status(self, html: str) -> bool:
        sale_phrases = ["立即购买", "购票", "选座购买", "马上预订"]
        return any(phrase in html for phrase in sale_phrases)
```

Sample fixture content (trim to minimal):

```html
<!-- tests/fixtures/search_result.html (not used directly, mocked via JSON) -->
```

```html
<!-- tests/fixtures/detail_on_sale.html -->
<!DOCTYPE html>
<html>
<body>
  <button class="buy__button">立即购买</button>
</body>
</html>
```

```html
<!-- tests/fixtures/detail_not_sale.html -->
<!DOCTYPE html>
<html>
<body>
  <button class="buy__button">即将开售</button>
</body>
</html>
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_checker.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add checkers/ tests/test_checker.py tests/fixtures/
git commit -m "feat: add HTTP damai checker

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 6: Main Controller

**Files:**
- Create: `main.py`
- Create: `tests/test_main.py`

**Interfaces:**
- Consumes: `Config`, `State`, `EmailNotifier`, `WeChatNotifier`, `HttpDamaiChecker`.
- Produces: `run_once(config)` and `run_polling(config, duration_seconds, interval_seconds)`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_main.py
from datetime import datetime, timezone
from unittest.mock import Mock, patch
import pytest
from config import Config
from main import run_once
from state import State
from checkers.base import ConcertResult


@pytest.fixture
def config():
    return Config(
        concert_keyword="刘宪华 苏州 演唱会",
        smtp_host="smtp.example.com",
        smtp_port=587,
        smtp_user="sender@example.com",
        smtp_password="secret",
        email_to="receiver@example.com",
        wechat_token="wx_token",
        wechat_provider="serverchan",
    )


def test_run_once_sends_notification_on_sale(config):
    old_state = State(last_status="not_on_sale", notified=False)
    result = ConcertResult(
        title="刘宪华演唱会-苏州站",
        url="https://detail.damai.cn/item.htm?id=123",
        status="on_sale",
        on_sale=True,
        checked_at=datetime.now(timezone.utc).isoformat(),
    )

    with patch("main.load_state", return_value=old_state), \
         patch("main.save_state") as mock_save, \
         patch("main.HttpDamaiChecker") as mock_checker_cls, \
         patch("main.EmailNotifier") as mock_email_cls, \
         patch("main.WeChatNotifier") as mock_wechat_cls:

        mock_checker_cls.return_value.check.return_value = result
        mock_email = Mock()
        mock_wechat = Mock()
        mock_email_cls.return_value = mock_email
        mock_wechat_cls.return_value = mock_wechat

        run_once(config)

        mock_email.send.assert_called_once()
        mock_wechat.send.assert_called_once()
        mock_save.assert_called_once()
        saved_state = mock_save.call_args[0][1]
        assert saved_state.last_status == "on_sale"
        assert saved_state.notified is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_main.py -v`

Expected: FAIL with import or attribute errors.

- [ ] **Step 3: Write minimal implementation**

```python
# main.py
import logging
import os
import time
from datetime import datetime, timezone
from typing import Optional

import pytz

from checkers.http import HttpDamaiChecker
from config import Config, load_config
from notifiers.email import EmailNotifier
from notifiers.wechat import WeChatNotifier
from state import State, load_state, save_state, should_notify

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

TZ = pytz.timezone("Asia/Shanghai")
RUN_WINDOW_START = 9
RUN_WINDOW_END = 20
POLL_SWITCH_DATE = "2026-07-20"


def is_within_run_window(now: Optional[datetime] = None) -> bool:
    if now is None:
        now = datetime.now(TZ)
    return RUN_WINDOW_START <= now.hour < RUN_WINDOW_END


def should_use_polling_mode(now: Optional[datetime] = None) -> bool:
    if now is None:
        now = datetime.now(TZ)
    return now.strftime("%Y-%m-%d") >= POLL_SWITCH_DATE


def run_once(config: Config, state_path: str = "state.json") -> None:
    old_state = load_state(state_path)
    checker = HttpDamaiChecker(config)
    result = checker.check()

    new_state = State(
        last_status=result.status,
        last_title=result.title,
        last_url=result.url,
        last_checked_at=result.checked_at,
        notified=False,
    )

    if should_notify(old_state, new_state):
        logger.info("Status changed to on_sale, sending notifications")
        EmailNotifier(config).send(result.title, result.url, result.status)
        WeChatNotifier(config).send(result.title, result.url, result.status)
        new_state.notified = True
    else:
        logger.info("No notification needed (status=%s)", result.status)

    save_state(state_path, new_state)


def run_polling(
    config: Config,
    duration_seconds: int = 300,
    interval_seconds: int = 60,
    state_path: str = "state.json",
) -> None:
    deadline = time.time() + duration_seconds
    while time.time() < deadline:
        try:
            run_once(config, state_path)
        except Exception as e:
            logger.exception("Polling check failed: %s", e)
        remaining = deadline - time.time()
        if remaining > 0:
            sleep_for = min(interval_seconds, remaining)
            time.sleep(sleep_for)


def main() -> None:
    config = load_config()
    now = datetime.now(TZ)

    if not is_within_run_window(now):
        logger.info("Outside run window 9:00-20:00 CST, exiting")
        return

    if should_use_polling_mode(now):
        logger.info("Entering polling mode (1-minute checks for 5 minutes)")
        run_polling(config, duration_seconds=300, interval_seconds=60)
    else:
        logger.info("Running single check")
        run_once(config)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_main.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add main.py tests/test_main.py
git commit -m "feat: add main controller with run window and polling logic

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 7: GitHub Actions Workflow

**Files:**
- Create: `.github/workflows/monitor.yml`
- Modify: `README.md`

**Interfaces:**
- Produces: workflow that runs every 5 minutes, installs deps, runs `main.py`, commits `state.json`.

- [ ] **Step 1: Write the failing test**

Manual verification: push to GitHub and inspect the Actions tab. There is no automated test for GitHub Actions YAML.

- [ ] **Step 2: Write the workflow**

```yaml
# .github/workflows/monitor.yml
name: Damai Ticket Monitor

on:
  schedule:
    - cron: "*/5 * * * *"
  workflow_dispatch:

permissions:
  contents: write

jobs:
  monitor:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt

      - name: Run monitor
        env:
          CONCERT_KEYWORD: ${{ secrets.CONCERT_KEYWORD }}
          SMTP_HOST: ${{ secrets.SMTP_HOST }}
          SMTP_PORT: ${{ secrets.SMTP_PORT }}
          SMTP_USER: ${{ secrets.SMTP_USER }}
          SMTP_PASSWORD: ${{ secrets.SMTP_PASSWORD }}
          EMAIL_TO: ${{ secrets.EMAIL_TO }}
          WECHAT_TOKEN: ${{ secrets.WECHAT_TOKEN }}
          WECHAT_PROVIDER: ${{ secrets.WECHAT_PROVIDER }}
        run: python main.py

      - name: Commit state changes
        run: |
          git config --local user.email "action@github.com"
          git config --local user.name "GitHub Action"
          git add state.json
          git diff --staged --quiet || git commit -m "chore: update state.json [skip ci]"
          git push
```

- [ ] **Step 3: Add minimal README setup**

```markdown
# Damai Ticket Monitor

监控大麦网演唱会开票状态，开票时发送邮件 + 微信通知。

## 配置

在 GitHub 仓库 Settings → Secrets and variables → Actions 中设置以下 Secrets：

| Secret | 说明 |
| --- | --- |
| CONCERT_KEYWORD | 搜索关键词，默认：刘宪华 苏州 演唱会 |
| SMTP_HOST | SMTP 服务器 |
| SMTP_PORT | SMTP 端口 |
| SMTP_USER | 发件邮箱 |
| SMTP_PASSWORD | 邮箱授权码 |
| EMAIL_TO | 收件邮箱 |
| WECHAT_TOKEN | Server 酱 SCKEY 或 PushPlus token |
| WECHAT_PROVIDER | serverchan 或 pushplus |

## 本地测试

```bash
pip install -r requirements-dev.txt
pytest
```
```

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/monitor.yml README.md
git commit -m "feat: add GitHub Actions workflow and README

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 8: Integration Verification

**Files:**
- Modify: `tests/test_main.py`
- Modify: `README.md`

**Interfaces:**
- Verifies end-to-end flow with mocked checker and notifiers.

- [ ] **Step 1: Add integration test**

```python
# tests/test_main.py

def test_run_once_does_not_notify_when_already_notified(config):
    old_state = State(last_status="on_sale", notified=True)
    result = ConcertResult(
        title="刘宪华演唱会-苏州站",
        url="https://detail.damai.cn/item.htm?id=123",
        status="on_sale",
        on_sale=True,
        checked_at=datetime.now(timezone.utc).isoformat(),
    )

    with patch("main.load_state", return_value=old_state), \
         patch("main.save_state") as mock_save, \
         patch("main.HttpDamaiChecker") as mock_checker_cls, \
         patch("main.EmailNotifier") as mock_email_cls, \
         patch("main.WeChatNotifier") as mock_wechat_cls:

        mock_checker_cls.return_value.check.return_value = result
        mock_email = Mock()
        mock_wechat = Mock()
        mock_email_cls.return_value = mock_email
        mock_wechat_cls.return_value = mock_wechat

        run_once(config)

        mock_email.send.assert_not_called()
        mock_wechat.send.assert_not_called()
```

- [ ] **Step 2: Run full test suite**

Run: `pytest -v`

Expected: All tests PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/test_main.py README.md
git commit -m "test: add integration verification for duplicate suppression

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Self-Review

**Spec coverage:**
- 9:00–20:00 window: Task 6 `is_within_run_window`.
- Date-based polling: Task 6 `should_use_polling_mode` + `run_polling`.
- HTTP checker + Playwright fallback hook: Task 5 `HttpDamaiChecker`; fallback is a future swap of the checker class in `main.py`.
- Email + WeChat notifications: Tasks 3 and 4.
- State persistence: Task 2.
- GitHub Actions cron + state commit: Task 7.
- No auto-purchase: confirmed; checker only reads status.

**Placeholder scan:** No TBD/TODO placeholders. All code and commands are explicit.

**Type consistency:** `Config`, `State`, and `ConcertResult` fields match across tasks.

**Remaining gap:** Playwright fallback implementation is intentionally deferred; the plan wires in `HttpDamaiChecker` first and documents the fallback as a later swap once HTTP is proven insufficient.
