# twag developer documentation

Reference documentation for working on twag itself. End-user installation and
usage live in the top-level [`README.md`](../README.md); this directory holds
the deeper, contributor-facing material.

## Contents

| Doc | Purpose |
|-----|---------|
| [architecture.md](./architecture.md) | High-level FETCH → PROCESS → DIGEST flow and module map |
| [database.md](./database.md) | SQLite schema reference: tables, columns, indexes, FTS triggers |
| [cli.md](./cli.md) | Full CLI command reference grouped by lifecycle |
| [web-api.md](./web-api.md) | FastAPI HTTP route reference |
| [metrics.md](./metrics.md) | Metrics emitted by each subsystem and how to read them |

These docs are derived from the current code in `twag/`. If a doc disagrees
with the source, treat the source as authoritative and update the doc.
