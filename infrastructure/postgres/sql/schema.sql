-- =====================================================================
-- SOC-DATABASE (VM 2): TechStore company schema, grants, and lockdown
-- =====================================================================
-- Run after roles.sql, as the postgres superuser, against techstore:
--
--   sudo -u postgres psql -v ON_ERROR_STOP=1 -d techstore -f schema.sql
--
-- All objects are created as db_admin so db_admin owns them. Safe to
-- re-run: tables use IF NOT EXISTS and the grants are idempotent.
-- =====================================================================

\set ON_ERROR_STOP 1

-- ---------------------------------------------------------------------
-- Monitoring schema (as superuser): pg_stat_statements lives outside
-- public, so the PUBLIC lockdown below never touches it, and soc_monitor
-- can use it without any access to the company tables.
-- ---------------------------------------------------------------------
CREATE SCHEMA IF NOT EXISTS monitoring AUTHORIZATION postgres;
REVOKE ALL ON SCHEMA monitoring FROM PUBLIC;
CREATE EXTENSION IF NOT EXISTS pg_stat_statements SCHEMA monitoring;
GRANT USAGE ON SCHEMA monitoring TO soc_monitor;

SET ROLE db_admin;

BEGIN;

-- ---------------------------------------------------------------------
-- Lock down the public schema and the PUBLIC pseudo-role
-- ---------------------------------------------------------------------
-- Without this, any role that can connect could create objects or see
-- the schema. Roles get only what is granted explicitly further down.
REVOKE ALL ON SCHEMA public FROM PUBLIC;
REVOKE ALL ON ALL TABLES    IN SCHEMA public FROM PUBLIC;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM PUBLIC;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA public FROM PUBLIC;

-- Objects db_admin creates later inherit the same lockdown.
ALTER DEFAULT PRIVILEGES FOR ROLE db_admin IN SCHEMA public REVOKE ALL ON TABLES    FROM PUBLIC;
ALTER DEFAULT PRIVILEGES FOR ROLE db_admin IN SCHEMA public REVOKE ALL ON SEQUENCES FROM PUBLIC;
ALTER DEFAULT PRIVILEGES FOR ROLE db_admin IN SCHEMA public REVOKE ALL ON FUNCTIONS FROM PUBLIC;

-- ---------------------------------------------------------------------
-- Tables
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS departments (
    department_id  integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name           text NOT NULL UNIQUE,
    location       text NOT NULL,
    budget         numeric(12, 2) NOT NULL CHECK (budget >= 0),
    created_at     timestamptz NOT NULL DEFAULT now()
);

-- Sensitive: holds salaries, partial SSNs and login password hashes.
-- intern_readonly is deliberately denied access to this table.
CREATE TABLE IF NOT EXISTS employees (
    employee_id         integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    department_id       integer NOT NULL REFERENCES departments (department_id),
    first_name          text NOT NULL,
    last_name           text NOT NULL,
    email               text NOT NULL UNIQUE,
    username            text NOT NULL UNIQUE,
    password_hash       text NOT NULL,          -- bcrypt, written by seed.py / the VM 3 app
    role                text NOT NULL DEFAULT 'employee'
                            CHECK (role IN ('employee', 'manager', 'admin')),
    job_title           text NOT NULL,
    salary              numeric(10, 2) NOT NULL CHECK (salary > 0),
    ssn_last4           char(4) NOT NULL CHECK (ssn_last4 ~ '^[0-9]{4}$'),
    phone               text,
    hire_date           date NOT NULL,
    is_active           boolean NOT NULL DEFAULT true,
    failed_login_count  integer NOT NULL DEFAULT 0 CHECK (failed_login_count >= 0),
    last_login_at       timestamptz,
    created_at          timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS customers (
    customer_id   integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    first_name    text NOT NULL,
    last_name     text NOT NULL,
    email         text NOT NULL UNIQUE,
    phone         text,
    street        text NOT NULL,
    city          text NOT NULL,
    state         text NOT NULL,
    postal_code   text NOT NULL,
    country       text NOT NULL DEFAULT 'US',
    created_at    timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS products (
    product_id   integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sku          text NOT NULL UNIQUE,
    name         text NOT NULL,
    category     text NOT NULL,
    price        numeric(10, 2) NOT NULL CHECK (price >= 0),
    stock        integer NOT NULL DEFAULT 0 CHECK (stock >= 0),
    created_at   timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS orders (
    order_id      integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id   integer NOT NULL REFERENCES customers (customer_id),
    handled_by    integer REFERENCES employees (employee_id),
    status        text NOT NULL DEFAULT 'pending'
                      CHECK (status IN ('pending', 'paid', 'shipped', 'delivered', 'cancelled', 'refunded')),
    order_date    timestamptz NOT NULL DEFAULT now(),
    total         numeric(12, 2) NOT NULL DEFAULT 0 CHECK (total >= 0)
);

CREATE TABLE IF NOT EXISTS order_items (
    order_item_id  integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_id       integer NOT NULL REFERENCES orders (order_id) ON DELETE CASCADE,
    product_id     integer NOT NULL REFERENCES products (product_id),
    quantity       integer NOT NULL CHECK (quantity > 0),
    unit_price     numeric(10, 2) NOT NULL CHECK (unit_price >= 0)
);

CREATE INDEX IF NOT EXISTS idx_employees_department ON employees (department_id);
CREATE INDEX IF NOT EXISTS idx_orders_customer      ON orders (customer_id);
CREATE INDEX IF NOT EXISTS idx_orders_handled_by    ON orders (handled_by);
CREATE INDEX IF NOT EXISTS idx_orders_order_date    ON orders (order_date);
CREATE INDEX IF NOT EXISTS idx_order_items_order    ON order_items (order_id);
CREATE INDEX IF NOT EXISTS idx_order_items_product  ON order_items (product_id);

-- Non-sensitive staff directory: what an intern may legitimately see.
-- Views run with the owner's (db_admin's) rights, so granting this view
-- does not grant anything on employees itself.
CREATE OR REPLACE VIEW employee_directory WITH (security_barrier) AS
SELECT e.employee_id,
       e.first_name,
       e.last_name,
       e.email,
       e.job_title,
       d.name AS department
FROM employees e
JOIN departments d USING (department_id)
WHERE e.is_active;

-- ---------------------------------------------------------------------
-- Grants
-- ---------------------------------------------------------------------
GRANT USAGE ON SCHEMA public TO app_user, intern_readonly;

-- app_user (VM 3): read the catalog and staff, take orders, record
-- logins. No DELETE, no TRUNCATE, no DDL, and only the login columns of
-- employees are writable.
GRANT SELECT ON departments, employees, customers, products, orders, order_items, employee_directory
    TO app_user;
GRANT INSERT, UPDATE ON customers, orders, order_items TO app_user;
GRANT UPDATE (stock) ON products TO app_user;
GRANT UPDATE (failed_login_count, last_login_at) ON employees TO app_user;
GRANT USAGE ON SEQUENCE customers_customer_id_seq,
                        orders_order_id_seq,
                        order_items_order_item_id_seq
    TO app_user;

-- intern_readonly: read-only business data. No grant on employees, so
-- "SELECT * FROM employees" fails with permission denied (SQLSTATE 42501),
-- which the SOC agent forwards as database_permission_denied.
GRANT SELECT ON departments, customers, products, orders, order_items, employee_directory
    TO intern_readonly;

-- soc_monitor gets nothing here: it reads pg_stat_* through pg_monitor
-- and monitoring.pg_stat_statements, and has no access to company tables.

COMMIT;

RESET ROLE;
