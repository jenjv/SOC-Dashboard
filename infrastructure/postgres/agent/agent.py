#!/usr/bin/env python3
"""SOC agent for SOC-DATABASE (VM 2).

Runs on the PostgreSQL VM and sends events to the SOC backend on VM 4
(POST /api/ingest with an X-Ingest-Token header; see
docs/agent-payload.md). It does three things:

1. System metrics (psutil): CPU, RAM, swap, disk, network and load,
   every SOC_METRICS_INTERVAL seconds.
2. Database stats (pg_stat_* as the read-only soc_monitor role):
   connections, transactions, deadlocks, rows read per sensitive table,
   and unexpected client IPs. Unusually large reads of sensitive tables
   are reported as database_bulk_read.
3. Log tailer: follows PostgreSQL's jsonlog files and forwards
   ERROR/FATAL/PANIC events, DDL, slow queries, server start/stop,
   pgaudit lines, and connection events from non-monitor users.

All configuration comes from environment variables (soc-agent.env).
"""

import glob
import json
import logging
import os
import re
import signal
import socket
import sys
import time
import urllib.error
import urllib.request
from collections import deque
from datetime import datetime, timezone

try:
    import psutil
except ImportError:  # checked in main(); lets tests import this module
    psutil = None

try:
    import psycopg
except ImportError:
    psycopg = None

AGENT_VERSION = "1.0.0"
LOG = logging.getLogger("soc-agent")

# The VM 4 parser re-parses any "message", "log" or "msg" field and lets
# the result overwrite source_ip and description. Events never use those
# keys; the PostgreSQL message goes in "pg_message" instead.
RESERVED_KEYS = ("message", "log", "msg")


# ---------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------
def _env_list(name, default=""):
    return [item.strip() for item in os.environ.get(name, default).split(",") if item.strip()]


def _env_bool(name, default):
    return os.environ.get(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


class Config:
    def __init__(self):
        self.ingest_url = os.environ.get("SOC_INGEST_URL", "")
        self.ingest_token = os.environ.get("SOC_INGEST_TOKEN", "")
        self.source_machine = os.environ.get("SOC_SOURCE_MACHINE", "SOC-DATABASE")
        self.pg_dsn = os.environ.get("PG_MONITOR_DSN", "")
        self.pg_log_glob = os.environ.get("PG_LOG_GLOB", "/var/log/postgresql/soc/soc-*.json")
        self.pg_data_dir = os.environ.get("PG_DATA_DIR", "/var/lib/postgresql")
        self.monitor_users = set(_env_list("SOC_MONITOR_USERS", "soc_monitor"))
        self.allowed_client_ips = set(_env_list("SOC_ALLOWED_CLIENT_IPS", "127.0.0.1,::1"))
        self.sensitive_tables = set(_env_list("SOC_SENSITIVE_TABLES", "employees,customers,orders"))
        self.bulk_read_rows = int(os.environ.get("SOC_BULK_READ_ROWS", "1000"))
        self.metrics_interval = float(os.environ.get("SOC_METRICS_INTERVAL", "30"))
        self.log_poll_interval = float(os.environ.get("SOC_LOG_POLL_INTERVAL", "2"))
        self.state_file = os.environ.get("SOC_STATE_FILE", "/var/lib/soc-agent/state.json")
        self.log_connections = _env_bool("SOC_LOG_CONNECTIONS", True)
        self.resource_warn_percent = float(os.environ.get("SOC_RESOURCE_WARN_PERCENT", "90"))
        self.batch_size = int(os.environ.get("SOC_BATCH_SIZE", "100"))
        self.max_queue = int(os.environ.get("SOC_MAX_QUEUE", "5000"))
        self.dry_run = _env_bool("SOC_DRY_RUN", False)  # print events instead of sending

    def validate(self):
        problems = []
        if not self.dry_run:
            if not self.ingest_url:
                problems.append("SOC_INGEST_URL is not set")
            if not self.ingest_token:
                problems.append("SOC_INGEST_TOKEN is not set")
        if not self.pg_dsn:
            problems.append("PG_MONITOR_DSN is not set")
        return problems


# ---------------------------------------------------------------------
# Event construction
# ---------------------------------------------------------------------
def utc_now_iso():
    return datetime.now(timezone.utc).isoformat()


def pg_timestamp_to_iso(value):
    """'2026-11-11 18:22:10.123 UTC' -> '2026-11-11T18:22:10.123000+00:00'."""
    if not value:
        return utc_now_iso()
    text = str(value).strip()
    if text.endswith(" UTC"):
        text = text[:-4] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return utc_now_iso()
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.isoformat()


def truncate(text, limit):
    text = "" if text is None else str(text)
    return text if len(text) <= limit else text[: limit - 3] + "..."


def make_event(cfg, event_type, severity, description, timestamp=None, **fields):
    """Build one event in the format VM 4's /api/ingest normalizer expects."""
    event = {
        "timestamp": timestamp or utc_now_iso(),
        "source_machine": cfg.source_machine,
        "service": "postgresql",
        "event_type": event_type,
        "severity": severity,
        "description": truncate(description, 1000),
        "agent": "soc-agent-vm2",
        "agent_version": AGENT_VERSION,
    }
    for key, value in fields.items():
        if value is None or key in RESERVED_KEYS:
            continue
        event[key] = value
    return event


# ---------------------------------------------------------------------
# Sending to VM 4
# ---------------------------------------------------------------------
class Sender:
    """Batches events and POSTs them; keeps them queued while VM 4 is down."""

    def __init__(self, cfg):
        self.cfg = cfg
        self.queue = deque(maxlen=cfg.max_queue)
        self.next_attempt = 0.0
        self.backoff = 1.0
        self.dropped_warned = False

    def add(self, event):
        if len(self.queue) == self.queue.maxlen and not self.dropped_warned:
            LOG.warning("send queue full (%d); oldest events are being dropped", self.queue.maxlen)
            self.dropped_warned = True
        self.queue.append(event)

    def flush(self):
        if not self.queue or time.monotonic() < self.next_attempt:
            return
        while self.queue:
            batch = [self.queue[i] for i in range(min(self.cfg.batch_size, len(self.queue)))]
            if not self._post(batch):
                self.next_attempt = time.monotonic() + self.backoff
                self.backoff = min(self.backoff * 2, 60.0)
                return
            for _ in batch:
                self.queue.popleft()
            self.backoff = 1.0
            self.dropped_warned = False

    def _post(self, batch):
        if self.cfg.dry_run:
            for event in batch:
                print(json.dumps(event, default=str), flush=True)
            return True
        body = json.dumps(batch, default=str).encode()
        request = urllib.request.Request(
            self.cfg.ingest_url,
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "X-Ingest-Token": self.cfg.ingest_token,
                "User-Agent": f"soc-agent-vm2/{AGENT_VERSION}",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                reply = response.read(2000).decode(errors="replace")
            LOG.debug("sent %d events: %s", len(batch), reply)
            return True
        except urllib.error.HTTPError as exc:
            if exc.code == 401:
                LOG.error("VM 4 rejected the ingest token (HTTP 401); check SOC_INGEST_TOKEN")
            elif 400 <= exc.code < 500:
                # A malformed batch will never succeed. Returning True makes
                # flush() drop it so it doesn't block the queue forever.
                LOG.error("VM 4 refused a batch of %d events (HTTP %d); dropping it", len(batch), exc.code)
                return True
            else:
                LOG.warning("VM 4 returned HTTP %d; will retry", exc.code)
        except (urllib.error.URLError, OSError) as exc:
            LOG.warning("cannot reach VM 4 at %s (%s); %d events queued", self.cfg.ingest_url, exc, len(self.queue))
        return False


# ---------------------------------------------------------------------
# PostgreSQL jsonlog classification
# ---------------------------------------------------------------------
SQLSTATE_RULES = {
    # SQLSTATE: (event_type, severity)
    "28P01": ("database_authentication_failure", "high"),   # wrong password / unknown user
    "28000": ("database_access_rejected", "high"),          # pg_hba reject, no entry, cannot login
    "42501": ("database_permission_denied", "high"),        # insufficient_privilege
    "3D000": ("database_access_rejected", "medium"),        # database does not exist
    "57014": ("database_query_canceled", "medium"),         # statement_timeout / cancel
    "53300": ("database_too_many_connections", "high"),
    "40P01": ("database_deadlock", "medium"),
}

SERVICE_STATE_PREFIXES = (
    "database system is ready to accept connections",
    "database system is shut down",
    "received fast shutdown request",
    "received smart shutdown request",
    "received immediate shutdown request",
    "database system was interrupted",
    "database system was not properly shut down",
)

DURATION_RE = re.compile(r"duration:\s*([\d.]+)\s*ms")


def classify_pg_log(cfg, rec):
    """Turn one jsonlog record (dict) into an event dict, or None to skip it."""
    level = (rec.get("error_severity") or "").upper()
    msg = rec.get("message") or ""
    state = rec.get("state_code")
    user = rec.get("user")
    remote = rec.get("remote_host")
    source_ip = None if remote in (None, "", "[local]") else remote
    db = rec.get("dbname")
    is_monitor = user in cfg.monitor_users

    event_type = severity = None

    if level in ("ERROR", "FATAL", "PANIC"):
        if "password authentication failed" in msg.lower():
            event_type, severity = "database_authentication_failure", "high"
        elif state in SQLSTATE_RULES:
            event_type, severity = SQLSTATE_RULES[state]
        else:
            event_type = "database_error"
            severity = "medium" if level == "ERROR" else "high"
        if level == "PANIC":
            severity = "critical"
    elif level == "LOG":
        if msg.startswith("connection authorized:"):
            if is_monitor or not cfg.log_connections:
                return None
            event_type, severity = "database_connection", "low"
        elif msg.startswith("disconnection:"):
            if is_monitor or not cfg.log_connections:
                return None
            event_type, severity = "database_disconnection", "low"
        elif msg.startswith("statement:"):
            # log_statement = 'ddl' only logs CREATE/ALTER/DROP-class statements
            event_type, severity = "database_ddl", "medium"
        elif msg.startswith("duration:"):
            event_type, severity = "database_slow_query", "medium"
        elif msg.startswith("AUDIT:"):
            event_type = "database_audit"
            severity = "medium" if "employees" in msg else "low"
        elif msg.startswith(SERVICE_STATE_PREFIXES):
            event_type, severity = "database_service_state", "medium"
        else:
            return None  # checkpoints, "connection received", autovacuum, etc.
    else:
        return None  # WARNING/NOTICE/INFO/DEBUG are noise for the SOC

    who = f"user={user or '?'} db={db or '?'} from={source_ip or 'local socket'}"
    description = f"PostgreSQL {level}: {msg} ({who})"

    extra = {}
    if event_type == "database_slow_query":
        match = DURATION_RE.search(msg)
        if match:
            extra["duration_ms"] = float(match.group(1))

    return make_event(
        cfg,
        event_type,
        severity,
        description,
        timestamp=pg_timestamp_to_iso(rec.get("timestamp")),
        source_ip=source_ip,
        source_port=rec.get("remote_port"),
        username=user,
        database=db,
        application_name=rec.get("application_name"),
        pg_severity=level,
        sqlstate=state,
        pg_message=truncate(msg, 2000),
        pg_detail=truncate(rec.get("detail"), 1000) if rec.get("detail") else None,
        statement=truncate(rec.get("statement"), 1000) if rec.get("statement") else None,
        session_id=rec.get("session_id"),
        pid=rec.get("pid"),
        **extra,
    )


class JsonLogTailer:
    """Follows the newest soc-*.json file and survives daily rotation and restarts."""

    def __init__(self, pattern, state):
        self.pattern = pattern
        self.path = state.get("path")
        self.offset = state.get("offset", 0)
        self.inode = state.get("inode")
        self.started = self.path is not None

    def state(self):
        return {"path": self.path, "offset": self.offset, "inode": self.inode}

    def _files(self):
        return sorted(glob.glob(self.pattern))

    def poll(self, max_lines=5000):
        """Return the new complete JSON records since the last poll."""
        files = self._files()
        if not files:
            return []
        if not self.started:
            # First run: start at the end of the newest file, not a backlog.
            self.path = files[-1]
            stat = os.stat(self.path)
            self.offset, self.inode, self.started = stat.st_size, stat.st_ino, True
            LOG.info("tailing %s from byte %d", self.path, self.offset)
            return []
        if self.path not in files:
            # Our file vanished (deleted/renamed): move to the oldest newer file.
            newer = [f for f in files if f > (self.path or "")]
            self.path = newer[0] if newer else files[-1]
            self.offset, self.inode = 0, None

        records = []
        while len(records) < max_lines:
            try:
                stat = os.stat(self.path)
            except FileNotFoundError:
                break
            if (self.inode is not None and stat.st_ino != self.inode) or stat.st_size < self.offset:
                self.offset = 0  # replaced or truncated
            self.inode = stat.st_ino
            with open(self.path, "rb") as handle:
                handle.seek(self.offset)
                chunk = handle.read(4 * 1024 * 1024)
            end = chunk.rfind(b"\n")
            if end >= 0:
                for line in chunk[: end + 1].splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError:
                        LOG.debug("skipping non-JSON log line: %r", line[:200])
                self.offset += end + 1
            if end >= 0 and len(chunk) == 4 * 1024 * 1024:
                continue  # more to read in this file
            newer = [f for f in files if f > self.path]
            # PostgreSQL has moved on to a newer file and this one is fully read
            if newer and (end < 0 or self.offset >= os.path.getsize(self.path)):
                LOG.info("log rotated: %s -> %s", self.path, newer[0])
                self.path, self.offset, self.inode = newer[0], 0, None
                continue
            break
        return records


# ---------------------------------------------------------------------
# System metrics
# ---------------------------------------------------------------------
class MetricsCollector:
    def __init__(self, cfg):
        self.cfg = cfg
        self.last_net = None
        self.last_time = None
        psutil.cpu_percent(interval=None)  # prime; first reading is meaningless

    def collect(self):
        cfg = self.cfg
        now = time.monotonic()
        vm = psutil.virtual_memory()
        swap = psutil.swap_memory()
        root = psutil.disk_usage("/")
        try:
            data = psutil.disk_usage(cfg.pg_data_dir)
        except OSError:
            data = root
        net = psutil.net_io_counters()
        rx_rate = tx_rate = None
        if self.last_net is not None:
            elapsed = max(now - self.last_time, 0.001)
            rx_rate = round((net.bytes_recv - self.last_net.bytes_recv) / elapsed)
            tx_rate = round((net.bytes_sent - self.last_net.bytes_sent) / elapsed)
        self.last_net, self.last_time = net, now

        postgres_procs = 0
        for proc in psutil.process_iter(["name"]):
            if (proc.info.get("name") or "").startswith("postgres"):
                postgres_procs += 1

        cpu = psutil.cpu_percent(interval=None)
        load1, load5, load15 = os.getloadavg()
        metrics = {
            "cpu_percent": cpu,
            "cpu_count": psutil.cpu_count(),
            "load_1m": round(load1, 2),
            "load_5m": round(load5, 2),
            "load_15m": round(load15, 2),
            "memory_percent": vm.percent,
            "memory_used_mb": round(vm.used / 1048576),
            "memory_total_mb": round(vm.total / 1048576),
            "swap_percent": swap.percent,
            "disk_root_percent": root.percent,
            "disk_pgdata_percent": data.percent,
            "disk_pgdata_free_gb": round(data.free / 1073741824, 2),
            "net_rx_bytes_per_sec": rx_rate,
            "net_tx_bytes_per_sec": tx_rate,
            "net_rx_bytes_total": net.bytes_recv,
            "net_tx_bytes_total": net.bytes_sent,
            "postgres_process_count": postgres_procs,
            "uptime_seconds": round(time.time() - psutil.boot_time()),
        }
        hot = [
            name for name, value in (
                ("CPU", cpu), ("memory", vm.percent),
                ("root disk", root.percent), ("PostgreSQL disk", data.percent),
            ) if value >= cfg.resource_warn_percent
        ]
        if hot:
            event_type, severity = "system_resource_warning", "medium"
            summary = f"High resource usage on {cfg.source_machine}: {', '.join(hot)} at or above {cfg.resource_warn_percent:.0f}%"
        else:
            event_type, severity = "system_metrics", "low"
            summary = (
                f"CPU {cpu:.0f}%, RAM {vm.percent:.0f}%, disk {root.percent:.0f}%, "
                f"postgres processes {postgres_procs}"
            )
        if postgres_procs == 0:
            event_type, severity = "database_service_down", "critical"
            summary = f"No postgres processes are running on {cfg.source_machine}"
        return make_event(cfg, event_type, severity, summary, **metrics)


# ---------------------------------------------------------------------
# Database statistics (soc_monitor role)
# ---------------------------------------------------------------------
class DbStatsCollector:
    def __init__(self, cfg):
        self.cfg = cfg
        self.conn = None
        self.last_db = None
        self.last_tables = None
        self.last_role_rows = None
        self.have_pgss = True
        self.db_down = False
        self.reported_clients = {}

    def _connect(self):
        if self.conn is None or self.conn.closed:
            self.conn = psycopg.connect(
                self.cfg.pg_dsn, autocommit=True, connect_timeout=5, application_name="soc-agent"
            )
            with self.conn.cursor() as cur:
                cur.execute("SET statement_timeout = '5s'")
        return self.conn

    def collect(self):
        events = []
        try:
            conn = self._connect()
            with conn.cursor() as cur:
                events.extend(self._collect(cur))
            if self.db_down:
                self.db_down = False
                events.append(make_event(self.cfg, "database_recovered", "low",
                                         "soc_monitor can connect to PostgreSQL again"))
        except psycopg.Error as exc:
            if self.conn is not None:
                try:
                    self.conn.close()
                except psycopg.Error:
                    pass
                self.conn = None
            if not self.db_down:
                self.db_down = True
                events.append(make_event(
                    self.cfg, "database_unreachable", "high",
                    f"SOC agent cannot query PostgreSQL as soc_monitor: {truncate(exc, 300)}",
                ))
            LOG.warning("database stats failed: %s", exc)
        return events

    def _collect(self, cur):
        cfg = self.cfg
        events = []

        cur.execute(
            """SELECT current_database(), numbackends, xact_commit, xact_rollback, deadlocks,
                      tup_returned, tup_fetched, tup_inserted, tup_updated, tup_deleted,
                      temp_bytes, conflicts, blks_read, blks_hit
               FROM pg_stat_database WHERE datname = current_database()"""
        )
        cols = [d.name for d in cur.description]
        db = dict(zip(cols, cur.fetchone()))
        deltas = {}
        if self.last_db:
            for key in ("xact_commit", "xact_rollback", "deadlocks", "tup_returned", "tup_fetched",
                        "tup_inserted", "tup_updated", "tup_deleted", "temp_bytes"):
                deltas[f"{key}_delta"] = max(db[key] - self.last_db[key], 0)
        self.last_db = db

        cur.execute(
            """SELECT usename, state, client_addr::text, backend_type,
                      EXTRACT(EPOCH FROM (now() - query_start)) AS query_seconds,
                      EXTRACT(EPOCH FROM (now() - xact_start))  AS xact_seconds
               FROM pg_stat_activity
               WHERE backend_type = 'client backend' AND pid <> pg_backend_pid()"""
        )
        sessions = cur.fetchall()
        by_user, by_state = {}, {}
        longest_query = longest_idle_xact = 0.0
        for usename, state, client_addr, _, query_s, xact_s in sessions:
            by_user[usename or "?"] = by_user.get(usename or "?", 0) + 1
            by_state[state or "?"] = by_state.get(state or "?", 0) + 1
            if state == "active" and query_s:
                longest_query = max(longest_query, float(query_s))
            if state and state.startswith("idle in transaction") and xact_s:
                longest_idle_xact = max(longest_idle_xact, float(xact_s))
            if client_addr and client_addr.split("/")[0] not in cfg.allowed_client_ips:
                key = (usename, client_addr)
                if time.monotonic() - self.reported_clients.get(key, 0) > 600:
                    self.reported_clients[key] = time.monotonic()
                    events.append(make_event(
                        cfg, "database_unexpected_client", "high",
                        f"PostgreSQL session from unexpected address {client_addr} as {usename}",
                        source_ip=client_addr.split("/")[0], username=usename,
                    ))

        # Rows read per sensitive table since the last sample
        cur.execute(
            """SELECT relname, COALESCE(seq_tup_read, 0) + COALESCE(idx_tup_fetch, 0)
               FROM pg_stat_user_tables WHERE schemaname = 'public'"""
        )
        tables = dict(cur.fetchall())
        role_deltas = self._role_row_deltas(cur)
        if self.last_tables is not None:
            for table in sorted(cfg.sensitive_tables):
                rows = tables.get(table, 0) - self.last_tables.get(table, 0)
                if rows >= cfg.bulk_read_rows:
                    top = sorted(role_deltas.items(), key=lambda kv: kv[1], reverse=True)[:3]
                    readers = ", ".join(f"{r} ({n} rows)" for r, n in top if n > 0) or "unknown"
                    events.append(make_event(
                        cfg, "database_bulk_read", "medium",
                        f"{rows} rows read from {table} in the last {cfg.metrics_interval:.0f}s "
                        f"(threshold {cfg.bulk_read_rows}); top readers: {readers}",
                        table=table, rows_read=rows, threshold=cfg.bulk_read_rows,
                        username=top[0][0] if top and top[0][1] > 0 else None,
                        top_readers=dict(top),
                    ))
        self.last_tables = tables

        stats = {
            "database": db["current_database"],
            "connections_total": db["numbackends"],
            "connections_by_user": by_user,
            "connections_by_state": by_state,
            "longest_active_query_seconds": round(longest_query, 1),
            "longest_idle_in_transaction_seconds": round(longest_idle_xact, 1),
            "deadlocks_total": db["deadlocks"],
            "cache_hit_ratio": round(db["blks_hit"] / max(db["blks_hit"] + db["blks_read"], 1), 4),
            **deltas,
        }
        events.append(make_event(
            cfg, "database_stats", "low",
            f"{db['numbackends']} connections; "
            f"{deltas.get('xact_commit_delta', 0)} commits, {deltas.get('xact_rollback_delta', 0)} rollbacks "
            f"since last sample",
            stats=stats,
        ))
        return events

    def _role_row_deltas(self, cur):
        """Rows returned per role since the last sample, from pg_stat_statements."""
        if not self.have_pgss:
            return {}
        try:
            cur.execute(
                """SELECT r.rolname, sum(s.rows)::bigint
                   FROM monitoring.pg_stat_statements s JOIN pg_roles r ON r.oid = s.userid
                   WHERE s.dbid = (SELECT oid FROM pg_database WHERE datname = current_database())
                   GROUP BY r.rolname"""
            )
        except psycopg.Error as exc:
            LOG.info("pg_stat_statements unavailable, bulk reads will not name a role: %s", exc)
            self.have_pgss = False
            return {}
        current = {role: int(rows) for role, rows in cur.fetchall()}
        previous, self.last_role_rows = self.last_role_rows, current
        if previous is None:
            return {}
        return {role: rows - previous.get(role, 0) for role, rows in current.items()
                if role not in self.cfg.monitor_users}


# ---------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------
def load_state(path):
    try:
        with open(path) as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return {}


def save_state(path, state):
    tmp = f"{path}.tmp"
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(tmp, "w") as handle:
            json.dump(state, handle)
        os.replace(tmp, path)
    except OSError as exc:
        LOG.warning("could not save state to %s: %s", path, exc)


def main():
    logging.basicConfig(
        level=os.environ.get("SOC_LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    if psutil is None or psycopg is None:
        sys.exit("missing dependencies: pip install -r requirements.txt")

    cfg = Config()
    problems = cfg.validate()
    if problems:
        sys.exit("configuration error: " + "; ".join(problems))

    state = load_state(cfg.state_file)
    tailer = JsonLogTailer(cfg.pg_log_glob, state.get("tailer", {}))
    sender = Sender(cfg)
    metrics = MetricsCollector(cfg)
    dbstats = DbStatsCollector(cfg)

    stopping = False

    def stop(signum, _frame):
        nonlocal stopping
        LOG.info("received signal %d, stopping", signum)
        stopping = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    sender.add(make_event(
        cfg, "agent_started", "low",
        f"SOC agent {AGENT_VERSION} started on {socket.gethostname()}",
        hostname=socket.gethostname(),
    ))
    LOG.info("sending to %s as %s", cfg.ingest_url or "stdout (dry run)", cfg.source_machine)

    next_metrics = 0.0
    last_state_save = time.monotonic()
    while not stopping:
        loop_start = time.monotonic()
        try:
            for rec in tailer.poll():
                event = classify_pg_log(cfg, rec)
                if event:
                    sender.add(event)
        except OSError as exc:
            LOG.warning("cannot read PostgreSQL logs (%s): %s", cfg.pg_log_glob, exc)

        if loop_start >= next_metrics:
            next_metrics = loop_start + cfg.metrics_interval
            try:
                sender.add(metrics.collect())
            except Exception:  # never let one bad sample kill the agent
                LOG.exception("metrics collection failed")
            for event in dbstats.collect():
                sender.add(event)

        sender.flush()
        if time.monotonic() - last_state_save > 10:
            save_state(cfg.state_file, {"tailer": tailer.state()})
            last_state_save = time.monotonic()
        time.sleep(max(cfg.log_poll_interval - (time.monotonic() - loop_start), 0.1))

    sender.add(make_event(cfg, "agent_stopped", "low", "SOC agent stopped"))
    sender.next_attempt = 0.0
    sender.flush()
    save_state(cfg.state_file, {"tailer": tailer.state()})


if __name__ == "__main__":
    main()
