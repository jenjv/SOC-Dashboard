# SOC Event Collection

## Overview

Fluent Bit is used to collect security logs from the
project infrastructure and forward them to the SOC backend.

## Monitored Systems

VM1 - Nginx logs
VM2 - PostgreSQL logs
VM3 - TechStore and Juice Shop logs
VM4 - Linux system logs

## Collection Method

Fluent Bit monitors local log files and forwards
records through HTTP to the SOC backend.

## Destination

http://VM4_TAILSCALE_IP:8000/api/ingest

## Configuration

Each VM has its own Fluent Bit configuration.

The source_machine field identifies the originating VM.

## Testing

1. Generate a test log entry.
2. Check Fluent Bit service status.
3. Check Fluent Bit service logs.
4. Query the SOC backend.
5. Confirm the event appears in /api/events.

## Security

Do not commit ingestion tokens or credentials.
