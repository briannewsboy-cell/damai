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
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError:
        return State()
    known_fields = {f.name for f in State.__dataclass_fields__.values()}
    filtered = {k: v for k, v in data.items() if k in known_fields}
    return State(**filtered)


def save_state(path: str, state: State) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(asdict(state), f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def should_notify(old: State, new: State) -> bool:
    return new.last_status == "on_sale" and (
        old.last_status != "on_sale" or not old.notified
    )
