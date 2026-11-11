# SOC Event Processing

## Overview

The processing system parses incoming raw logs
and normalizes them into the agreed SOC event schema.

## Files

parser.py:
Identifies and extracts information from different
log formats.

normalizer.py:
Converts parsed information into a common event format.

## Supported Sources

- Nginx
- PostgreSQL
- TechStore application
- Linux system logs

## Output

Normalized security events containing:

- event_id
- timestamp
- source_machine
- event_type
- severity
- source_ip
- description
- status
