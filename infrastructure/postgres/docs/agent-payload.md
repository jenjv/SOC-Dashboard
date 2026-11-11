# SOC-DATABASE agent payload

> **Needs team agreement.** This document describes what the VM 2 agent
> sends today, matched to the VM 4 code on `main` (`soc/backend/main.py`,
> `soc/processing/`). The open questions at the bottom need decisions from
> the VM 4 owner.

## Transport

| | |
|---|---|
| Endpoint | `POST http://<VM4_TS_IP>:8000/api/ingest` |
| Auth | `X-Ingest-Token: <INGEST_TOKEN>` (VM 4's `.env`) |
| Body | JSON **array** of event objects, up to 100 per request |
| Retries | Exponential backoff up to 60 s. Up to 5000 events are queued in memory while VM 4 is down. A batch that gets a 4xx other than 401 is dropped. |

## Event fields

Every event has:

| Field | Example | Notes |
|---|---|---|
| `timestamp` | `2026-11-11T18:22:10.123000+00:00` | ISO 8601 in UTC; the PostgreSQL log time for log events |
| `source_machine` | `SOC-DATABASE` | VM 1 uses `SOC-NGINX` |
| `service` | `postgresql` | |
| `event_type` | `database_authentication_failure` | see the table below |
| `severity` | `low` / `medium` / `high` / `critical` | VM 4 stats count these four |
| `description` | `PostgreSQL FATAL: password authentication failed ... (user=admin db=techstore from=127.0.0.1)` | at most 1000 characters |
| `agent`, `agent_version` | `soc-agent-vm2`, `1.0.0` | |

Log events also have `source_ip`, `source_port`, `username`, `database`,
`application_name`, `pg_severity`, `sqlstate`, `pg_message`, `pg_detail`,
`statement`, `session_id` and `pid`. Missing values are left out.

VM 4 maps `source_ip`, `username` and `description` into columns, and
stores the whole object in `events.raw_log`.

**The agent never sends `message`, `log` or `msg` keys.** VM 4's
`parse_log()` re-parses any of those fields and merges the result over
the record. The pieces it extracts (`source_ip`, `description`) would
overwrite the agent's values. That's why the PostgreSQL text is in
`pg_message`.

## Event types

| `event_type` | Severity | Source | Trigger |
|---|---|---|---|
| `database_authentication_failure` | high | log | SQLSTATE 28P01: wrong password or unknown role |
| `database_access_rejected` | high (medium for 3D000) | log | 28000 pg_hba reject or no entry; 3D000 unknown database |
| `database_permission_denied` | high | log | 42501 insufficient privilege |
| `database_query_canceled` | medium | log | 57014 statement timeout |
| `database_too_many_connections` | high | log | 53300 |
| `database_deadlock` | medium | log | 40P01 |
| `database_error` | medium (ERROR) / high (FATAL) / critical (PANIC) | log | any other error |
| `database_ddl` | medium | log | `log_statement = 'ddl'` |
| `database_slow_query` | medium | log | above 500 ms; includes `duration_ms` |
| `database_service_state` | medium | log | server started, stopped or crashed |
| `database_audit` | low / medium (employees) | log | pgaudit `AUDIT:` lines (optional) |
| `database_connection` / `database_disconnection` | low | log | any user except `SOC_MONITOR_USERS` |
| `database_bulk_read` | medium | pg_stat | rows read from one sensitive table in one interval ≥ `SOC_BULK_READ_ROWS`; includes `table`, `rows_read`, `top_readers` |
| `database_unexpected_client` | high | pg_stat | a session from an IP not in `SOC_ALLOWED_CLIENT_IPS` |
| `database_unreachable` / `database_recovered` | high / low | agent | soc_monitor cannot query, or can again |
| `database_stats` | low | pg_stat | every interval: `stats` object with connections by user/state, commit/rollback/tuple deltas, deadlocks, cache hit ratio |
| `system_metrics` | low | psutil | every interval; see below |
| `system_resource_warning` | medium | psutil | CPU, RAM or a disk ≥ `SOC_RESOURCE_WARN_PERCENT` |
| `database_service_down` | critical | psutil | no `postgres` processes running |
| `agent_started` / `agent_stopped` | low | agent | |

Metric fields (top level on `system_metrics`): `cpu_percent`,
`cpu_count`, `load_1m`/`load_5m`/`load_15m`, `memory_percent`,
`memory_used_mb`, `memory_total_mb`, `swap_percent`, `disk_root_percent`,
`disk_pgdata_percent`, `disk_pgdata_free_gb`, `net_rx_bytes_per_sec`,
`net_tx_bytes_per_sec`, `net_rx_bytes_total`, `net_tx_bytes_total`,
`postgres_process_count`, `uptime_seconds`.

## Open questions for VM 4 (SOC-CORE)

0. **soc_db lives on VM 2.** The SOC backend's `DATABASE_URL` points at
   `soc_db` on SOC-DATABASE, as `soc_user` from VM 4. VM 2's pg_hba and
   firewall allow exactly that. `soc_user`'s routine connections are not
   reported back to the SOC (failed logins and errors still are), so the
   backend doesn't flood the dashboard with reports about itself. Don't
   point the backend at `techstore`; pg_hba rejects it.

1. **Fluent Bit vs. Python agent.** `soc/collection/README.md` plans
   Fluent Bit on every VM. VM 2 uses a Python agent because it also needs
   psutil metrics and `pg_stat_*` queries, which Fluent Bit can't do. Is
   that OK?
2. **DB-001 can never fire on raw PostgreSQL logs.** If PostgreSQL jsonlog
   lines were forwarded unchanged (for example by Fluent Bit), the client
   IP is in `remote_host`, which VM 4 never reads. So `source_ip` stays
   NULL, and DB-001 skips any event without an IP. The VM 2 agent avoids
   this by sending `source_ip`. A one-line fallback in `normalizer.py`
   (`data.get("source_ip") or data.get("remote_host")`) would also fix it.
3. **Metrics storage.** Metrics are currently sent as low-severity
   `system_metrics` events: one row every 30 s in `events`. A dedicated
   `POST /api/metrics` endpoint and `metrics` table would keep the events
   table for security data and make CPU/RAM charts easy. Proposed body:
   the same fields as above plus `source_machine` and `timestamp`.
4. **Proposed detection rules** that use VM 2 events:
   - DB-002: any `database_permission_denied` on `employees` → high
   - DB-003: `database_bulk_read` → medium; high if the role is not `app_user`
   - DB-004: `database_access_rejected` or `database_unexpected_client` → high
5. **Metrics events and `/api/stats`:** severity `low` events don't
   create alerts, but they count toward `total_events`. Is that fine?
