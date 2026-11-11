#!/usr/bin/env python3
"""Fill the TechStore database (SOC-DATABASE, VM 2) with fake company data.

Usage (on VM 2, as any user):

    export SEED_DSN='postgresql://db_admin:<password>@127.0.0.1:5432/techstore'
    export SEED_EMPLOYEE_PASSWORD='<shared lab password for employee logins>'
    python3 seed.py            # refuses if data already exists
    python3 seed.py --reset    # truncates the company tables first

Data is deterministic (fixed Faker seed), so every teammate gets the same
employees and customers. Each employee's password_hash is a bcrypt hash of
SEED_EMPLOYEE_PASSWORD, so the VM 3 login page can verify it with bcrypt.
"""

import argparse
import os
import random
import sys
from datetime import timedelta
from decimal import Decimal

import bcrypt
import psycopg
from faker import Faker

SEED = 2026
COUNTS = {
    "customers": 5000,   # large enough that a bulk SELECT stands out
    "products": 60,
    "orders": 4000,
}

DEPARTMENTS = [
    # name, location, budget, headcount
    ("Executive", "Austin, TX", 900_000, 4),
    ("Sales", "Austin, TX", 1_200_000, 18),
    ("Customer Support", "Denver, CO", 600_000, 14),
    ("IT", "Austin, TX", 1_000_000, 10),
    ("Warehouse", "Reno, NV", 800_000, 16),
    ("Finance", "Austin, TX", 700_000, 6),
    ("Human Resources", "Denver, CO", 400_000, 4),
    ("Marketing", "Remote", 650_000, 8),
]

JOB_TITLES = {
    "Executive": ["Chief Executive Officer", "Chief Operating Officer", "Chief Technology Officer", "Chief Financial Officer"],
    "Sales": ["Sales Associate", "Senior Sales Associate", "Sales Manager"],
    "Customer Support": ["Support Specialist", "Senior Support Specialist", "Support Manager"],
    "IT": ["Systems Administrator", "Database Administrator", "Help Desk Technician", "Security Analyst", "IT Manager"],
    "Warehouse": ["Warehouse Associate", "Forklift Operator", "Shipping Coordinator", "Warehouse Manager"],
    "Finance": ["Accountant", "Payroll Specialist", "Finance Manager"],
    "Human Resources": ["HR Generalist", "Recruiter", "HR Manager"],
    "Marketing": ["Marketing Specialist", "Content Writer", "Marketing Manager"],
}

SALARY_RANGE = {
    "Executive": (180_000, 260_000),
    "IT": (65_000, 135_000),
    "Finance": (60_000, 120_000),
}

PRODUCT_CATALOG = {
    "Laptops": ["UltraBook 14", "ProBook 16", "Student Laptop 13", "Gaming Laptop 17"],
    "Monitors": ["24in IPS Monitor", "27in 4K Monitor", "34in Ultrawide Monitor"],
    "Accessories": ["Wireless Mouse", "Mechanical Keyboard", "USB-C Hub", "Laptop Stand", "Webcam 1080p"],
    "Networking": ["Wi-Fi 7 Router", "Mesh Node", "8-Port Switch", "Ethernet Cable 3m"],
    "Storage": ["1TB NVMe SSD", "2TB External SSD", "4TB NAS Drive", "128GB USB Drive"],
    "Audio": ["Noise-Cancelling Headphones", "Bluetooth Speaker", "USB Microphone"],
}

ORDER_STATUSES = ["pending", "paid", "shipped", "delivered", "delivered", "delivered", "cancelled", "refunded"]

COMPANY_TABLES = ["order_items", "orders", "products", "customers", "employees", "departments"]


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--reset", action="store_true", help="truncate company tables before seeding")
    return parser.parse_args()


def require_env(name):
    value = os.environ.get(name)
    if not value:
        sys.exit(f"error: environment variable {name} is not set (see the docstring at the top of seed.py)")
    return value


def make_username(first, last, taken):
    base = (first[0] + last).lower()
    base = "".join(ch for ch in base if ch.isalnum())
    name, n = base, 1
    while name in taken:
        n += 1
        name = f"{base}{n}"
    taken.add(name)
    return name


def seed(conn, fake, password_hash):
    rng = random.Random(SEED)

    with conn.cursor() as cur:
        # Departments
        dept_ids = {}
        for name, location, budget, _ in DEPARTMENTS:
            cur.execute(
                "INSERT INTO departments (name, location, budget) VALUES (%s, %s, %s) RETURNING department_id",
                (name, location, Decimal(budget)),
            )
            dept_ids[name] = cur.fetchone()[0]

        # Employees. The first employee in each department with a title
        # ending in "Manager" or starting with "Chief" gets a manager/admin
        # role, so the VM 3 app has some privileged accounts to target.
        usernames = set()
        employee_rows = []
        for dept, _, _, headcount in DEPARTMENTS:
            low, high = SALARY_RANGE.get(dept, (38_000, 95_000))
            for i in range(headcount):
                first, last = fake.first_name(), fake.last_name()
                username = make_username(first, last, usernames)
                title = JOB_TITLES[dept][i % len(JOB_TITLES[dept])]
                if dept == "IT" and title in ("Systems Administrator", "IT Manager"):
                    role = "admin"
                elif title.endswith("Manager") or title.startswith("Chief"):
                    role = "manager"
                else:
                    role = "employee"
                employee_rows.append((
                    dept_ids[dept], first, last, f"{username}@techstore.example",
                    username, password_hash, role, title,
                    Decimal(rng.randrange(low, high, 500)),
                    f"{rng.randrange(0, 10_000):04d}",
                    fake.numerify("555-###-####"),
                    fake.date_between(start_date="-12y", end_date="-30d"),
                    rng.random() > 0.05,
                ))
        cur.executemany(
            """INSERT INTO employees (department_id, first_name, last_name, email, username,
                                      password_hash, role, job_title, salary, ssn_last4,
                                      phone, hire_date, is_active)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            employee_rows,
        )
        cur.execute("SELECT employee_id FROM employees WHERE department_id = %s", (dept_ids["Sales"],))
        sales_ids = [r[0] for r in cur.fetchall()]

        # Customers (COPY is much faster than INSERT for thousands of rows)
        emails = set()
        with cur.copy(
            "COPY customers (first_name, last_name, email, phone, street, city, state, postal_code) FROM STDIN"
        ) as copy:
            for _ in range(COUNTS["customers"]):
                first, last = fake.first_name(), fake.last_name()
                email = f"{first}.{last}{rng.randrange(1, 9999)}@{fake.free_email_domain()}".lower()
                while email in emails:
                    email = f"{first}.{last}{rng.randrange(1, 99999)}@{fake.free_email_domain()}".lower()
                emails.add(email)
                copy.write_row((
                    first, last, email, fake.numerify("555-###-####"),
                    fake.street_address(), fake.city(), fake.state_abbr(), fake.zipcode(),
                ))

        # Products
        product_rows = []
        sku_n = 1000
        while len(product_rows) < COUNTS["products"]:
            for category, names in PRODUCT_CATALOG.items():
                for name in names:
                    if len(product_rows) >= COUNTS["products"]:
                        break
                    sku_n += 1
                    variant = f" ({rng.choice(['Black', 'Silver', 'White', 'Gen 2', 'Pro'])})" if sku_n > 1023 else ""
                    product_rows.append((
                        f"TS-{category[:3].upper()}-{sku_n}", name + variant, category,
                        Decimal(rng.randrange(900, 250_000)) / 100, rng.randrange(0, 400),
                    ))
        cur.executemany(
            "INSERT INTO products (sku, name, category, price, stock) VALUES (%s, %s, %s, %s, %s)",
            product_rows,
        )
        cur.execute("SELECT product_id, price FROM products")
        products = cur.fetchall()
        cur.execute("SELECT customer_id FROM customers")
        customer_ids = [r[0] for r in cur.fetchall()]

        # Orders and their line items
        for _ in range(COUNTS["orders"]):
            order_date = fake.date_time_between(start_date="-2y", end_date="now", tzinfo=None)
            cur.execute(
                """INSERT INTO orders (customer_id, handled_by, status, order_date)
                   VALUES (%s, %s, %s, %s::timestamp AT TIME ZONE 'UTC') RETURNING order_id""",
                (rng.choice(customer_ids), rng.choice(sales_ids + [None]), rng.choice(ORDER_STATUSES), order_date),
            )
            order_id = cur.fetchone()[0]
            items = [(order_id, pid, rng.randint(1, 3), price) for pid, price in rng.sample(products, rng.randint(1, 4))]
            cur.executemany(
                "INSERT INTO order_items (order_id, product_id, quantity, unit_price) VALUES (%s, %s, %s, %s)",
                items,
            )
        cur.execute(
            """UPDATE orders o SET total = s.total
               FROM (SELECT order_id, sum(quantity * unit_price) AS total FROM order_items GROUP BY order_id) s
               WHERE o.order_id = s.order_id"""
        )

        # Make the newest orders look recent, so dashboards have fresh data.
        cur.execute(
            "UPDATE orders SET order_date = now() - (random() * interval '7 days') "
            "WHERE order_id IN (SELECT order_id FROM orders ORDER BY order_id DESC LIMIT 50)"
        )

        cur.execute("SELECT count(*) FROM employees")
        n_emp = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM order_items")
        n_items = cur.fetchone()[0]

    print(
        f"seeded: {len(DEPARTMENTS)} departments, {n_emp} employees, {COUNTS['customers']} customers, "
        f"{len(product_rows)} products, {COUNTS['orders']} orders, {n_items} order items"
    )


def main():
    args = parse_args()
    dsn = require_env("SEED_DSN")
    employee_password = require_env("SEED_EMPLOYEE_PASSWORD")

    fake = Faker("en_US")
    Faker.seed(SEED)
    # One hash for every employee: bcrypt is slow on purpose, and the lab
    # only needs one known password. Each row still gets a valid hash.
    password_hash = bcrypt.hashpw(employee_password.encode(), bcrypt.gensalt(rounds=12)).decode()

    with psycopg.connect(dsn, application_name="techstore-seed") as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM departments")
            existing = cur.fetchone()[0]
            if existing and not args.reset:
                sys.exit("error: techstore already has data; re-run with --reset to wipe and re-seed")
            if args.reset:
                cur.execute(f"TRUNCATE {', '.join(COMPANY_TABLES)} RESTART IDENTITY CASCADE")
        seed(conn, fake, password_hash)
        conn.commit()


if __name__ == "__main__":
    main()
