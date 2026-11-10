import uuid
import re

from datetime import datetime, timezone

from .parser import parse_log


SUSPICIOUS_PATTERNS = [
    r"\.\./",
    r"union\s+select",
    r"<script",
    r"etc/passwd",
    r"or\s+1=1",
    r"wp-admin",
]


def normalize_event(record, default_source=None):

    data = parse_log(record)

    message = str(
        data.get("description")
        or data.get("message")
        or data.get("log")
        or ""
    )

    source = (
        data.get("source_machine")
        or default_source
        or "UNKNOWN"
    )

    source_ip = data.get("source_ip")

    event_type = data.get("event_type")

    # Identify failed authentication attempts
    if not event_type:

        if "password authentication failed" in message.lower():

            event_type = "database_authentication_failure"

        elif (
            "failed login" in message.lower()
            or "authentication failure" in message.lower()
            or "invalid password" in message.lower()
        ):

            event_type = "authentication_failure"

    # Identify suspicious HTTP requests
    if data.get("path"):

        path = str(data["path"])

        if any(
            re.search(pattern, path, re.IGNORECASE)
            for pattern in SUSPICIOUS_PATTERNS
        ):

            event_type = "suspicious_web_request"

    # Also inspect raw messages for suspicious patterns
    if not event_type or event_type == "unknown":

        if any(
            re.search(pattern, message, re.IGNORECASE)
            for pattern in SUSPICIOUS_PATTERNS
        ):

            event_type = "suspicious_web_request"

    if not event_type:
        event_type = "system_event"

    severity = data.get("severity")

    if not severity:

        severity = {
            "authentication_failure": "medium",
            "database_authentication_failure": "high",
            "suspicious_web_request": "high",
            "system_event": "low"
        }.get(event_type, "low")

    timestamp = data.get("timestamp")

    if timestamp:

        try:

            timestamp = datetime.fromisoformat(
                str(timestamp).replace("Z", "+00:00")
            )

            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=timezone.utc)

        except ValueError:

            timestamp = datetime.now(timezone.utc)

    else:

        timestamp = datetime.now(timezone.utc)

    return {

        "event_id": str(uuid.uuid4()),

        "timestamp": timestamp,

        "source_machine": source,

        "event_type": event_type,

        "severity": severity,

        "source_ip": source_ip,

        "destination_ip": data.get("destination_ip"),

        "username": data.get("username"),

        "description": (
            data.get("description")
            or message
            or "Security event received"
        ),

        "status": "new",

        "raw_log": data
    }
