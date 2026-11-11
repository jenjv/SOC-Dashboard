-- =====================================================================
-- SOC-DATABASE (VM 2): roles and database for the TechStore company DB
-- =====================================================================
-- Run as the postgres superuser on VM 2. Passwords are passed in as psql
-- variables, so none are stored in this file:
--
--   sudo -u postgres psql -v ON_ERROR_STOP=1 \
--     -v db_admin_password="$DB_ADMIN_PASSWORD" \
--     -v app_user_password="$APP_USER_PASSWORD" \
--     -v soc_monitor_password="$SOC_MONITOR_PASSWORD" \
--     -v intern_password="$INTERN_PASSWORD" \
--     -f roles.sql
--
-- Safe to re-run: it creates missing roles and resets the passwords.
-- =====================================================================

-- log_statement = 'ddl' would otherwise write each ALTER ROLE ... PASSWORD
-- statement, plaintext password included, into the PostgreSQL log, which
-- the SOC agent then forwards to VM 4. Turn statement logging off for this
-- session only (requires superuser).
SET log_statement = 'none';
SET log_min_duration_statement = -1;
SET password_encryption = 'scram-sha-256';

-- ---------------------------------------------------------------------
-- Roles
-- ---------------------------------------------------------------------
-- db_admin        owns the database and every object in it. Local only.
-- app_user        the VM 3 TechStore app. Least privilege, no DELETE/DDL.
-- soc_monitor     used by the SOC agent. Reads pg_stat_* only, no data.
-- intern_readonly reads some business tables but is deliberately denied
--                 the employees table (for unauthorized-access tests).
SELECT format('CREATE ROLE %I LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE', r)
FROM unnest(ARRAY['db_admin', 'app_user', 'soc_monitor', 'intern_readonly']) AS r
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r)
\gexec

ALTER ROLE db_admin        LOGIN PASSWORD :'db_admin_password';
ALTER ROLE app_user        LOGIN PASSWORD :'app_user_password'    CONNECTION LIMIT 50;
ALTER ROLE soc_monitor     LOGIN PASSWORD :'soc_monitor_password' CONNECTION LIMIT 3;
ALTER ROLE intern_readonly LOGIN PASSWORD :'intern_password'      CONNECTION LIMIT 5;

-- pg_monitor lets soc_monitor read every pg_stat_* view (including other
-- sessions' queries in pg_stat_activity) without reading table data.
GRANT pg_monitor TO soc_monitor;

-- Stop a runaway intern query from hogging the box during bulk-read tests.
ALTER ROLE intern_readonly SET statement_timeout = '30s';

-- ---------------------------------------------------------------------
-- Database
-- ---------------------------------------------------------------------
SELECT 'CREATE DATABASE techstore OWNER db_admin ENCODING ''UTF8'' TEMPLATE template0'
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'techstore')
\gexec

-- Nobody connects to techstore unless granted below.
REVOKE ALL ON DATABASE techstore FROM PUBLIC;
GRANT CONNECT ON DATABASE techstore TO db_admin, app_user, soc_monitor, intern_readonly;
GRANT TEMPORARY ON DATABASE techstore TO db_admin;
