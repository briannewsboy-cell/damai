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
