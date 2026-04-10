"""Database commands."""

import sys
from datetime import datetime
from pathlib import Path

import rich_click as click

from ..config import get_database_path
from ..db import dump_sql, get_connection, init_db, rebuild_fts, restore_sql
from ..db.migrations import (
    LATEST_VERSION,
    _get_columns,
    get_applied_migrations,
    get_current_version,
    get_expected_tables,
    get_pending_migrations,
    run_pending_migrations,
)
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


@db.command("schema-status")
def db_schema_status():
    """Show current schema version, applied and pending migrations, and column diff."""
    db_file = get_database_path()
    if not db_file.exists():
        console.print("[red]Database not found. Run 'twag db init' first.[/red]")
        sys.exit(1)

    with get_connection(readonly=True) as conn:
        current = get_current_version(conn)
        applied = get_applied_migrations(conn)
        pending = get_pending_migrations(current)

        console.print(f"[bold]Schema version:[/bold] {current} / {LATEST_VERSION}")
        console.print()

        if applied:
            console.print("[bold]Applied migrations:[/bold]")
            for m in applied:
                console.print(f"  v{m['version']:>2}  {m['name']:<25} {m['applied_at'] or '—'}")
        else:
            console.print("[dim]No migrations recorded in audit table.[/dim]")

        console.print()

        if pending:
            console.print(f"[yellow]Pending migrations ({len(pending)}):[/yellow]")
            for m in pending:
                console.print(f"  v{m.version:>2}  {m.name:<25} {m.description}")
        else:
            console.print("[green]All migrations applied.[/green]")

        # Column diff
        console.print()
        console.print("[bold]Column diff (expected vs actual):[/bold]")
        expected_tables = get_expected_tables()
        has_diff = False
        for table, expected_cols in sorted(expected_tables.items()):
            try:
                actual_cols = _get_columns(conn, table)
            except Exception:
                console.print(f"  [red]{table}: TABLE MISSING[/red]")
                has_diff = True
                continue
            missing = expected_cols - actual_cols
            extra = actual_cols - expected_cols
            if missing or extra:
                has_diff = True
                console.print(f"  [yellow]{table}:[/yellow]")
                for col in sorted(missing):
                    console.print(f"    [red]- {col} (missing)[/red]")
                for col in sorted(extra):
                    console.print(f"    [dim]+ {col} (extra)[/dim]")
        if not has_diff:
            console.print("  [green]All tables match expected schema.[/green]")


@db.command("migrate")
@click.option("--dry-run", is_flag=True, help="Show what would change without applying")
def db_migrate(dry_run: bool):
    """Run pending schema migrations explicitly."""
    db_file = get_database_path()
    if not db_file.exists():
        console.print("[red]Database not found. Run 'twag db init' first.[/red]")
        sys.exit(1)

    with get_connection() as conn:
        current = get_current_version(conn)
        pending = get_pending_migrations(current)

        if not pending:
            console.print(f"[green]Database is up to date (v{current}).[/green]")
            return

        if dry_run:
            console.print(f"[bold]Dry run:[/bold] {len(pending)} migration(s) would be applied:")
            for m in pending:
                console.print(f"  v{m.version:>2}  {m.name:<25} {m.description}")
            return

        applied = run_pending_migrations(conn)
        conn.commit()
        new_version = get_current_version(conn)
        console.print(f"[green]Applied {len(applied)} migration(s). Schema version: {current} → {new_version}[/green]")
