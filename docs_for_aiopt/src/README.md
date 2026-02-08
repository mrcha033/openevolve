# src/ — Stale Copies (Do Not Use)

The files in this directory are **outdated snapshots** of the profiler parsers and fitness function.
They were placed here for documentation purposes during the initial RocksDB experiment design.

## Canonical Location

The actively maintained versions live in the main package:

| File | Canonical Path | Notes |
|------|---------------|-------|
| `bcoz_parser.py` | `openevolve/aiopt/bcoz_parser.py` | Identical to this copy |
| `bperf_parser.py` | `openevolve/aiopt/bperf_parser.py` | This copy is **missing** `generate_mutation_context()` |
| `fitness.py` | `openevolve/aiopt/fitness.py` | Minor whitespace differences only |

**Always use `openevolve/aiopt/` for imports and development.**

These copies are kept only for reference and will not be updated.
