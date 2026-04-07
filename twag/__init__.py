"""Twitter Aggregator - Market-relevant signal curation from Twitter/X."""

from . import metrics

try:
    from importlib.metadata import version

    __version__ = version("twag")
except Exception:
    __version__ = "0.0.0-dev"

__all__ = ["__version__", "metrics"]
