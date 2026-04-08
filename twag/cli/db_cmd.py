"""Database commands."""

import sys
from datetime import datetime
from pathlib import Path

import rich_click as click

from ..config import get_database_path
from ..db import check_schema, dump_sql, get_connection, init_db, rebuild_fts, restore_sql
from ..db.migrations import TARGET_VERSION
from ._console import console


@click.group()
def db():
    """Database operations."""


@db.command("path")
def db_path():
    """Show database file path."""
    console.print(str(get_database_path()))


@db.command("shell")
def db_shell():
    """Open SQLite shell."""
    import subprocess

    db_file = get_database_path()
    subprocess.run(["sqlite3", str(db_file)], check=False)


@db.command("init")
def db_init():
    """Initialize/reset the database."""
    init_db()
    console.print(f"Database initialized at: {get_database_path()}")


@db.command("rebuild-fts")
def db_rebuild_fts():
    """Rebuild the FTS5 full-text search index."""
    console.print("Rebuilding FTS index...")
    with get_connection() as conn:
        count = rebuild_fts(conn)
        conn.commit()
    console.print(f"Indexed {count} tweets")


@db.command("dump")
@click.argument("output", type=click.Path(), default=None, required=False)
@click.option("--stdout", is_flag=True, help="Output to stdout instead of file")
def db_dump(output: str | None, stdout: bool):
    r"""Dump database to SQL file (FTS5-safe).

    \b
    Examples:
      twag db dump                    # Creates twag-YYYYMMDD-HHMMSS.sql
      twag db dump backup.sql         # Creates backup.sql
      twag db dump --stdout | gzip    # Pipe to compression
    """
    db_file = get_database_path()

    if not db_file.exists():
        console.print(f"[red]Database not found: {db_file}[/red]")
        sys.exit(1)

    if stdout:
        for stmt in dump_sql(db_file):
            click.echo(stmt)
    else:
        if output is None:
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            output = f"twag-{timestamp}.sql"

        output_path = Path(output)

        with open(output_path, "w") as f:
            for stmt in dump_sql(db_file):
                f.write(f"{stmt}\n")

        # Get file size
        size_bytes = output_path.stat().st_size
        if size_bytes >= 1024 * 1024:
            size_str = f"{size_bytes / (1024 * 1024):.1f} MB"
        elif size_bytes >= 1024:
            size_str = f"{size_bytes / 1024:.1f} KB"
        else:
            size_str = f"{size_bytes} bytes"

        console.print(f"Dumped database to: {output_path} ({size_str})")


@db.command("restore")
@click.argument("input_file", type=click.Path(exists=True))
@click.option("--force", is_flag=True, help="Overwrite existing database without prompting")
def db_restore(input_file: str, force: bool):
    r"""Restore database from SQL dump (handles .gz files).

    \b
    WARNING: This will replace the existing database!
    FTS5 index is rebuilt automatically after restore.

    \b
    Examples:
      twag db restore backup.sql
      twag db restore backup.sql.gz --force
      twag db restore twag-20240115-120000.sql --force
    """
    import gzip

    db_file = get_database_path()
    input_path = Path(input_file)

    # Warn about overwriting
    if db_file.exists() and not force:
        try:
            with get_connection() as conn:
                cursor = conn.execute("SELECT COUNT(*) FROM tweets")
                tweet_count = cursor.fetchone()[0]
            msg = f"This will replace the existing database ({tweet_count} tweets). Continue?"
        except Exception:
            msg = "This will replace the existing database. Continue?"

        if not click.confirm(msg):
            console.print("Aborted.")
            return

    console.print(f"Restoring from: {input_path}")

    # Read the SQL dump, handling .gz transparently
    if input_path.suffix == ".gz" or input_path.name.endswith(".sql.gz"):
        with gzip.open(input_path, "rt", encoding="utf-8") as f:
            sql_script = f.read()
    else:
        with open(input_path) as f:
            sql_script = f.read()

    try:
        counts = restore_sql(sql_script, db_file, backup=True)
        console.print(
            f"Restored database: {counts['tweets']} tweets, {counts['accounts']} accounts, {counts['fts']} FTS entries",
        )
    except Exception as e:
        console.print(f"[red]Error restoring database: {e}[/red]")
        sys.exit(1)


@db.command("schema-version")
def db_schema_version():
    """Show current and target schema versions."""
    db_file = get_database_path()
    if not db_file.exists():
        console.print("[red]Database not found.[/red]")
        sys.exit(1)

    with get_connection(readonly=True) as conn:
        cursor = conn.execute("PRAGMA user_version")
        current = cursor.fetchone()[0]

    console.print(f"Current schema version: {current}")
    console.print(f"Target schema version:  {TARGET_VERSION}")
    if current < TARGET_VERSION:
        console.print("[yellow]Database needs migration. Run: twag db init[/yellow]")
    else:
        console.print("[green]Schema is up to date.[/green]")


@db.command("check")
def db_check():
    """Check database schema for drift against expected state."""
    db_file = get_database_path()
    if not db_file.exists():
        console.print("[red]Database not found.[/red]")
        sys.exit(1)

    with get_connection(readonly=True) as conn:
        result = check_schema(conn)

    console.print(f"Schema version: {result['version_current']}/{result['version_target']}")

    if not result["version_ok"]:
        console.print(
            f"[yellow]Version mismatch: have {result['version_current']}, need {result['version_target']}[/yellow]",
        )

    if result["missing_tables"]:
        console.print(f"[red]Missing tables: {', '.join(result['missing_tables'])}[/red]")

    if result["missing_columns"]:
        for table, cols in result["missing_columns"].items():
            console.print(f"[red]Missing columns in {table}: {', '.join(cols)}[/red]")

    if result["ok"]:
        console.print("[green]Schema check passed — no drift detected.[/green]")
    else:
        console.print("[yellow]Run 'twag db init' to apply pending migrations.[/yellow]")
        sys.exit(1)
