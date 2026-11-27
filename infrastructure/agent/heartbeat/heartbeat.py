#!/usr/bin/env python3
import json
import os
import sys
from urllib.request import Request, urlopen

CORE_URL = "http://100.104.68.114:8000/api/hosts/heartbeat"
ALLOWED_HOSTS = {"SOC-APPLICATION", "SOC-NGINX"}

def main():
    if len(sys.argv) != 2 or sys.argv[1] not in ALLOWED_HOSTS:
        raise SystemExit("Provide SOC-APPLICATION or SOC-NGINX")

    token = os.environ.get("SOC_INGEST_TOKEN")
    if not token:
        raise SystemExit("SOC_INGEST_TOKEN is missing")

    body = json.dumps({"source_machine": sys.argv[1]}).encode()
    request = Request(
        CORE_URL,
        data=body,
        headers={
            "Content-Type": "application/json",
            "X-Ingest-Token": token,
        },
        method="POST",
    )
    with urlopen(request, timeout=5) as response:
        response.read()
        if response.status != 200:
            raise SystemExit(f"Core returned HTTP {response.status}")

if __name__ == "__main__":
    main()
