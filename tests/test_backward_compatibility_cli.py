"""Backward-compatibility guards for the CLI surface.

Pins every command listed in CLAUDE.md and SKILL.md so that renames or
removals fail loudly in CI rather than silently breaking user shell scripts,
cron jobs, and OpenClaw automations.
"""

import rich_click as click

from twag.cli import cli as root_cli


def _command_names(group: click.Group) -> set[str]:
    return set(group.commands.keys())


def _subcommand_names(group: click.Group, name: str) -> set[str]:
    sub = group.commands.get(name)
    assert isinstance(sub, click.Group), f"Expected '{name}' to be a click group, got {type(sub).__name__}"
    return set(sub.commands.keys())


# Top-level commands documented in CLAUDE.md and SKILL.md.
EXPECTED_TOP_LEVEL = {
    "init",
    "doctor",
    "fetch",
    "process",
    "analyze",
    "digest",
    "accounts",
    "narratives",
    "stats",
    "prune",
    "export",
    "config",
    "db",
    "search",
    "web",
}

EXPECTED_ACCOUNTS_SUBS = {
    "list",
    "add",
    "promote",
    "demote",
    "mute",
    "boost",
    "decay",
    "import",
}

EXPECTED_NARRATIVES_SUBS = {"list"}

EXPECTED_CONFIG_SUBS = {"show", "path", "set"}

EXPECTED_DB_SUBS = {
    "path",
    "shell",
    "init",
    "rebuild-fts",
    "dump",
    "restore",
}


def test_top_level_commands_registered():
    actual = _command_names(root_cli)
    missing = EXPECTED_TOP_LEVEL - actual
    assert not missing, (
        f"Top-level CLI commands documented in CLAUDE.md/SKILL.md are not registered: {missing}. "
        "Either restore the command or remove it from the docs."
    )


def test_accounts_subcommands_registered():
    actual = _subcommand_names(root_cli, "accounts")
    missing = EXPECTED_ACCOUNTS_SUBS - actual
    assert not missing, f"twag accounts is missing documented subcommands: {missing}"


def test_narratives_subcommands_registered():
    actual = _subcommand_names(root_cli, "narratives")
    missing = EXPECTED_NARRATIVES_SUBS - actual
    assert not missing, f"twag narratives is missing documented subcommands: {missing}"


def test_config_subcommands_registered():
    actual = _subcommand_names(root_cli, "config")
    missing = EXPECTED_CONFIG_SUBS - actual
    assert not missing, f"twag config is missing documented subcommands: {missing}"


def test_db_subcommands_registered():
    actual = _subcommand_names(root_cli, "db")
    missing = EXPECTED_DB_SUBS - actual
    assert not missing, f"twag db is missing documented subcommands: {missing}"


def test_re_exports_for_test_monkeypatching():
    """``twag.cli`` re-exports DB symbols that downstream tests monkeypatch."""
    import twag.cli as cli_mod

    for name in ("get_connection", "get_tweet_by_id", "get_unprocessed_tweets", "init_db"):
        assert hasattr(cli_mod, name), f"twag.cli must re-export {name}"
