import logging
import time
from datetime import datetime
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
    elif new_state.last_status == "on_sale" and old_state.notified:
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
