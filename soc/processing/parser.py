import json
import re


NGINX_PATTERN = re.compile(
    r'(?P<ip>\S+) \S+ \S+ '
    r'\[(?P<timestamp>.*?)\] '
    r'"(?P<method>\S+) (?P<path>\S+) [^"]*" '
    r'(?P<status>\d{3}) (?P<size>\S+)'
)


def parse_log(record):

    if isinstance(record, dict):

        message = (
            record.get("log")
            or record.get("message")
            or record.get("msg")
        )

        if isinstance(message, str):

            try:
                parsed = json.loads(message)

                if isinstance(parsed, dict):
                    return {**record, **parsed}

            except json.JSONDecodeError:
                pass

        return record

    if not isinstance(record, str):
        return {"message": str(record)}

    # Try JSON first
    try:

        parsed = json.loads(record)

        if isinstance(parsed, dict):
            return parsed

    except json.JSONDecodeError:
        pass

    # Try Nginx access log
    match = NGINX_PATTERN.search(record)

    if match:

        return {
            "source_ip": match.group("ip"),
            "timestamp": match.group("timestamp"),
            "method": match.group("method"),
            "path": match.group("path"),
            "http_status": int(match.group("status")),
            "message": record,
            "source_type": "nginx"
        }

    # PostgreSQL authentication failure
    if "password authentication failed" in record.lower():

        ip_match = re.search(
            r'(?<![\d.])(\d{1,3}(?:\.\d{1,3}){3})(?![\d.])',
            record
        )

        user_match = re.search(
            r'password authentication failed for user "([^"]+)"',
            record,
            re.IGNORECASE
        )

        return {
            "event_type": "database_authentication_failure",
            "source_ip": ip_match.group(1) if ip_match else None,
            "username": user_match.group(1) if user_match else None,
            "description": record,
            "message": record
        }

    # Generic fallback
    return {
        "message": record,
        "description": record
    }
