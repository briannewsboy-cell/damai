from datetime import datetime, timezone
from unittest.mock import Mock, patch

import pytest
import pytz

from checkers.base import ConcertResult
from config import Config
from main import (
    POLL_END_DATE,
    POLL_SWITCH_DATE,
    RUN_WINDOW_END,
    RUN_WINDOW_START,
    is_within_run_window,
    run_once,
    run_polling,
    seconds_until_window_end,
    should_use_polling_mode,
)
from state import State


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


def _make_result(status: str = "on_sale") -> ConcertResult:
    return ConcertResult(
        title="刘宪华演唱会-苏州站",
        url="https://detail.damai.cn/item.htm?id=123",
        status=status,
        on_sale=(status == "on_sale"),
        checked_at=datetime.now(timezone.utc).isoformat(),
    )


def test_run_once_sends_notification_on_sale(config):
    old_state = State(last_status="not_on_sale", notified=False)
    result = _make_result("on_sale")

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


def test_run_once_skips_notification_when_not_on_sale(config):
    """When the new status is not_on_sale, no notification fires and state is persisted."""
    old_state = State(last_status="not_on_sale", notified=False)
    result = _make_result("not_on_sale")

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
        mock_save.assert_called_once()
        saved_state = mock_save.call_args[0][1]
        assert saved_state.last_status == "not_on_sale"
        assert saved_state.notified is False


def test_run_once_passes_result_fields_to_notifiers(config):
    """Notifiers receive the title, url, and status from the checker result."""
    old_state = State(last_status="not_on_sale", notified=False)
    result = _make_result("on_sale")

    with patch("main.load_state", return_value=old_state), \
         patch("main.save_state"), \
         patch("main.HttpDamaiChecker") as mock_checker_cls, \
         patch("main.EmailNotifier") as mock_email_cls, \
         patch("main.WeChatNotifier") as mock_wechat_cls:

        mock_checker_cls.return_value.check.return_value = result
        mock_email = Mock()
        mock_wechat = Mock()
        mock_email_cls.return_value = mock_email
        mock_wechat_cls.return_value = mock_wechat

        run_once(config)

        mock_email.send.assert_called_once_with(
            result.title, result.url, result.status
        )
        mock_wechat.send.assert_called_once_with(
            result.title, result.url, result.status
        )


def test_run_once_uses_state_path_argument(config, tmp_path):
    """run_once forwards state_path to load_state and save_state."""
    state_path = str(tmp_path / "custom.json")
    old_state = State(last_status="not_on_sale", notified=False)
    result = _make_result("not_on_sale")

    with patch("main.load_state", return_value=old_state) as mock_load, \
         patch("main.save_state") as mock_save, \
         patch("main.HttpDamaiChecker") as mock_checker_cls, \
         patch("main.EmailNotifier"), \
         patch("main.WeChatNotifier"):

        mock_checker_cls.return_value.check.return_value = result
        run_once(config, state_path=state_path)

        mock_load.assert_called_once_with(state_path)
        mock_save.assert_called_once_with(state_path, mock_save.call_args[0][1])


def test_run_once_does_not_notify_when_already_notified(config):
    """Integration check: a repeated on_sale result must not re-notify.

    Verifies the end-to-end flow with mocked checker and notifiers: when the
    previous state already records on_sale + notified, run_once must skip both
    notifiers. See task-8 report for a related state-persistence concern.
    """
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
        # State is still persisted on the no-notify path.
        mock_save.assert_called_once()
        saved_state = mock_save.call_args[0][1]
        assert saved_state.notified is True


def test_is_within_run_window_inside_window():
    tz = pytz.timezone("Asia/Shanghai")
    # 12:00 CST is inside the 9:00-20:00 window
    now = tz.localize(datetime(2026, 7, 7, 12, 0))
    assert is_within_run_window(now) is True


def test_is_within_run_window_at_start_boundary():
    tz = pytz.timezone("Asia/Shanghai")
    # 9:00 inclusive start
    now = tz.localize(datetime(2026, 7, 7, 9, 0))
    assert is_within_run_window(now) is True


def test_is_within_run_window_at_end_boundary():
    tz = pytz.timezone("Asia/Shanghai")
    # 20:00 exclusive end
    now = tz.localize(datetime(2026, 7, 7, 20, 0))
    assert is_within_run_window(now) is False


def test_is_within_run_window_before_window():
    tz = pytz.timezone("Asia/Shanghai")
    now = tz.localize(datetime(2026, 7, 7, 8, 59))
    assert is_within_run_window(now) is False


def test_is_within_run_window_after_window():
    tz = pytz.timezone("Asia/Shanghai")
    now = tz.localize(datetime(2026, 7, 7, 23, 30))
    assert is_within_run_window(now) is False


def test_should_use_polling_mode_before_switch_date():
    tz = pytz.timezone("Asia/Shanghai")
    now = tz.localize(datetime(2026, 7, 19, 12, 0))
    assert should_use_polling_mode(now) is False


def test_should_use_polling_mode_on_switch_date():
    tz = pytz.timezone("Asia/Shanghai")
    now = tz.localize(datetime(2026, 7, 20, 0, 0))
    assert should_use_polling_mode(now) is True


def test_should_use_polling_mode_on_end_date():
    """July 31 is the last polling day (inclusive)."""
    tz = pytz.timezone("Asia/Shanghai")
    now = tz.localize(datetime(2026, 7, 31, 19, 59))
    assert should_use_polling_mode(now) is True


def test_should_use_polling_mode_after_end_date():
    """Polling must stop after July 31 (Critical fix: previously unbounded)."""
    tz = pytz.timezone("Asia/Shanghai")
    now = tz.localize(datetime(2026, 8, 1, 9, 0))
    assert should_use_polling_mode(now) is False


def test_run_window_constants_match_plan():
    assert RUN_WINDOW_START == 9
    assert RUN_WINDOW_END == 20
    assert POLL_SWITCH_DATE == "2026-07-20"
    assert POLL_END_DATE == "2026-07-31"


def test_run_polling_runs_until_deadline(config):
    """run_polling invokes run_once repeatedly while time remains, then stops."""
    result = _make_result("not_on_sale")
    # time.time() sequence:
    #   0.0   -> deadline = 0 + 10 = 10
    #   1.0   -> while-check: 1 < 10, enter iter 1 (run_once -> check)
    #   2.0   -> remaining = 10 - 2 = 8 > 0, sleep 5
    #   3.0   -> while-check: 3 < 10, enter iter 2 (run_once -> check)
    #   4.0   -> remaining = 10 - 4 = 6 > 0, sleep 5
    #   100.0 -> while-check: 100 < 10 False, exit
    time_values = [0.0, 1.0, 2.0, 3.0, 4.0, 100.0]
    with patch("main.load_state", return_value=State()), \
         patch("main.save_state"), \
         patch("main.HttpDamaiChecker") as mock_checker_cls, \
         patch("main.EmailNotifier"), \
         patch("main.WeChatNotifier"), \
         patch("main.time.sleep") as mock_sleep, \
         patch("main.time.time", side_effect=time_values):

        mock_checker_cls.return_value.check.return_value = result

        run_polling(config, duration_seconds=10, interval_seconds=5)

        assert mock_checker_cls.return_value.check.call_count == 2
        assert mock_sleep.call_count == 2


def test_run_polling_continues_after_exception(config):
    """A failing checker must not terminate the polling loop.

    run_once catches checker exceptions internally (and sends a one-time
    fallback alert), so run_polling's own try/except is a backstop.
    """
    # time.time() sequence:
    #   0.0   -> deadline = 0 + 10 = 10
    #   1.0   -> while-check: 1 < 10, enter iter 1 (checker raises, run_once handles)
    #   2.0   -> remaining = 10 - 2 = 8 > 0, sleep 5
    #   100.0 -> while-check: 100 < 10 False, exit
    time_values = [0.0, 1.0, 2.0, 100.0]
    with patch("main.load_state", return_value=State()), \
         patch("main.save_state"), \
         patch("main.HttpDamaiChecker") as mock_checker_cls, \
         patch("main.EmailNotifier"), \
         patch("main.WeChatNotifier"), \
         patch("main.time.sleep"), \
         patch("main.time.time", side_effect=time_values):

        mock_checker_cls.return_value.check.side_effect = RuntimeError("boom")

        # Should not raise even though run_once raises internally
        run_polling(config, duration_seconds=10, interval_seconds=5)

        assert mock_checker_cls.return_value.check.call_count == 1


def test_run_polling_forwards_state_path(config, tmp_path):
    """run_polling forwards state_path to run_once."""
    state_path = str(tmp_path / "poll.json")
    result = _make_result("not_on_sale")
    # time.time() sequence: deadline=10, enter (1<10), remaining (10-2=8, sleep), exit (100<10 False)
    time_values = [0.0, 1.0, 2.0, 100.0]
    with patch("main.load_state", return_value=State()) as mock_load, \
         patch("main.save_state"), \
         patch("main.HttpDamaiChecker") as mock_checker_cls, \
         patch("main.EmailNotifier"), \
         patch("main.WeChatNotifier"), \
         patch("main.time.sleep"), \
         patch("main.time.time", side_effect=time_values):

        mock_checker_cls.return_value.check.return_value = result
        run_polling(config, duration_seconds=10, interval_seconds=5, state_path=state_path)

        mock_load.assert_called_once_with(state_path)


def test_run_once_email_failure_does_not_block_wechat_or_save(config):
    """An SMTP failure must not prevent WeChat or skip state persistence.

    Critical fix: previously a single notifier raising aborted save_state,
    causing duplicate alerts on the next run.
    """
    old_state = State(last_status="not_on_sale", notified=False)
    result = _make_result("on_sale")

    with patch("main.load_state", return_value=old_state), \
         patch("main.save_state") as mock_save, \
         patch("main.HttpDamaiChecker") as mock_checker_cls, \
         patch("main.EmailNotifier") as mock_email_cls, \
         patch("main.WeChatNotifier") as mock_wechat_cls:

        mock_checker_cls.return_value.check.return_value = result
        mock_email = Mock()
        mock_wechat = Mock()
        mock_email.send.side_effect = RuntimeError("smtp down")
        mock_email_cls.return_value = mock_email
        mock_wechat_cls.return_value = mock_wechat

        run_once(config)

        # Both notifiers attempted independently.
        mock_email.send.assert_called_once()
        mock_wechat.send.assert_called_once()
        # State is still persisted.
        mock_save.assert_called_once()
        saved_state = mock_save.call_args[0][1]
        # WeChat succeeded, so notified is True (no duplicate next run).
        assert saved_state.notified is True
        assert saved_state.last_status == "on_sale"


def test_run_once_wechat_failure_does_not_block_email(config):
    """Symmetric to the email case: a WeChat failure must not block email."""
    old_state = State(last_status="not_on_sale", notified=False)
    result = _make_result("on_sale")

    with patch("main.load_state", return_value=old_state), \
         patch("main.save_state") as mock_save, \
         patch("main.HttpDamaiChecker") as mock_checker_cls, \
         patch("main.EmailNotifier") as mock_email_cls, \
         patch("main.WeChatNotifier") as mock_wechat_cls:

        mock_checker_cls.return_value.check.return_value = result
        mock_email = Mock()
        mock_wechat = Mock()
        mock_wechat.send.side_effect = RuntimeError("wechat down")
        mock_email_cls.return_value = mock_email
        mock_wechat_cls.return_value = mock_wechat

        run_once(config)

        mock_email.send.assert_called_once()
        mock_wechat.send.assert_called_once()
        mock_save.assert_called_once()
        saved_state = mock_save.call_args[0][1]
        # Email succeeded, so notified is True.
        assert saved_state.notified is True


def test_run_once_both_notifiers_fail_leaves_notified_false(config):
    """When both notifiers fail, notified stays False so both retry next run."""
    old_state = State(last_status="not_on_sale", notified=False)
    result = _make_result("on_sale")

    with patch("main.load_state", return_value=old_state), \
         patch("main.save_state") as mock_save, \
         patch("main.HttpDamaiChecker") as mock_checker_cls, \
         patch("main.EmailNotifier") as mock_email_cls, \
         patch("main.WeChatNotifier") as mock_wechat_cls:

        mock_checker_cls.return_value.check.return_value = result
        mock_email = Mock()
        mock_wechat = Mock()
        mock_email.send.side_effect = RuntimeError("smtp down")
        mock_wechat.send.side_effect = RuntimeError("wechat down")
        mock_email_cls.return_value = mock_email
        mock_wechat_cls.return_value = mock_wechat

        run_once(config)

        mock_email.send.assert_called_once()
        mock_wechat.send.assert_called_once()
        mock_save.assert_called_once()
        saved_state = mock_save.call_args[0][1]
        assert saved_state.notified is False


def test_run_once_checker_failure_sends_one_time_alert(config):
    """A persistent checker failure sends a one-time fallback alert."""
    old_state = State(last_status="not_on_sale", notified=False)

    with patch("main.load_state", return_value=old_state), \
         patch("main.save_state") as mock_save, \
         patch("main.HttpDamaiChecker") as mock_checker_cls, \
         patch("main.EmailNotifier") as mock_email_cls, \
         patch("main.WeChatNotifier") as mock_wechat_cls:

        mock_checker_cls.return_value.check.side_effect = RuntimeError("damai 500")
        mock_email = Mock()
        mock_wechat = Mock()
        mock_email_cls.return_value = mock_email
        mock_wechat_cls.return_value = mock_wechat

        run_once(config)

        # One-time fallback alert fires on both channels.
        mock_email.send.assert_called_once()
        mock_wechat.send.assert_called_once()
        # The alert message is the checker-failure text.
        email_args = mock_email.send.call_args[0]
        assert email_args[0] == "检查器失效，请人工查看"
        mock_save.assert_called_once()
        saved_state = mock_save.call_args[0][1]
        assert saved_state.checker_failed_notified is True


def test_run_once_checker_failure_does_not_renotify(config):
    """Once checker_failed_notified is set, subsequent failures don't re-alert."""
    old_state = State(
        last_status="not_on_sale", notified=False, checker_failed_notified=True
    )

    with patch("main.load_state", return_value=old_state), \
         patch("main.save_state") as mock_save, \
         patch("main.HttpDamaiChecker") as mock_checker_cls, \
         patch("main.EmailNotifier") as mock_email_cls, \
         patch("main.WeChatNotifier") as mock_wechat_cls:

        mock_checker_cls.return_value.check.side_effect = RuntimeError("damai 500")

        run_once(config)

        # No re-notification.
        mock_email_cls.return_value.send.assert_not_called()
        mock_wechat_cls.return_value.send.assert_not_called()
        mock_save.assert_called_once()
        saved_state = mock_save.call_args[0][1]
        assert saved_state.checker_failed_notified is True


def test_run_once_resets_checker_failed_flag_on_success(config):
    """A successful check clears the checker_failed_notified flag."""
    old_state = State(
        last_status="not_on_sale", notified=False, checker_failed_notified=True
    )
    result = _make_result("not_on_sale")

    with patch("main.load_state", return_value=old_state), \
         patch("main.save_state") as mock_save, \
         patch("main.HttpDamaiChecker") as mock_checker_cls, \
         patch("main.EmailNotifier"), \
         patch("main.WeChatNotifier"):

        mock_checker_cls.return_value.check.return_value = result
        run_once(config)

        mock_save.assert_called_once()
        saved_state = mock_save.call_args[0][1]
        assert saved_state.checker_failed_notified is False


# --- Polling window cap (Important fix #2) -------------------------------


def test_seconds_until_window_end_midday():
    """At 12:00 CST, 8 hours remain until 20:00."""
    tz = pytz.timezone("Asia/Shanghai")
    now = tz.localize(datetime(2026, 7, 25, 12, 0, 0))
    assert seconds_until_window_end(now) == 8 * 3600


def test_seconds_until_window_end_near_boundary():
    """At 19:55:00 CST, exactly 300 seconds remain."""
    tz = pytz.timezone("Asia/Shanghai")
    now = tz.localize(datetime(2026, 7, 25, 19, 55, 0))
    assert seconds_until_window_end(now) == 300


def test_seconds_until_window_end_just_inside():
    """At 19:59:30 CST, 30 seconds remain (sub-minute precision)."""
    tz = pytz.timezone("Asia/Shanghai")
    now = tz.localize(datetime(2026, 7, 25, 19, 59, 30))
    assert seconds_until_window_end(now) == 30


def test_seconds_until_window_end_at_boundary_is_zero():
    """At exactly 20:00:00 CST, 0 seconds remain (not negative)."""
    tz = pytz.timezone("Asia/Shanghai")
    now = tz.localize(datetime(2026, 7, 25, 20, 0, 0))
    assert seconds_until_window_end(now) == 0


def test_seconds_until_window_end_past_boundary_is_zero():
    """Past 20:00 CST, the remaining time is clamped to 0."""
    tz = pytz.timezone("Asia/Shanghai")
    now = tz.localize(datetime(2026, 7, 25, 23, 30, 0))
    assert seconds_until_window_end(now) == 0


def test_main_caps_polling_duration_near_window_end(config):
    """A delayed trigger near 19:55 caps duration to the remaining window time.

    Important fix #2: main() computes min(300, remaining_seconds) so a
    delayed 19:55 trigger cannot run checks past 20:00 CST. At 19:58, only
    120 seconds remain, so duration_seconds must be 120 (not 300).
    """
    tz = pytz.timezone("Asia/Shanghai")
    now = tz.localize(datetime(2026, 7, 25, 19, 58, 0))  # 120s remaining

    with patch("main.load_config", return_value=config), \
         patch("main.datetime") as mock_datetime, \
         patch("main.is_within_run_window", return_value=True), \
         patch("main.should_use_polling_mode", return_value=True), \
         patch("main.run_polling") as mock_run_polling:
        # main() uses `datetime.now(TZ)`; redirect to a fixed time.
        mock_datetime.now.return_value = now

        from main import main
        main()

        mock_run_polling.assert_called_once()
        kwargs = mock_run_polling.call_args.kwargs
        assert kwargs["duration_seconds"] == 120
        assert kwargs["interval_seconds"] == 60


def test_main_polling_duration_capped_at_300_midday(config):
    """Midday, 300s cap applies (8h remaining > 300s, so duration stays 300)."""
    tz = pytz.timezone("Asia/Shanghai")
    now = tz.localize(datetime(2026, 7, 25, 12, 0, 0))

    with patch("main.load_config", return_value=config), \
         patch("main.datetime") as mock_datetime, \
         patch("main.is_within_run_window", return_value=True), \
         patch("main.should_use_polling_mode", return_value=True), \
         patch("main.run_polling") as mock_run_polling:
        mock_datetime.now.return_value = now

        from main import main
        main()

        kwargs = mock_run_polling.call_args.kwargs
        assert kwargs["duration_seconds"] == 300


def test_main_polling_duration_zero_at_window_end(config):
    """At exactly 20:00, main() exits before polling (is_within_run_window False)."""
    tz = pytz.timezone("Asia/Shanghai")
    now = tz.localize(datetime(2026, 7, 25, 20, 0, 0))

    with patch("main.load_config", return_value=config), \
         patch("main.datetime") as mock_datetime, \
         patch("main.is_within_run_window", return_value=False), \
         patch("main.should_use_polling_mode", return_value=True), \
         patch("main.run_polling") as mock_run_polling:
        mock_datetime.now.return_value = now

        from main import main
        main()

        mock_run_polling.assert_not_called()
