# SOC-DATABASE (VM 2): test results

## 1. Pre-deployment rehearsal (local Docker)

These ran before anything touched the live VM:

- **Containers:** Ubuntu 26.04 with PostgreSQL 18.6, built to match the live VM. That means an existing `soc_db` owned by `soc_user`, `listen_addresses='*'` set via ALTER SYSTEM, and a pg_hba line for VM 4.
- **Stand-in VM 4:** queried `soc_db` every second during the install. It stayed connected throughout, except for a ~1 s gap at each PostgreSQL restart.
- **Outsider:** a third container was rejected by pg_hba, and VM 4 was rejected when it tried `techstore`.
- **Role permissions:** 19 allow/deny checks all passed. For example, `intern_readonly` is denied `employees`, `app_user` can't DELETE or change salaries, and `soc_monitor` can't read company data.
- **Agent output:** every event type ran through VM 4's own `soc.processing.normalizer` and came out with the correct `event_type`, `severity`, `source_ip` and `username`.
- **Re-running** `install_vm2.sh` kept the data and passwords.

### Bugs found and fixed

| Bug | Fix |
|---|---|
| `soc_monitor` couldn't read `pg_stat_statements`, and re-running `schema.sql` revoked access to it | moved the extension to its own `monitoring` schema |
| The agent DSN (contains spaces) broke when the env file was sourced from a shell | quoted the value |
| Failed logins were logged twice with `ssl = on` (libpq retries without SSL) | the attack script makes one plain attempt each |
| On the live VM, `postgres` couldn't read SQL files in a mode-750 home directory | the install script pipes SQL in on stdin |
| A pg_file_settings check stopped on "setting could not be applied", which only means "needs a restart" | that message is ignored; real errors still stop the install |

## 2. Live install (2026-11-11/12)

**Survey before the install** found:

- PostgreSQL 18.6 listening on `0.0.0.0` (`listen_addresses='*'` via ALTER SYSTEM)
- ufw inactive, and default logging
- VM 4's `soc_db` already in use by `soc_user`

**After the install** (`install_vm2.sh all`):

| Check | Result |
|---|---|
| `listen_addresses` | `localhost,<VM2_TS_IP>` only |
| Logging | jsonlog, connections on, `log_statement = ddl`, slow queries > 500 ms |
| pg_hba remote rules | `techstore/app_user` from VM 3, `soc_db/soc_user` from VM 4, reject all else |
| techstore | 80 employees, 5000 customers, 4000 orders |
| VM 4 backend | reconnected to `soc_db`; `/api/stats` OK |
| soc-agent | running, sending to VM 4 with the ingest token |

### Firewall

Tailscale's `ts-input` chain was first in INPUT and accepted all tailnet traffic before ufw ran. After `tailscale set --netfilter-mode=nodivert`, a TCP test to port 5432 gave:

| From | Result |
|---|---|
| VM 3 (SOC-APPLICATION) | open |
| VM 4 (SOC-CORE) | open |
| VM 1 (SOC-NGINX) | blocked |
| Other tailnet devices | blocked |

SSH and VM 4's sessions were unaffected.

## 3. Live attack simulation (2026-11-12, `simulate_attacks.sh all` on VM 2)

| Test | Events received by VM 4 (`/api/events?source_machine=SOC-DATABASE`) | VM 4 alert |
|---|---|---|
| brute | 6× `database_authentication_failure` (app_user) + 3× (admin), high, from 127.0.0.1 | **DB-001** "Repeated Database Authentication Failures" |
| denied | 1× `database_permission_denied`, high, intern_readonly | none (DB-002 proposed) |
| bulk | `database_bulk_read`, medium: 15000 rows from customers, 12000 from orders, top reader intern_readonly | none (DB-003 proposed) |
| slow | 1× `database_slow_query`, medium | none |
| ddl | 1× `database_ddl`, medium, db_admin | none |
| reject | 1× `database_access_rejected`, high, from VM 2's own Tailscale IP | none (DB-004 proposed) |
| all | 10 connection + 10 disconnection events (low) for intern_readonly/db_admin | none |

Totals on VM 4 went from 41 events / 3 alerts to 90 events / 4 alerts. The
3 alerts that existed before were VM 4's own test data.

## 4. Not yet tested

- **The VM 3 TechStore app connecting as `app_user`.** The app isn't deployed on SOC-APPLICATION yet, although port 5432 is reachable from VM 3.
- **Behaviour after a reboot.** The Tailscale wait drop-in and the netfilter setting are persisted, but VM 2 hasn't been rebooted to confirm.
- **pgaudit (optional).** Not installed.
