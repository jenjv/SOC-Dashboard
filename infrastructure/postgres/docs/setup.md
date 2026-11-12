# SOC-DATABASE (VM 2) setup

SOC-DATABASE is the team's PostgreSQL server. It holds two databases:

| Database | Owner | Used by | Managed by |
|---|---|---|---|
| `techstore` | `db_admin` | VM 3 TechStore app (`app_user`) | this folder |
| `soc_db` | `soc_user` | VM 4 SOC backend (events, alerts) | the VM 4 owner; this folder only manages its pg_hba line and firewall rule, never its data |

## Quick install (recommended)

From this folder on VM 2:

```bash
sudo VM3_TS_IP=<VM3_TS_IP> VM4_TS_IP=<VM4_TS_IP> bash scripts/install_vm2.sh all
```

- **What it does:** runs every manual step below. Each phase checks itself, and pg_hba is validated before it goes live, with an automatic rollback if anything is wrong.
- **Safe to re-run:** existing data and passwords are kept.
- **Passwords:** generated into `/etc/soc-vm2/secrets.env` (root only).
- **VM 4 blip:** PostgreSQL restarts once in the `logging` phase, so VM 4's connections drop for about a second and reconnect on their own.
- **Ingest token:** the `agent` phase asks for VM 4's ingest token. Without one, the agent runs in dry-run mode.
- **Status check:** `sudo bash scripts/install_vm2.sh check` prints a read-only status at any time.

The manual steps below explain what the script does, and are there for
debugging. Every command runs **on SOC-DATABASE** unless it says
otherwise. Fill in the placeholders as you go, and never commit the real
values.

| Placeholder | Meaning | How to find it |
|---|---|---|
| `<PG_VERSION>` | Installed PostgreSQL major version | `ls /etc/postgresql` |
| `<VM2_TS_IP>` | SOC-DATABASE Tailscale IP | `tailscale ip -4` on VM 2 |
| `<VM3_TS_IP>` | SOC-APPLICATION Tailscale IP | `tailscale status` |
| `<VM4_TS_IP>` | SOC-CORE Tailscale IP | `tailscale status` |
| `<INGEST_TOKEN>` | `INGEST_TOKEN` from VM 4's `.env` | ask the VM 4 owner |

Generate one strong password per role and keep them in a password
manager, not in the repo:

```bash
openssl rand -base64 24   # run 4 times: db_admin, app_user, soc_monitor, intern_readonly
```

## 1. Get the files onto VM 2

```bash
git clone https://github.com/jenjv/SOC-Dashboard.git ~/SOC-Dashboard
cd ~/SOC-Dashboard && git checkout vm2-database   # until it is merged
cd infrastructure/postgres
```

## 2. Install PostgreSQL

Ubuntu 26.04 ships a newer PostgreSQL than 16. These files work with 16
and later (jsonlog needs 15+), so use the version the OS provides.

```bash
sudo apt update
sudo apt install -y postgresql postgresql-contrib python3-venv
ls /etc/postgresql                     # -> <PG_VERSION>
psql --version
grep -n "^include_dir" /etc/postgresql/<PG_VERSION>/main/postgresql.conf   # expect 'conf.d'
```

## 3. Logging directory

```bash
sudo install -d -o postgres -g adm -m 2750 /var/log/postgresql/soc
```

The setgid bit (`2`) keeps new log files in the `adm` group, which the
SOC agent belongs to.

## 4. PostgreSQL configuration

```bash
PGV=<PG_VERSION>
sudo cp config/soc.conf /etc/postgresql/$PGV/main/conf.d/soc.conf
sudo sed -i "s/<VM2_TS_IP>/$(tailscale ip -4)/" /etc/postgresql/$PGV/main/conf.d/soc.conf
# ALTER SYSTEM settings (postgresql.auto.conf) override conf.d. Clear the old '*'
sudo -u postgres psql -c "ALTER SYSTEM RESET listen_addresses;"
# Wait for Tailscale at boot so PostgreSQL can bind the Tailscale IP
sudo install -d /etc/systemd/system/postgresql@.service.d
sudo cp config/postgresql-wait-tailscale.conf /etc/systemd/system/postgresql@.service.d/10-wait-tailscale.conf
sudo systemctl daemon-reload

sudo cp /etc/postgresql/$PGV/main/pg_hba.conf /etc/postgresql/$PGV/main/pg_hba.conf.orig
sudo cp config/pg_hba.snippet /etc/postgresql/$PGV/main/pg_hba.conf
sudo sed -i -e "s/<VM3_TS_IP>/<real VM 3 IP>/" -e "s/<VM4_TS_IP>/<real VM 4 IP>/" /etc/postgresql/$PGV/main/pg_hba.conf
sudo chown postgres:postgres /etc/postgresql/$PGV/main/pg_hba.conf
sudo chmod 640 /etc/postgresql/$PGV/main/pg_hba.conf

sudo systemctl restart postgresql
```

Check the result:

```bash
sudo -u postgres psql -c "SELECT * FROM pg_hba_file_rules WHERE error IS NOT NULL;"   # expect 0 rows
sudo -u postgres psql -c "SHOW listen_addresses; SHOW log_destination; SHOW log_connections;"
sudo ss -ltnp | grep 5432        # 127.0.0.1:5432 and <VM2_TS_IP>:5432 only, never 0.0.0.0
ls -l /var/log/postgresql/soc/   # soc-YYYY-MM-DD.json, group adm
```

If PostgreSQL won't start, `sudo journalctl -u postgresql@$PGV-main -n 50`
usually shows a typo or a missing log directory.

## 5. Firewall (ufw): second layer behind pg_hba

```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow OpenSSH                       # keep SSH working before enabling ufw
sudo ufw allow 41641/udp comment 'Tailscale direct connections'
sudo ufw allow in on tailscale0 from <VM3_TS_IP> to any port 5432 proto tcp comment 'TechStore app (VM 3)'
sudo ufw allow in on tailscale0 from <VM4_TS_IP> to any port 5432 proto tcp comment 'SOC backend (VM 4)'
sudo ufw deny 5432/tcp comment 'PostgreSQL: everyone else'
sudo ufw enable
sudo ufw status numbered
# Tailscale's ts-input chain otherwise accepts all tailnet traffic before ufw runs
sudo tailscale set --netfilter-mode=nodivert
sudo iptables -S INPUT | head -3      # first rule must be ufw-..., not ts-input
```

Check from **VM 3**, and from your PC for the negative test:

```bash
# On SOC-APPLICATION: should connect
psql "host=<VM2_TS_IP> dbname=techstore user=app_user" -c "SELECT current_user;"
# From any other machine: should time out (ufw) or be rejected (pg_hba)
psql "host=<VM2_TS_IP> dbname=techstore user=app_user connect_timeout=5" -c "SELECT 1;"
```

## 6. Roles, schema and seed data

```bash
read -rs -p "db_admin password: " DB_ADMIN_PASSWORD; echo
read -rs -p "app_user password: " APP_USER_PASSWORD; echo
read -rs -p "soc_monitor password: " SOC_MONITOR_PASSWORD; echo
read -rs -p "intern_readonly password: " INTERN_PASSWORD; echo

sudo -u postgres psql -v ON_ERROR_STOP=1 \
  -v db_admin_password="$DB_ADMIN_PASSWORD" \
  -v app_user_password="$APP_USER_PASSWORD" \
  -v soc_monitor_password="$SOC_MONITOR_PASSWORD" \
  -v intern_password="$INTERN_PASSWORD" \
  -f sql/roles.sql

sudo -u postgres psql -v ON_ERROR_STOP=1 -d techstore -f sql/schema.sql   # also creates monitoring.pg_stat_statements

python3 -m venv ~/seed-venv && ~/seed-venv/bin/pip install -r sql/requirements.txt
read -rs -p "Shared employee login password (for the VM 3 app): " SEED_EMPLOYEE_PASSWORD; echo
SEED_DSN="host=127.0.0.1 dbname=techstore user=db_admin password=$DB_ADMIN_PASSWORD" \
SEED_EMPLOYEE_PASSWORD="$SEED_EMPLOYEE_PASSWORD" \
  ~/seed-venv/bin/python sql/seed.py
```

Check that the permissions behave as intended:

```bash
export PGHOST=127.0.0.1 PGDATABASE=techstore
PGPASSWORD="$INTERN_PASSWORD" psql -U intern_readonly -c "SELECT count(*) FROM customers;"    # works
PGPASSWORD="$INTERN_PASSWORD" psql -U intern_readonly -c "SELECT * FROM employees LIMIT 1;"   # permission denied
PGPASSWORD="$APP_USER_PASSWORD" psql -U app_user -c "DELETE FROM orders WHERE false;"          # permission denied
PGPASSWORD="$SOC_MONITOR_PASSWORD" psql -U soc_monitor -c "SELECT count(*) FROM pg_stat_activity;"  # works
PGPASSWORD="$SOC_MONITOR_PASSWORD" psql -U soc_monitor -c "SELECT * FROM customers LIMIT 1;"   # permission denied
unset PGHOST PGDATABASE
```

For the VM 3 owner, app_user can:

- **read** every company table and `employee_directory`
- **insert/update** `customers`, `orders` and `order_items`
- **update** only `products.stock`, and `employees.failed_login_count` / `employees.last_login_at`
- **not** delete, truncate or change the schema

Employee logins: `employees.username` plus `employees.password_hash`
(bcrypt, `$2b$12$...`), so verify with `bcrypt.checkpw()`.

## 7. SOC agent

```bash
sudo useradd --system --no-create-home --shell /usr/sbin/nologin soc-agent
sudo install -d -m 0755 /opt/soc-agent
sudo install -m 0644 agent/agent.py agent/requirements.txt /opt/soc-agent/
sudo python3 -m venv /opt/soc-agent/venv
sudo /opt/soc-agent/venv/bin/pip install -r /opt/soc-agent/requirements.txt

sudo install -d -m 0750 -o root -g soc-agent /etc/soc-agent
sudo install -m 0640 -o root -g soc-agent agent/soc-agent.env.example /etc/soc-agent/soc-agent.env
sudo nano /etc/soc-agent/soc-agent.env      # fill in every <PLACEHOLDER>
```

Dry run first. This prints events to the terminal instead of sending them:

```bash
sudo systemd-run --pty --uid=soc-agent -p SupplementaryGroups=adm \
  -p EnvironmentFile=/etc/soc-agent/soc-agent.env -E SOC_DRY_RUN=true \
  -E SOC_STATE_FILE=/tmp/soc-agent-test.json \
  /opt/soc-agent/venv/bin/python /opt/soc-agent/agent.py
# Ctrl+C after you see agent_started, system_metrics and database_stats
```

Then run it for real:

```bash
sudo install -m 0644 agent/soc-agent.service /etc/systemd/system/soc-agent.service
sudo systemctl daemon-reload
sudo systemctl enable --now soc-agent
systemctl status soc-agent
journalctl -u soc-agent -f        # no "401" or "cannot reach VM 4" warnings
```

From any machine on the tailnet:

```bash
curl -s "http://<VM4_TS_IP>:8000/api/events?source_machine=SOC-DATABASE&limit=5"
```

## 8. Simulated attacks and expected events

Run these **on VM 2 only**:

```bash
export INTERN_PASSWORD DB_ADMIN_PASSWORD   # from step 6
export VM2_TS_IP="$(tailscale ip -4)"
chmod +x scripts/simulate_attacks.sh
scripts/simulate_attacks.sh all            # or: brute denied bulk slow ddl reject
```

| Test | PostgreSQL jsonlog (`error_severity` / `state_code` / `message`) | SOC event (`event_type` / `severity`) | VM 4 alert |
|---|---|---|---|
| `brute` | `FATAL` / `28P01` / `password authentication failed for user "app_user"` (6×), and the same for `"admin"` (3×) | `database_authentication_failure` / high, `source_ip` 127.0.0.1, `username` app_user / admin | **DB-001** after 3 failures from one IP within 5 min |
| `denied` | `ERROR` / `42501` / `permission denied for table employees`, `statement` holds the query | `database_permission_denied` / high, `username` intern_readonly | none yet (proposed rule DB-002) |
| `bulk` | none (fast queries aren't logged) | `database_bulk_read` / medium, `table` customers/orders, `rows_read` ≥ 1000, top reader intern_readonly | none yet (proposed DB-003) |
| `slow` | `LOG` / `duration: 8xx ms  statement: SELECT pg_sleep(0.8)` | `database_slow_query` / medium, `duration_ms` | none |
| `ddl` | `LOG` / `statement: CREATE TABLE soc_sim_tmp (id int); DROP TABLE soc_sim_tmp;` (one line, sent as one statement) | `database_ddl` / medium, `username` db_admin | none |
| `reject` | `FATAL` / `28000` / `pg_hba.conf rejects connection for host "<VM2_TS_IP>", user "app_user" ...` | `database_access_rejected` / high, `source_ip` <VM2_TS_IP> | none yet |
| every test | `LOG` / `connection authorized: ...` and `disconnection: ...` for intern_readonly/db_admin | `database_connection` / `database_disconnection` / low | none |

Watch the raw log while testing:

```bash
sudo tail -f /var/log/postgresql/soc/soc-$(date -u +%F).json | \
  python3 -c 'import sys,json; [print(r.get("error_severity"), r.get("state_code"), r.get("user"), r.get("remote_host"), r.get("message")) for r in map(json.loads, sys.stdin)]'
```

## 9. Optional: pgaudit

pgaudit records successful reads of `employees`, not only denied ones.

```bash
sudo apt install -y postgresql-$PGV-pgaudit
sudo cp config/soc_pgaudit.conf /etc/postgresql/$PGV/main/conf.d/soc_pgaudit.conf
sudo systemctl restart postgresql
sudo -u postgres psql -d techstore -c "CREATE EXTENSION IF NOT EXISTS pgaudit;"
sudo -u postgres psql -d techstore -c "CREATE ROLE auditor NOLOGIN; GRANT SELECT ON employees TO auditor;"
```

Every `SELECT ... FROM employees` (for example by app_user at login)
then logs `AUDIT: OBJECT,...,READ,SELECT,TABLE,public.employees,...`.
The agent forwards that as `database_audit` / medium.

## Troubleshooting

| Symptom | Check |
|---|---|
| Agent logs `HTTP 401` | `SOC_INGEST_TOKEN` must equal VM 4's `INGEST_TOKEN` |
| Agent logs `cannot reach VM 4` | Is VM 4's uvicorn running with `--host 0.0.0.0` on port 8000? Does `curl http://<VM4_TS_IP>:8000/health` work? |
| `database_unreachable` events | soc_monitor password in the env file; pg_hba line for 127.0.0.1 |
| No log events | `ls -l /var/log/postgresql/soc`: files must be group `adm`, mode 640 |
| VM 3 can't connect | `sudo ufw status`, `pg_hba_file_rules`, and `listen_addresses` includes the Tailscale IP. Tailscale must be up before PostgreSQL starts; if not, `sudo systemctl restart postgresql` |
