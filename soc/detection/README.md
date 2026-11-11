# SOC Detection Engine

## Overview

The detection engine evaluates normalized events
against predefined security rules.

## Initial Rules

AUTH-001: Possible brute-force attack

WEB-001: Suspicious web request

DB-001: Repeated database authentication failures

## Alert Storage

Detected incidents are stored in the SOC PostgreSQL
database and exposed through the SOC backend API.

## Future Improvements

- Additional detection rules
- Improved alert correlation
- Configurable detection thresholds
- Detection of unusual system activity
