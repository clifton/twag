"""Table utilities for rendering extracted table data."""

from tabulate import tabulate


def table_to_markdown(table: dict) -> str:
    """Convert table data to aligned markdown format.

    Args:
        table: Dict with "columns" (list of str) and "rows" (list of lists)

    Returns:
        Markdown-formatted table string with aligned columns
    """
    cols = table.get("columns", [])
    rows = table.get("rows", [])

    if not cols and not rows:
        return ""

    return tabulate(rows, headers=cols, tablefmt="github")


def should_show_inline(table: dict, threshold: int = 10) -> bool:
    """Check if table should be shown inline (vs behind a toggle).

    Args:
        table: Dict with "rows" key
        threshold: Max rows to show inline (default 10)

    Returns:
        True if table should be shown inline, False for toggle
    """
    rows = table.get("rows", [])
    return len(rows) <= threshold
