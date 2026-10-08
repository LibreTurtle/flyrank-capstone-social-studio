import os
from pathlib import Path


def load_environment_file() -> None:
    env_file = Path(__file__).parent.parent / ".env"
    if not env_file.exists():
        return

    for line in env_file.read_text().splitlines():
        entry = line.strip()
        if not entry or entry.startswith("#") or "=" not in entry:
            continue
        name, value = entry.split("=", 1)
        value = value.strip().strip("\"'")
        os.environ.setdefault(name.strip(), value)
