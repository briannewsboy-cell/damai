import logging
import time
from datetime import datetime
from typing import Optional

import pytz

from checkers.base import ConcertResult
from checkers.http import HttpDamaiChecker
from checkers.playwright import PlaywrightDamaiChecker
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
POLL_END_DATE = "2026-07-31"

# Status passed to notifiers when the checker itself is broken and a
# one-time fallback alert is sent. Notifiers render the raw status string.
CHECKER_FAILED_STATUS = "checker_failed"
CHECKER_FAILED_MESSAGE = "检查器失效，请人工查看"


def is_within_run_window(now: Optional[datetime] = None) -> bool:
    if now is None:
        now = datetime.now(TZ)
    return RUN_WINDOW_START <= now.hour < RUN_WINDOW_END


def seconds_until_window_end(now: Optional[datetime] = None) -> int:
    """Seconds remaining until the 20:00 CST window boundary.

    Returns 0 if ``now`` is at or past 20:00 CST. Used to cap polling
    duration so a delayed trigger near 19:55 cannot run checks past 20:00.
    """
    if now is None:
        now = datetime.now(TZ)
    end = now.replace(hour=RUN_WINDOW_END, minute=0, second=0, microsecond=0)
    remaining = (end - now).total_seconds()
    return max(0, int(remaining))


def should_use_polling_mode(now: Optional[datetime] = None) -> bool:
    if now is None:
        now = datetime.now(TZ)
    today = now.strftime("%Y-%m-%d")
    return POLL_SWITCH_DATE <= today <= POLL_END_DATE


def _send_checker_failure_alert(config: Config) -> None:
    """Send the one-time checker-failure fallback alert.

    Each notifier is attempted independently so an SMTP outage doesn't block
    WeChat (and vice versa). Failures are logged, never raised.
    """
    for name, notifier in (
        ("email", EmailNotifier(config)),
        ("wechat", WeChatNotifier(config)),
    ):
        try:
            notifier.send(CHECKER_FAILED_MESSAGE, "", CHECKER_FAILED_STATUS)
        except Exception as e:  # noqa: BLE001 - best-effort alert
            logger.exception("%s notifier failed during checker-failure alert: %s", name, e)


def run_once(config: Config, state_path: str = "state.json") -> None:
    old_state = load_state(state_path)

    result = _try_checkers(config)
    if result is None:
        # Both checkers failed; the inner exception has already been logged.
        if not old_state.checker_failed_notified:
            logger.warning("Sending one-time checker-failure alert")
            _send_checker_failure_alert(config)
        new_state = State(
            last_status=old_state.last_status,
            last_title=old_state.last_title,
            last_url=old_state.last_url,
            last_checked_at=old_state.last_checked_at,
            notified=old_state.notified,
            checker_failed_notified=True,
        )
        save_state(state_path, new_state)
        return

    # Successful check clears any prior checker-failure flag.
    new_state = State(
        last_status=result.status,
        last_title=result.title,
        last_url=result.url,
        last_checked_at=result.checked_at,
        notified=False,
        checker_failed_notified=False,
    )

    if should_notify(old_state, new_state):
        logger.info("Status changed to on_sale, sending notifications")
        # Each notifier is attempted independently: an SMTP failure must not
        # prevent WeChat (and vice versa). State is always persisted below.
        any_succeeded = False
        for name, notifier in (
            ("email", EmailNotifier(config)),
            ("wechat", WeChatNotifier(config)),
        ):
            try:
                notifier.send(result.title, result.url, result.status)
                any_succeeded = True
            except Exception as e:  # noqa: BLE001 - log and continue
                logger.exception("%s notifier failed: %s", name, e)
        # Mark notified iff at least one channel succeeded; if both failed
        # leave notified=False so both retry on the next run.
        if any_succeeded:
            new_state.notified = True
    elif new_state.last_status == "on_sale" and old_state.notified:
        new_state.notified = True
    else:
        logger.info("No notification needed (status=%s)", result.status)

    save_state(state_path, new_state)


def _try_checkers(config: Config) -> ConcertResult | None:
    """Try the fast HTTP checker first, then fall back to Playwright.

    Checkers are instantiated lazily so the Playwright browser is only launched
    when the HTTP checker fails.

    Returns ``None`` when both checkers fail so ``run_once`` can persist state
    and send the one-time checker-failure alert.
    """
    for name, factory in (
        ("http", lambda: HttpDamaiChecker(config)),
        ("playwright", lambda: PlaywrightDamaiChecker(config)),
    ):
        try:
            logger.info("Trying %s checker", name)
            checker = factory()
            return checker.check()
        except Exception as e:  # noqa: BLE001 - checker is I/O-bound and unpredictable
            logger.exception("%s checker failed: %s", name, e)

    logger.error("All checkers failed")
    return None


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
        # Cap the duration to the remaining window time so a delayed trigger
        # (e.g. 19:55) cannot run checks past 20:00 CST.
        remaining = seconds_until_window_end(now)
        duration = min(300, remaining)
        logger.info(
            "Entering polling mode (1-minute checks for %d seconds)", duration
        )
        run_polling(config, duration_seconds=duration, interval_seconds=60)
    else:
        logger.info("Running single check")
        run_once(config)


if __name__ == "__main__":
    main()
