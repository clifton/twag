"""Init and doctor commands."""

import sys

import rich_click as click
from rich.panel import Panel

from ..config import (
    get_config_path,
    get_data_dir,
    get_database_path,
    get_digests_dir,
    get_following_path,
    load_config,
    save_config,
)
from ..db import get_connection, init_db
from ._console import console, status_icon


@click.command()
@click.option("--force", is_flag=True, help="Overwrite existing config file")
def init(force: bool):
    """Initialize twag data directories and configuration.

    Creates:
    - Data directory (~/.local/share/twag/ or TWAG_DATA_DIR)
    - Config file (~/.config/twag/config.json)
    - Database (twag.db)
    - Digests directory
    """
    data_dir = get_data_dir()
    config_path = get_config_path()
    db_path = get_database_path()
    digests_dir = get_digests_dir()
    following_path = get_following_path()

    console.print("Initializing twag...")
    console.print(f"  Data directory: {data_dir}")
    console.print(f"  Config file: {config_path}")

    # Create data directory
    data_dir.mkdir(parents=True, exist_ok=True)
    console.print(f"  {status_icon(True)} Data directory created")

    # Create digests directory
    digests_dir.mkdir(parents=True, exist_ok=True)
    console.print(f"  {status_icon(True)} Digests directory created")

    # Create config file
    if config_path.exists() and not force:
        console.print("  [yellow]SKIP[/yellow] Config already exists (use --force to overwrite)")
    else:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        save_config(load_config())
        console.print(f"  {status_icon(True)} Config file created")

    # Initialize database
    init_db()
    console.print(f"  {status_icon(True)} Database initialized at {db_path}")

    # Create empty following.txt if it doesn't exist
    if not following_path.exists():
        following_path.write_text("# Add Twitter handles to track (one per line)\n# Example: @NickTimiraos\n")
        console.print(f"  {status_icon(True)} Following file created at {following_path}")
    else:
        console.print("  [yellow]SKIP[/yellow] Following file already exists")

    console.print("")
    console.print("Initialization complete! Next steps:")
    console.print("  1. Set API keys: export GEMINI_API_KEY=... ANTHROPIC_API_KEY=...")
    console.print("  2. Set Twitter auth: export AUTH_TOKEN=... CT0=...")
    console.print("  3. Run: twag doctor")
    console.print("  4. Add accounts: twag accounts add @handle")
    console.print("  5. Fetch tweets: twag fetch")


@click.command()
def doctor():
    """Check twag dependencies and configuration.

    Verifies:
    - Required directories exist
    - Config file is valid
    - API keys are set
    - bird CLI is available
    - Database is accessible
    """
    import os
    import shutil

    issues = []
    warnings = []

    console.print("Checking twag configuration...\n")

    # 1. Check data directory
    data_dir = get_data_dir()
    console.print(f"Data directory: {data_dir}")
    if data_dir.exists():
        console.print(f"  {status_icon(True)} Directory exists")
    else:
        console.print(f"  {status_icon(False)} Directory does not exist")
        issues.append("Run 'twag init' to create data directory")

    # 2. Check config file
    config_path = get_config_path()
    console.print(f"\nConfig file: {config_path}")
    if config_path.exists():
        try:
            load_config()
            console.print(f"  {status_icon(True)} Config file valid")
        except Exception as e:
            console.print(f"  {status_icon(False)} Config file invalid: {e}")
            issues.append("Fix or delete config file")
    else:
        console.print("  [yellow]WARN[/yellow] Config file not found (using defaults)")
        warnings.append("Run 'twag init' to create config file")

    # 3. Check database
    db_path = get_database_path()
    console.print(f"\nDatabase: {db_path}")
    if db_path.exists():
        try:
            with get_connection() as conn:
                cursor = conn.execute("SELECT COUNT(*) FROM tweets")
                count = cursor.fetchone()[0]
            console.print(f"  {status_icon(True)} Database accessible ({count} tweets)")
        except Exception as e:
            console.print(f"  {status_icon(False)} Database error: {e}")
            issues.append("Run 'twag db init' to repair database")
    else:
        console.print("  [yellow]WARN[/yellow] Database not found")
        warnings.append("Run 'twag init' to create database")

    # 4. Check bird CLI
    console.print("\nbird CLI:")
    bird_path = shutil.which("bird")
    if bird_path:
        console.print(f"  {status_icon(True)} Found at {bird_path}")
    else:
        console.print(f"  {status_icon(False)} bird CLI not found in PATH")
        issues.append("Install bird CLI: cargo install bird-cli or see https://github.com/...")

    # 5. Check API keys
    console.print("\nAPI keys:")

    gemini_key = os.environ.get("GEMINI_API_KEY")
    if gemini_key:
        console.print(f"  {status_icon(True)} GEMINI_API_KEY set ({gemini_key[:8]}...)")
    else:
        console.print(f"  {status_icon(False)} GEMINI_API_KEY not set")
        issues.append("Set GEMINI_API_KEY environment variable")

    anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
    if anthropic_key:
        console.print(f"  {status_icon(True)} ANTHROPIC_API_KEY set ({anthropic_key[:8]}...)")
    else:
        console.print("  [yellow]WARN[/yellow] ANTHROPIC_API_KEY not set (enrichment disabled)")
        warnings.append("Set ANTHROPIC_API_KEY for enrichment features")

    # 6. Check Twitter auth
    console.print("\nTwitter auth:")
    auth_token = os.environ.get("AUTH_TOKEN")
    ct0 = os.environ.get("CT0")

    if auth_token:
        console.print(f"  {status_icon(True)} AUTH_TOKEN set")
    else:
        console.print(f"  {status_icon(False)} AUTH_TOKEN not set")
        issues.append("Set AUTH_TOKEN environment variable")

    if ct0:
        console.print(f"  {status_icon(True)} CT0 set")
    else:
        console.print(f"  {status_icon(False)} CT0 not set")
        issues.append("Set CT0 environment variable")

    # 7. Check Telegram (optional)
    console.print("\nTelegram notifications:")
    telegram_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    telegram_chat = os.environ.get("TELEGRAM_CHAT_ID")

    if telegram_token and telegram_chat:
        console.print(f"  {status_icon(True)} Telegram configured")
    elif telegram_token or telegram_chat:
        console.print("  [yellow]WARN[/yellow] Partial Telegram config")
        warnings.append("Set both TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID")
    else:
        console.print("  [dim]INFO[/dim] Telegram not configured (optional)")

    # Summary
    console.print("\n" + "=" * 50)

    if issues:
        console.print(
            Panel(
                "\n".join(f"  - {issue}" for issue in issues),
                title=f"{len(issues)} issue(s) found",
                border_style="red",
            )
        )
        sys.exit(1)
    elif warnings:
        console.print(
            Panel(
                "\n".join(f"  - {w}" for w in warnings),
                title=f"All checks passed with {len(warnings)} warning(s)",
                border_style="yellow",
            )
        )
    else:
        console.print("\n[green]All checks passed![/green]")
