"""Static metrics-instrumentation coverage analyzer.

Walks the ``twag/`` source tree, detects metrics API call sites with the
:mod:`ast` module, and reports per-subsystem instrumentation coverage and
prefix mismatches without needing runtime data.

This complements :mod:`twag.metrics`, which only knows about subsystems that
have *already recorded* a metric in the current process.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path

# ── Subsystem map ─────────────────────────────────────────────────────────

# Adding a new subsystem only requires editing this map. The path prefix is
# matched against the module's path under twag/, the metric prefix against
# the metric name (literal first arg) at each call site.
SUBSYSTEM_MAP: dict[str, dict[str, str]] = {
    "scorer": {
        "path_prefix": "scorer/",
        "metric_prefix": "scorer.",
        "description": "LLM scoring (latency, tokens, errors, retries)",
    },
    "pipeline": {
        "path_prefix": "processor/",
        "metric_prefix": "pipeline.",
        "description": "Pipeline processing (batch timing, triage counts)",
    },
    "fetcher": {
        "path_prefix": "fetcher/",
        "metric_prefix": "fetcher.",
        "description": "Tweet fetching (latency, retries, errors)",
    },
    "web": {
        "path_prefix": "web/",
        "metric_prefix": "web.",
        "description": "Web layer (request count, latency)",
    },
    "db": {
        "path_prefix": "db/",
        "metric_prefix": "db.",
        "description": "Database layer",
    },
    "notifier": {
        "path_prefix": "notifier",
        "metric_prefix": "notifier.",
        "description": "Telegram notifications",
    },
    "renderer": {
        "path_prefix": "renderer",
        "metric_prefix": "renderer.",
        "description": "Digest rendering",
    },
}

# Method names on a MetricsCollector instance that record a metric.
_COLLECTOR_METHODS = {"inc", "observe", "set_gauge"}

# Module-level convenience functions in twag.metrics that record a metric.
_MODULE_FUNCS = {"counter", "histogram", "timer"}


@dataclass
class CallSite:
    """A single metrics API invocation discovered by the AST scan."""

    module: str  # dotted path under twag, e.g. "fetcher.bird_cli"
    file: str  # path relative to twag/
    lineno: int
    api: str  # e.g. "inc", "observe", "counter", "timer"
    metric_name: str | None  # literal first arg, if a constant string
    inferred_subsystem: str | None  # from file path
    name_subsystem: str | None  # from metric_name prefix


@dataclass
class SubsystemCoverage:
    name: str
    description: str
    expected: bool
    instrumented_modules: set[str] = field(default_factory=set)
    total_modules: int = 0
    call_sites: int = 0
    metric_names: set[str] = field(default_factory=set)
    prefix_mismatches: list[CallSite] = field(default_factory=list)


@dataclass
class CoverageReport:
    subsystems: dict[str, SubsystemCoverage]
    uninstrumented_modules: list[str]
    total_modules: int
    instrumented_modules: int
    call_sites: list[CallSite]

    @property
    def coverage_pct(self) -> float:
        if self.total_modules == 0:
            return 0.0
        return 100.0 * self.instrumented_modules / self.total_modules


# ── Public API ────────────────────────────────────────────────────────────


def analyze_coverage(root: Path) -> CoverageReport:
    """Walk ``root`` (a twag package directory) and produce a coverage report."""
    files = sorted(_iter_source_files(root))
    all_call_sites: list[CallSite] = []
    instrumented_modules: set[str] = set()
    module_to_subsystem: dict[str, str | None] = {}

    for file in files:
        rel = file.relative_to(root)
        rel_str = rel.as_posix()
        module = _module_dotted_name(rel)
        module_to_subsystem[module] = _path_to_subsystem(rel_str)

        try:
            tree = ast.parse(file.read_text(encoding="utf-8"), filename=str(file))
        except (SyntaxError, UnicodeDecodeError):
            continue

        sites = _extract_call_sites(tree, module=module, file=rel_str)
        if sites:
            instrumented_modules.add(module)
            all_call_sites.extend(sites)

    subsystems: dict[str, SubsystemCoverage] = {}
    for name, spec in SUBSYSTEM_MAP.items():
        subsystems[name] = SubsystemCoverage(
            name=name,
            description=spec["description"],
            expected=True,
            total_modules=sum(1 for m, sub in module_to_subsystem.items() if sub == name),
        )

    for site in all_call_sites:
        sub = site.inferred_subsystem or site.name_subsystem
        if sub and sub in subsystems:
            cov = subsystems[sub]
            cov.instrumented_modules.add(site.module)
            cov.call_sites += 1
            if site.metric_name:
                cov.metric_names.add(site.metric_name)
            if (
                site.inferred_subsystem is not None
                and site.name_subsystem is not None
                and site.inferred_subsystem != site.name_subsystem
            ):
                cov.prefix_mismatches.append(site)

    uninstrumented = sorted(
        module for module, sub in module_to_subsystem.items() if sub is not None and module not in instrumented_modules
    )

    return CoverageReport(
        subsystems=subsystems,
        uninstrumented_modules=uninstrumented,
        total_modules=len(module_to_subsystem),
        instrumented_modules=len(instrumented_modules),
        call_sites=all_call_sites,
    )


# ── Internals ─────────────────────────────────────────────────────────────


def _iter_source_files(root: Path) -> Iterable[Path]:
    skip_dirs = {"__pycache__", "frontend", "templates", "tests"}
    for path in root.rglob("*.py"):
        if any(part in skip_dirs for part in path.parts):
            continue
        yield path


def _module_dotted_name(rel: Path) -> str:
    parts = list(rel.with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _path_to_subsystem(rel_str: str) -> str | None:
    for name, spec in SUBSYSTEM_MAP.items():
        prefix = spec["path_prefix"]
        # Match either "fetcher/" (a directory) or "notifier" (a file stem).
        if prefix.endswith("/"):
            if rel_str.startswith(prefix):
                return name
        elif rel_str == f"{prefix}.py" or rel_str.startswith(f"{prefix}/"):
            return name
    return None


def _name_to_subsystem(metric_name: str) -> str | None:
    for name, spec in SUBSYSTEM_MAP.items():
        if metric_name.startswith(spec["metric_prefix"]):
            return name
    return None


def _extract_call_sites(tree: ast.AST, *, module: str, file: str) -> list[CallSite]:
    sites: list[CallSite] = []
    inferred = _path_to_subsystem(file)

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        api = _classify_call(node)
        if api is None:
            continue
        metric_name = _first_string_arg(node)
        name_sub = _name_to_subsystem(metric_name) if metric_name else None
        sites.append(
            CallSite(
                module=module,
                file=file,
                lineno=node.lineno,
                api=api,
                metric_name=metric_name,
                inferred_subsystem=inferred,
                name_subsystem=name_sub,
            ),
        )
    return sites


def _classify_call(node: ast.Call) -> str | None:
    """Return the metrics API name if this call records a metric, else None."""
    func = node.func
    # Attribute call: e.g. m.inc(...), get_collector().observe(...)
    if isinstance(func, ast.Attribute):
        if func.attr in _COLLECTOR_METHODS:
            return func.attr
        # Module-style call via twag.metrics module: metrics.counter(...)
        if func.attr in _MODULE_FUNCS and isinstance(func.value, ast.Name) and func.value.id in {"metrics", "m"}:
            return func.attr
        return None
    # Bare-name call: counter(...), histogram(...), timer(...)
    if isinstance(func, ast.Name) and func.id in _MODULE_FUNCS:
        return func.id
    return None


def _first_string_arg(node: ast.Call) -> str | None:
    if not node.args:
        return None
    first = node.args[0]
    if isinstance(first, ast.Constant) and isinstance(first.value, str):
        return first.value
    return None
