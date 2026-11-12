# PostgreSQL on SOC-DATABASE (VM 2)

## Purpose

SOC-DATABASE holds the fake company data for **TechStore**: departments,
employees, customers, products and orders. It accepts database
connections only from the TechStore app on SOC-APPLICATION (VM 3), logs
security-relevant activity as JSON, and runs an agent that reports
system metrics, database stats and log events to SOC-CORE (VM 4).

## Layout

| Path | What it is | Installed to |
|---|---|---|
| `sql/roles.sql` | Roles (`db_admin`, `app_user`, `soc_monitor`, `intern_readonly`) and the `techstore` database | run once with psql |
| `sql/schema.sql` | Tables, `employee_directory` view, grants, PUBLIC lockdown | run once with psql |
| `sql/seed.py` | Faker seed data (DSN from `SEED_DSN`) | run once |
| `config/soc.conf` | Network, jsonlog logging, stats | `/etc/postgresql/<ver>/main/conf.d/` |
| `config/soc_pgaudit.conf` | Optional pgaudit add-on | `/etc/postgresql/<ver>/main/conf.d/` |
| `config/pg_hba.snippet` | Allow VM 3 + localhost, reject the rest | `/etc/postgresql/<ver>/main/pg_hba.conf` |
| `agent/` | SOC agent, systemd unit, env template | `/opt/soc-agent/`, `/etc/soc-agent/` |
| `scripts/install_vm2.sh` | One-command, re-runnable install of everything below (`sudo ... all`) | run on VM 2 |
| `config/postgresql-wait-tailscale.conf` | systemd drop-in: PostgreSQL waits for tailscale0 at boot | `/etc/systemd/system/postgresql@.service.d/` |
| `scripts/simulate_attacks.sh` | Lab-only attack simulations (localhost only) | run on VM 2 |
| `docs/setup.md` | Step-by-step setup, verification, expected events per attack | |
| `docs/agent-payload.md` | What the agent sends to VM 4, and open questions | |
| `docs/test-results.md` | Rehearsal, live install, firewall and attack-simulation results | |

## Roles

| Role | Can | Cannot | Connects from |
|---|---|---|---|
| `db_admin` | own and change everything in `techstore` | superuser actions | localhost |
| `app_user` | read all tables; insert/update customers, orders, order_items; update stock and login columns | delete, truncate, DDL | VM 3 (Tailscale) |
| `soc_monitor` | `pg_monitor`: read `pg_stat_*` | read any company table | localhost (agent) |
| `intern_readonly` | read departments, products, customers, orders, `employee_directory` | read `employees` (permission denied, on purpose) | localhost |
| `soc_user` (VM 4 team) | own `soc_db`, the SOC's events and alerts | connect to `techstore` | VM 4 (Tailscale) |

## Security layers

1. `listen_addresses = 'localhost,<VM2_TS_IP>'`: never all interfaces
2. `pg_hba.conf`: only `app_user`→`techstore` from `<VM3_TS_IP>` and `soc_user`→`soc_db` from `<VM4_TS_IP>`, scram-sha-256, an explicit `reject` for everything else
3. `ufw`: TCP 5432 only from `<VM3_TS_IP>` and `<VM4_TS_IP>` on `tailscale0`
4. Least-privilege grants, with `PUBLIC` revoked on the database and schema

## Status

- **Live on SOC-DATABASE (2026-11-12):** installed with `scripts/install_vm2.sh`. techstore is seeded, soc_db (VM 4) is still connected, and soc-agent is sending events to VM 4's `/api/ingest`.
- **Attacks verified:** all six simulated attacks were detected and forwarded to VM 4, and brute force raised a DB-001 alert. See [docs/test-results.md](docs/test-results.md).
- **Not done yet:** the VM 3 app isn't deployed, so `app_user` from VM 3 is untested end to end.
- **Firewall verified:** port 5432 is reachable from VM 3 and VM 4 only. VM 1 and other tailnet devices are blocked. This needs `tailscale set --netfilter-mode=nodivert` (applied by the `firewall` phase): otherwise Tailscale's `ts-input` chain accepts tailnet traffic before ufw's rules run.
- The agent payload matches VM 4's `/api/ingest`, but the open questions in [docs/agent-payload.md](docs/agent-payload.md) need agreement from the VM 4 owner.
- The repo has no Ansible yet. Every file installs by copying it to a fixed path with placeholders, so each one can become an Ansible `template`/`copy` task later.

See [docs/setup.md](docs/setup.md) to install.
