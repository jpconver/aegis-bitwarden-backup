#!/usr/bin/env python3
from __future__ import annotations

import os
import shlex
from pathlib import Path


def default_config_dir() -> Path:
    xdg_config_home = os.environ.get("XDG_CONFIG_HOME")
    if xdg_config_home:
        return Path(xdg_config_home) / "aegis"
    return Path.home() / ".config" / "aegis"


def default_config_file() -> Path:
    return Path(os.environ.get("AEGIS_CONFIG_FILE", default_config_dir() / "config.env"))


def load_config_file(path: Path | None = None) -> dict[str, str]:
    config_path = path or default_config_file()
    if not config_path.is_file():
        return {}

    values: dict[str, str] = {}
    for raw_line in config_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        try:
            values[key] = shlex.split(value, posix=True)[0] if value else ""
        except ValueError:
            values[key] = value
    return values


def resolve_secrets_path(config: dict[str, str] | None = None) -> Path:
    config = config or load_config_file()
    return Path(
        os.environ.get(
            "SECRETS_PATH",
            os.environ.get(
                "AEGIS_SECRETS_PATH",
                config.get("SECRETS_PATH")
                or config.get("AEGIS_SECRETS_PATH")
                or str(Path.home() / "projects" / "security" / "secrets"),
            ),
        )
    )


def resolve_state_dir(
    secrets_path: Path | None = None,
    config: dict[str, str] | None = None,
) -> Path:
    config = config or load_config_file()
    if "AEGIS_STATE_DIR" in os.environ:
        return Path(os.environ["AEGIS_STATE_DIR"])
    if "AEGIS_STATE_DIR" in config:
        return Path(config["AEGIS_STATE_DIR"])

    default_state_dir = default_config_dir()
    try:
        default_state_dir.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        base = secrets_path or resolve_secrets_path(config)
        return base / ".aegis-state"
    return default_state_dir


def resolve_dropbox_credentials_file(
    state_dir: Path | None = None,
    config: dict[str, str] | None = None,
) -> Path:
    config = config or load_config_file()
    if "AEGIS_DROPBOX_CREDENTIALS_FILE" in os.environ:
        return Path(os.environ["AEGIS_DROPBOX_CREDENTIALS_FILE"])
    if "AEGIS_DROPBOX_CREDENTIALS_FILE" in config:
        return Path(config["AEGIS_DROPBOX_CREDENTIALS_FILE"])

    base_state_dir = state_dir or resolve_state_dir(config=config)
    return base_state_dir / "dropbox.json"
