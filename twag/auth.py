"""Centralised environment-file parsing and credential helpers."""

import os
from pathlib import Path


def load_env_file(path: Path | None = None) -> dict[str, str]:
    """Parse a .env file, returning a dict of key-value pairs.

    Skips blank lines and comments.  Handles ``export KEY=value`` and
    quoted values.  If *path* is ``None`` the default ``~/.env`` is used.
    """
    if path is None:
        path = Path.home() / ".env"

    env: dict[str, str] = {}
    if not path.exists():
        return env

    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            if line.startswith("export "):
                line = line[7:]
            key, value = line.split("=", 1)
            value = value.strip("\"'")
            env[key] = value

    return env


def get_api_key(key_name: str) -> str:
    """Return an API key from the environment or ``~/.env``.

    Raises ``ValueError`` when the key cannot be found.
    """
    value = os.environ.get(key_name)
    if not value:
        value = load_env_file().get(key_name)
    if not value:
        raise ValueError(f"{key_name} not set")
    return value


def get_auth_env() -> dict[str, str]:
    """Return a copy of ``os.environ`` enriched with ``~/.env`` entries.

    Used by the fetcher to pass auth tokens to the ``bird`` subprocess.
    """
    env = os.environ.copy()
    env.update(load_env_file())
    return env
