#!/usr/bin/env bash
# =====================================================================
# SOC-DATABASE (VM 2): simulated attacks for SOC detection testing
# =====================================================================
# LAB USE ONLY. Run this ON VM 2 itself. It only connects to the local
# PostgreSQL (127.0.0.1), plus VM 2's own Tailscale IP for the "reject"
# test, and refuses any address that isn't on this machine.
#
# Usage:
#   export INTERN_PASSWORD='...'        # needed for denied, bulk, slow
#   export DB_ADMIN_PASSWORD='...'      # only for the ddl test
#   export VM2_TS_IP="$(tailscale ip -4)"   # only for the reject test
#   ./simulate_attacks.sh [all|brute|denied|bulk|slow|ddl|reject] ...
#
# docs/setup.md lists the PostgreSQL log line and SOC event that each
# test should produce.
# =====================================================================
set -euo pipefail

DB="${PGDATABASE_NAME:-techstore}"
LOCAL_HOST="127.0.0.1"
PORT="${PGPORT:-5432}"
BRUTE_ATTEMPTS="${BRUTE_ATTEMPTS:-6}"
BULK_REPEAT="${BULK_REPEAT:-3}"
export PGCONNECT_TIMEOUT=5

say()  { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
note() { printf '    %s\n' "$*"; }
die()  { printf '\033[1;31merror:\033[0m %s\n' "$*" >&2; exit 1; }

command -v psql >/dev/null || die "psql not found (sudo apt install postgresql-client)"

# Never print passwords; pass them only through the environment of psql.
run_psql() {  # run_psql <host> <user> <password> <sql>
  PGPASSWORD="$3" psql -X -w -q -h "$1" -p "$PORT" -U "$2" -d "$DB" \
    -v ON_ERROR_STOP=1 -c "$4"
}

require() { [[ -n "${!1:-}" ]] || die "set $1 first (see the header of this script)"; }

is_local_address() {  # true only if the IP is assigned to this machine
  ip -o addr show | awk '{print $4}' | cut -d/ -f1 | grep -qxF "$1"
}

test_brute() {
  say "Brute force: $BRUTE_ATTEMPTS wrong passwords for app_user, 3 for nonexistent 'admin'"
  for i in $(seq 1 "$BRUTE_ATTEMPTS"); do
    run_psql "$LOCAL_HOST" app_user "wrong-password-$i" 'SELECT 1' >/dev/null 2>&1 \
      && note "attempt $i unexpectedly SUCCEEDED" || note "attempt $i rejected (expected)"
  done
  for i in 1 2 3; do
    run_psql "$LOCAL_HOST" admin "admin$i" 'SELECT 1' >/dev/null 2>&1 || note "admin attempt $i rejected (expected)"
  done
}

test_denied() {
  require INTERN_PASSWORD
  say "Unauthorized access: intern_readonly tries to read employees"
  if run_psql "$LOCAL_HOST" intern_readonly "$INTERN_PASSWORD" \
       'SELECT first_name, last_name, salary, ssn_last4 FROM employees LIMIT 5' 2>&1; then
    die "intern_readonly COULD read employees; the grants in schema.sql are not applied"
  fi
  note "permission denied (expected). The allowed directory view still works:"
  run_psql "$LOCAL_HOST" intern_readonly "$INTERN_PASSWORD" 'SELECT count(*) AS directory_rows FROM employee_directory'
}

test_bulk() {
  require INTERN_PASSWORD
  say "Bulk read: intern_readonly dumps customers and orders $BULK_REPEAT times"
  for i in $(seq 1 "$BULK_REPEAT"); do
    run_psql "$LOCAL_HOST" intern_readonly "$INTERN_PASSWORD" 'SELECT * FROM customers' >/dev/null
    run_psql "$LOCAL_HOST" intern_readonly "$INTERN_PASSWORD" 'SELECT * FROM orders' >/dev/null
    note "pass $i done"
  done
  note "The agent reports database_bulk_read on its next stats sample (up to SOC_METRICS_INTERVAL seconds)."
}

test_slow() {
  require INTERN_PASSWORD
  say "Slow query: a 0.8 s query (log_min_duration_statement = 500 ms)"
  run_psql "$LOCAL_HOST" intern_readonly "$INTERN_PASSWORD" 'SELECT pg_sleep(0.8)' >/dev/null
  note "done"
}

test_ddl() {
  require DB_ADMIN_PASSWORD
  say "DDL: db_admin creates and drops a scratch table"
  run_psql "$LOCAL_HOST" db_admin "$DB_ADMIN_PASSWORD" \
    'CREATE TABLE soc_sim_tmp (id int); DROP TABLE soc_sim_tmp;'
  note "done"
}

test_reject() {
  require VM2_TS_IP
  is_local_address "$VM2_TS_IP" || die "VM2_TS_IP=$VM2_TS_IP is not an address of this machine; refusing"
  say "pg_hba reject: connect to VM 2's own Tailscale IP ($VM2_TS_IP), which pg_hba only allows from VM 3"
  run_psql "$VM2_TS_IP" app_user "not-a-real-password" 'SELECT 1' 2>&1 \
    && die "connection was ACCEPTED; check pg_hba.conf" || note "rejected (expected)"
}

main() {
  local tests=("$@")
  [[ ${#tests[@]} -eq 0 ]] && tests=(all)
  if [[ " ${tests[*]} " == *" all "* ]]; then
    tests=(brute denied bulk slow)
    [[ -n "${DB_ADMIN_PASSWORD:-}" ]] && tests+=(ddl)
    [[ -n "${VM2_TS_IP:-}" ]] && tests+=(reject)
  fi
  printf 'Simulated attacks against PostgreSQL on THIS machine (%s), database %s: %s\n' \
    "$(hostname)" "$DB" "${tests[*]}"
  for t in "${tests[@]}"; do
    case "$t" in
      brute|denied|bulk|slow|ddl|reject) "test_$t" ;;
      *) die "unknown test '$t' (use all, brute, denied, bulk, slow, ddl, reject)" ;;
    esac
  done
  say "Done. Check: sudo tail -n 30 /var/log/postgresql/soc/soc-\$(date -u +%F).json"
  note "and the SOC dashboard / GET /api/events?source_machine=SOC-DATABASE on VM 4"
}

main "$@"
