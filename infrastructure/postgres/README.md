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
| `scripts/simulate_attacks.sh` | Lab-only attack simulations (localhost only) | run on VM 2 |
| `docs/setup.md` | Step-by-step setup, verification, expected events per attack | |
| `docs/agent-payload.md` | What the agent sends to VM 4, and open questions | |

## Roles

| Role | Can | Cannot | Connects from |
|---|---|---|---|
| `db_admin` | own and change everything in `techstore` | superuser actions | localhost |
| `app_user` | read all tables; insert/update customers, orders, order_items; update stock and login columns | delete, truncate, DDL | VM 3 (Tailscale) |
| `soc_monitor` | `pg_monitor`: read `pg_stat_*` | read any company table | localhost (agent) |
| `intern_readonly` | read departments, products, customers, orders, `employee_directory` | read `employees` (permission denied, on purpose) | localhost |

## Security layers

1. `listen_addresses = 'localhost,<VM2_TS_IP>'`: never all interfaces
2. `pg_hba.conf`: only `app_user` from `<VM3_TS_IP>`, scram-sha-256, an explicit `reject` for everything else
3. `ufw`: TCP 5432 only from `<VM3_TS_IP>` on `tailscale0`
4. Least-privilege grants, with `PUBLIC` revoked on the database and schema

## Status

- Written and tested locally. Not yet applied to the live VM.
- The agent payload matches VM 4's `/api/ingest`, but the open questions in [docs/agent-payload.md](docs/agent-payload.md) need agreement from the VM 4 owner.
- The repo has no Ansible yet. Every file installs by copying it to a fixed path with placeholders, so each one can become an Ansible `template`/`copy` task later.

See [docs/setup.md](docs/setup.md) to install.
