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
