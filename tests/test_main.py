from datetime import datetime, timezone
from unittest.mock import Mock, patch

import pytest
import pytz

from checkers.base import ConcertResult
from config import Config
from main import (
    POLL_SWITCH_DATE,
    RUN_WINDOW_END,
    RUN_WINDOW_START,
    is_within_run_window,
    run_once,
    run_polling,
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


def test_should_use_polling_mode_after_switch_date():
    tz = pytz.timezone("Asia/Shanghai")
    now = tz.localize(datetime(2026, 7, 31, 19, 59))
    assert should_use_polling_mode(now) is True


def test_run_window_constants_match_plan():
    assert RUN_WINDOW_START == 9
    assert RUN_WINDOW_END == 20
    assert POLL_SWITCH_DATE == "2026-07-20"


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
    """A failing run_once iteration must not terminate the polling loop."""
    # time.time() sequence:
    #   0.0   -> deadline = 0 + 10 = 10
    #   1.0   -> while-check: 1 < 10, enter iter 1 (run_once raises, caught)
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
