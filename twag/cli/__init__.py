"""CLI entry point for twag."""

import rich_click as click

from .. import __version__

# Re-export symbols that tests monkeypatch on `twag.cli`
from ..db import get_connection, get_tweet_by_id, get_unprocessed_tweets, init_db  # noqa: F401

# Import command modules — avoid shadowing module names with command objects
# so that `import twag.cli.<module>` still resolves to the module.
from . import accounts as _accounts_mod
from . import analyze as _analyze_mod
from . import config_cmd as _config_mod
from . import db_cmd as _db_mod
from . import digest as _digest_mod
from . import fetch as _fetch_mod
from . import init_cmd as _init_mod
from . import narratives as _narratives_mod
from . import process as _process_mod
from . import search as _search_mod
from . import stats as _stats_mod
from . import web as _web_mod
from .analyze import _analysis_wrap_width as _analysis_wrap_width
from .analyze import _echo_labeled as _echo_labeled
from .analyze import _echo_wrapped as _echo_wrapped
from .analyze import _print_status_analysis as _print_status_analysis


@click.group()
@click.version_option(version=__version__)
def cli():
    """Twitter aggregator for market-relevant signals."""
    pass


# Register commands
cli.add_command(_init_mod.init)
cli.add_command(_init_mod.doctor)
cli.add_command(_fetch_mod.fetch)
cli.add_command(_process_mod.process)
cli.add_command(_analyze_mod.analyze)
cli.add_command(_digest_mod.digest)
cli.add_command(_accounts_mod.accounts)
cli.add_command(_narratives_mod.narratives)
cli.add_command(_stats_mod.stats)
cli.add_command(_stats_mod.prune)
cli.add_command(_stats_mod.export)
cli.add_command(_config_mod.config)
cli.add_command(_db_mod.db)
cli.add_command(_search_mod.search)
cli.add_command(_web_mod.web)


if __name__ == "__main__":
    cli()
