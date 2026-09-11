# Postgres temporarily DISABLED on dev

Date: 2026-09-11
Scope: `power_core` dev branch only. Prod untouched.
Flag: `PG_ENABLED=false` (default). No Postgres work is lost — only gated.

## Why
Dev must run as before (Dropbox sync, pipelines, Cloud Run smoke) without a
live Postgres. Previously `DropboxAuth.__init__` called `connect_to_db()` on
every Dropbox flow (5s stall when DB unreachable) and `psycopg` was a hard
import-time dependency (`no pq wrapper` risk).

## What was changed
| File | Change |
|------|--------|
| `power_core/power_core/database/db_conect.py` | Optional `psycopg` import (`None` fallback); new `is_pg_enabled()` gate; `connect_to_db()` returns `None` immediately when disabled or driver missing; `load_stream_to_postgres()` returns `0` when disabled; removed `print("HH", host)` debug; broad `except Exception` so `psycopg=None` never raises at handler level |
| `power_core/power_core/dropbox_usage/utils.py` | Removed top-level `from power_core.database.db_conect import connect_to_db`; new `_maybe_preflight_db()` — lazy import, called only when `PG_ENABLED=true`, never raises |
| `power_core/power_core/workshop/csv_to_base.py` | Removed top-level DB import; `process_data()` returns `0` early when disabled; pure `parse_memory_csv_stream()` stays active |
| `power_core/tests/test_db_conect.py` | Existing DB tests now set `PG_ENABLED=true`; added `test_returns_none_when_pg_disabled` (driver must not be called, loader returns `0`) |
| `local_config.dev.json` | Added `"PG_ENABLED": "false"` |
| `power_core/keys.env.dev` | Added `PG_ENABLED=false` with comment |

Placeholders `stage_06ver2` / `stage_07ver2` in `workers.py` left untouched
(docstring-only, not called by `run_full_pipeline` / `run_repair_flow`).

## Behavior when disabled
- `connect_to_db()` → `None` (debug log, no network, no driver needed).
- `load_stream_to_postgres()` → `0` (info log, no network).
- `process_data()` → `0` (info log, CSV parsing still importable/testable).
- `DropboxAuth()` → no DB preflight, no 5s stall.
- App boots even if `psycopg` is not installed.

## Verify dev still works
```bash
cd /home/stas/projects/main/BigBikeData/power_core
.venv/bin/python -m pytest tests/ -q
# expect 51 passed (50 old + 1 new disabled-gate test)

PG_ENABLED=false .venv/bin/python -c \
  "from power_core.database.db_conect import connect_to_db, load_stream_to_postgres; \
   assert connect_to_db() is None; \
   assert load_stream_to_postgres(iter([])) == 0; print('PG disabled OK')"
```

## How to re-enable later
1. Set `PG_ENABLED=true` in `local_config.dev.json` + `power_core/keys.env.dev`
   (and Cloud Run `--set-env-vars` / secrets for deployed rev).
2. Provide `PG_HOST`, `PG_PORT`, `PG_DATABASE`, `PG_USER`, `PG_PASS`.
3. Ensure driver present: either `psycopg[binary]` in requirements or
   `libpq-dev` (build) + `libpq5` (runtime) in `Dockerfile` — dev image
   `00019` already has the apt combo.
4. Wire `stage_06ver2` / `stage_07ver2` in `workers.py` to `process_data()`.
5. Run tests + Dropbox e2e (`wahoo_0001.fit` → `completed`) with DB up.
