from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from soc.backend.models import Event, Alert


def create_alert(
    db,
    event,
    rule_id,
    title,
    description,
    severity="high"
):

    # Prevent repeated duplicate alerts for the same source
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=10)

    existing = db.query(Alert).filter(
        Alert.rule_id == rule_id,
        Alert.source_ip == event.source_ip,
        Alert.created_at >= cutoff,
        Alert.status != "closed"
    ).first()

    if existing:
        return False

    alert = Alert(

        rule_id=rule_id,

        title=title,

        severity=severity,

        description=description,

        source_machine=event.source_machine,

        source_ip=event.source_ip,

        event_id=event.event_id,

        status="new"
    )

    db.add(alert)

    return True


def detect_event(db: Session, event: Event):

    alerts_created = 0

    cutoff = datetime.now(timezone.utc) - timedelta(minutes=5)

    # RULE 1: Repeated failed logins
    if event.event_type == "authentication_failure":

        failures = db.query(Event).filter(
            Event.event_type == "authentication_failure",
            Event.source_ip == event.source_ip,
            Event.timestamp >= cutoff
        ).count()

        if event.source_ip and failures >= 5:

            if create_alert(
                db,
                event,
                "AUTH-001",
                "Possible Brute Force Attack",
                (
                    f"{failures} failed login attempts "
                    f"were detected from {event.source_ip} "
                    f"within five minutes."
                )
            ):

                alerts_created += 1

    # RULE 2: Suspicious web requests
    if event.event_type == "suspicious_web_request":

        if create_alert(
            db,
            event,
            "WEB-001",
            "Suspicious Web Request",
            (
                f"A suspicious web request was detected "
                f"from {event.source_ip or 'unknown IP'}. "
                f"Details: {event.description}"
            )
        ):

            alerts_created += 1

    # RULE 3: Database authentication failures
    if event.event_type == "database_authentication_failure":

        failures = db.query(Event).filter(
            Event.event_type == "database_authentication_failure",
            Event.source_ip == event.source_ip,
            Event.timestamp >= cutoff
        ).count()

        if event.source_ip and failures >= 3:

            if create_alert(
                db,
                event,
                "DB-001",
                "Repeated Database Authentication Failures",
                (
                    f"{failures} failed database login attempts "
                    f"were detected from {event.source_ip}."
                )
            ):

                alerts_created += 1

    return alerts_created
