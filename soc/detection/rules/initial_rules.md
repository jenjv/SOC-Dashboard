# Initial SOC Detection Rules

## AUTH-001: Possible Brute Force Attack

- Event type: authentication_failure
- Condition: 5 or more failed login attempts
- Time window: 5 minutes
- Grouping: source IP
- Severity: High

## WEB-001: Suspicious Web Request

- Event type: suspicious_web_request
- Condition: Request contains suspicious patterns
- Examples:
  - SQL injection
  - Directory traversal
  - Script injection
- Severity: High

## DB-001: Database Authentication Failures

- Event type: database_authentication_failure
- Condition: 3 or more failed attempts
- Time window: 5 minutes
- Grouping: source IP
- Severity: High
