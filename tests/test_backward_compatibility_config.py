"""Backward-compatibility guards for config loading.

Existing user installs may have a minimal config.json that doesn't include
keys added in later versions. ``load_config`` must keep working for those
users by falling back to ``DEFAULT_CONFIG`` for any missing key — never by
demanding a key be present.
"""

import json

import twag.config as config_mod


def _isolate_config(monkeypatch, tmp_path, payload: dict | None) -> None:
    """Point ``twag.config`` at a tmp_path-based config and clear its cache."""
    cfg_dir = tmp_path / "twag"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    cfg_path = cfg_dir / "config.json"
    if payload is not None:
        cfg_path.write_text(json.dumps(payload))

    monkeypatch.setattr(config_mod, "get_config_path", lambda: cfg_path)
    monkeypatch.setattr(config_mod, "_config_cache", None, raising=False)


def test_minimal_legacy_config_loads_without_error(monkeypatch, tmp_path):
    """A legacy config with only a single key must merge against defaults."""
    legacy = {"scoring": {"min_score_for_digest": 5}}
    _isolate_config(monkeypatch, tmp_path, legacy)

    cfg = config_mod.load_config()

    # User-provided value preserved.
    assert cfg["scoring"]["min_score_for_digest"] == 5
    # Newer keys still come through from defaults.
    assert "high_signal_threshold" in cfg["scoring"]
    assert "alert_threshold" in cfg["scoring"]
    # Newer top-level sections still come through from defaults.
    assert "llm" in cfg
    assert "notifications" in cfg
    assert "fetch" in cfg
    assert "bird" in cfg


def test_empty_config_loads_with_defaults(monkeypatch, tmp_path):
    _isolate_config(monkeypatch, tmp_path, {})

    cfg = config_mod.load_config()
    assert cfg["scoring"]["min_score_for_digest"] == config_mod.DEFAULT_CONFIG["scoring"]["min_score_for_digest"]
    assert cfg["llm"]["triage_provider"] == config_mod.DEFAULT_CONFIG["llm"]["triage_provider"]


def test_missing_config_file_uses_defaults(monkeypatch, tmp_path):
    """No config file at all must not break — fall back to defaults entirely."""
    _isolate_config(monkeypatch, tmp_path, payload=None)

    cfg = config_mod.load_config()
    assert cfg == config_mod.DEFAULT_CONFIG or cfg["scoring"] == config_mod.DEFAULT_CONFIG["scoring"]


def test_data_dir_falls_back_for_legacy_config(monkeypatch, tmp_path):
    """A legacy config without paths.data_dir must still resolve a data dir."""
    monkeypatch.delenv("TWAG_DATA_DIR", raising=False)
    legacy = {"scoring": {"min_score_for_digest": 5}}
    _isolate_config(monkeypatch, tmp_path, legacy)

    fake_xdg = tmp_path / "xdg-data"
    monkeypatch.setattr(config_mod, "get_xdg_data_home", lambda: fake_xdg)

    data_dir = config_mod.get_data_dir()
    assert data_dir == fake_xdg / config_mod.APP_NAME

    db_path = config_mod.get_database_path()
    assert db_path == fake_xdg / config_mod.APP_NAME / "twag.db"

    following_path = config_mod.get_following_path()
    assert following_path == fake_xdg / config_mod.APP_NAME / "following.txt"


def test_legacy_config_does_not_corrupt_cache(monkeypatch, tmp_path):
    """Loading a legacy config twice returns equivalent results.

    Guards against shared mutable state between cache hits — a caller mutating
    one returned dict must not break the next caller.
    """
    legacy = {"scoring": {"min_score_for_digest": 5}}
    _isolate_config(monkeypatch, tmp_path, legacy)

    first = config_mod.load_config()
    first["scoring"]["min_score_for_digest"] = 999
    first["llm"]["triage_provider"] = "mutated"

    second = config_mod.load_config()
    assert second["scoring"]["min_score_for_digest"] == 5
    assert second["llm"]["triage_provider"] == config_mod.DEFAULT_CONFIG["llm"]["triage_provider"]


def test_required_default_keys_exist():
    """Sanity check on the defaults contract itself.

    These keys are read directly by various modules; if any of them disappears
    from DEFAULT_CONFIG, calling code will silently break for users with old
    config files (since their config wouldn't have them either).
    """
    required_paths = [
        ("llm", "triage_provider"),
        ("llm", "triage_model"),
        ("scoring", "min_score_for_digest"),
        ("scoring", "high_signal_threshold"),
        ("scoring", "alert_threshold"),
        ("notifications", "telegram_enabled"),
        ("accounts", "decay_rate"),
        ("fetch", "tier1_delay"),
        ("bird", "auth_token_env"),
    ]
    for path in required_paths:
        node = config_mod.DEFAULT_CONFIG
        for key in path:
            assert key in node, f"DEFAULT_CONFIG is missing required key: {'.'.join(path)}"
            node = node[key]
