import os

from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv

from fastapi import FastAPI, Depends, HTTPException, Header

from sqlalchemy.orm import Session

from sqlalchemy import func

from soc.backend.database import Base, engine, get_db

from soc.backend.models import Event, Alert, HostHeartbeat

from soc.processing.normalizer import normalize_event

from soc.detection.engine import detect_event


load_dotenv()

INGEST_TOKEN = os.getenv("INGEST_TOKEN")

HOST_INVENTORY = [
    {"name": "SOC-NGINX", "role": "Web server", "address": "100.91.198.37"},
    {"name": "SOC-DATABASE", "role": "Database server", "address": "100.81.236.47"},
    {"name": "SOC-APPLICATION", "role": "Application server", "address": "100.83.222.68"},
]
HOSTS_BY_NAME = {host["name"]: host for host in HOST_INVENTORY}
HOST_ONLINE_WINDOW = timedelta(seconds=150)


# Initialize database tables
Base.metadata.create_all(bind=engine)


app = FastAPI(
    title="TechStore SOC API",
    description="Security Operations Center Backend",
    version="1.0.0"
)


@app.get("/")
def root():

    return {
        "message": "SOC Backend is running",
        "status": "online"
    }


@app.get("/health")
def health():

    return {
        "status": "healthy",
        "service": "SOC Backend"
    }


@app.post("/api/hosts/heartbeat")
def record_host_heartbeat(
    payload: dict,
    db: Session = Depends(get_db),
    x_ingest_token: str | None = Header(default=None)
):
    if not INGEST_TOKEN or x_ingest_token != INGEST_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid ingestion token")

    source_machine = payload.get("source_machine")
    if source_machine not in HOSTS_BY_NAME:
        raise HTTPException(status_code=400, detail="Unknown source machine")

    now = datetime.now(timezone.utc)
    heartbeat = db.query(HostHeartbeat).filter(
        HostHeartbeat.source_machine == source_machine
    ).first()

    if heartbeat is None:
        heartbeat = HostHeartbeat(source_machine=source_machine, last_seen=now)
        db.add(heartbeat)
    else:
        heartbeat.last_seen = now

    db.commit()
    return {"source_machine": source_machine, "last_seen": now}


@app.get("/api/hosts")
def get_hosts(db: Session = Depends(get_db)):
    heartbeat_times = {
        row.source_machine: row.last_seen
        for row in db.query(HostHeartbeat).all()
    }
    event_times = dict(
        db.query(Event.source_machine, func.max(Event.timestamp))
        .group_by(Event.source_machine)
        .all()
    )

    now = datetime.now(timezone.utc)
    hosts = []

    for host in HOST_INVENTORY:
        last_seen = heartbeat_times.get(host["name"]) or event_times.get(host["name"])

        if last_seen is None:
            status = "unknown"
        else:
            if last_seen.tzinfo is None:
                last_seen = last_seen.replace(tzinfo=timezone.utc)
            status = "online" if now - last_seen <= HOST_ONLINE_WINDOW else "stale"

        hosts.append({**host, "status": status, "last_seen": last_seen})

    return hosts


# Receive security events
@app.post("/api/ingest")
def ingest_events(
    payload: dict | list[dict],
    db: Session = Depends(get_db),
    x_ingest_token: str | None = Header(default=None)
):

    if not INGEST_TOKEN or x_ingest_token != INGEST_TOKEN:

        raise HTTPException(
            status_code=401,
            detail="Invalid ingestion token"
        )

    records = payload if isinstance(payload, list) else [payload]

    accepted = 0
    alerts_created = 0

    for record in records:

        normalized = normalize_event(record)

        # Avoid duplicate event IDs
        existing = db.query(Event).filter(
            Event.event_id == normalized["event_id"]
        ).first()

        if existing:
            continue

        event = Event(**normalized)

        db.add(event)

        db.flush()

        # Execute detection rules
        alerts_created += detect_event(db, event)

        accepted += 1

    db.commit()

    return {
        "message": "Events processed successfully",
        "events_received": len(records),
        "events_saved": accepted,
        "alerts_created": alerts_created
    }


# Retrieve events
@app.get("/api/events")
def get_events(
    limit: int = 100,
    severity: str | None = None,
    event_type: str | None = None,
    source_machine: str | None = None,
    db: Session = Depends(get_db)
):

    query = db.query(Event)

    if severity:
        query = query.filter(Event.severity == severity)

    if event_type:
        query = query.filter(Event.event_type == event_type)

    if source_machine:
        query = query.filter(
            Event.source_machine == source_machine
        )

    events = query.order_by(
        Event.timestamp.desc()
    ).limit(min(max(limit, 1), 500)).all()

    return events


# Retrieve alerts
@app.get("/api/alerts")
def get_alerts(
    limit: int = 100,
    severity: str | None = None,
    status: str | None = None,
    db: Session = Depends(get_db)
):

    query = db.query(Alert)

    if severity:
        query = query.filter(Alert.severity == severity)

    if status:
        query = query.filter(Alert.status == status)

    return query.order_by(
        Alert.created_at.desc()
    ).limit(min(max(limit, 1), 500)).all()


# Retrieve one alert
@app.get("/api/alerts/{alert_id}")
def get_alert(
    alert_id: int,
    db: Session = Depends(get_db)
):

    alert = db.query(Alert).filter(
        Alert.id == alert_id
    ).first()

    if not alert:

        raise HTTPException(
            status_code=404,
            detail="Alert not found"
        )

    return alert


# Update alert status
@app.patch("/api/alerts/{alert_id}")
def update_alert(
    alert_id: int,
    payload: dict,
    db: Session = Depends(get_db)
):

    alert = db.query(Alert).filter(
        Alert.id == alert_id
    ).first()

    if not alert:

        raise HTTPException(
            status_code=404,
            detail="Alert not found"
        )

    new_status = payload.get("status")

    allowed_statuses = [
        "new",
        "investigating",
        "resolved",
        "closed"
    ]

    if new_status not in allowed_statuses:

        raise HTTPException(
            status_code=400,
            detail="Invalid alert status"
        )

    alert.status = new_status

    db.commit()

    db.refresh(alert)

    return alert


# Dashboard statistics
@app.get("/api/stats")
def get_stats(db: Session = Depends(get_db)):

    total_events = db.query(Event).count()

    total_alerts = db.query(Alert).count()

    severity_counts = {}

    for severity in ["critical", "high", "medium", "low"]:

        severity_counts[severity] = db.query(Alert).filter(
            Alert.severity == severity
        ).count()

    new_alerts = db.query(Alert).filter(
        Alert.status == "new"
    ).count()

    recent_events = db.query(Event).order_by(
        Event.timestamp.desc()
    ).limit(5).all()

    return {

        "total_events": total_events,

        "total_alerts": total_alerts,

        "new_alerts": new_alerts,

        "severity_counts": severity_counts,

        "recent_events": recent_events

    }
