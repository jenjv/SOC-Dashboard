CREATE TABLE IF NOT EXISTS events (
    id SERIAL PRIMARY KEY,
    event_id VARCHAR(100) UNIQUE NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    source_machine VARCHAR(100) NOT NULL,
    event_type VARCHAR(100) NOT NULL,
    severity VARCHAR(20) NOT NULL,
    source_ip VARCHAR(100),
    destination_ip VARCHAR(100),
    username VARCHAR(255),
    description TEXT NOT NULL,
    status VARCHAR(30) DEFAULT 'new',
    raw_log JSONB,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS alerts (
    id SERIAL PRIMARY KEY,
    rule_id VARCHAR(100) NOT NULL,
    title VARCHAR(255) NOT NULL,
    severity VARCHAR(20) NOT NULL,
    description TEXT NOT NULL,
    source_machine VARCHAR(100) NOT NULL,
    source_ip VARCHAR(100),
    event_id VARCHAR(100),
    status VARCHAR(30) DEFAULT 'new',
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_alert_event
        FOREIGN KEY (event_id)
        REFERENCES events(event_id)
        ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_events_timestamp
ON events(timestamp);

CREATE INDEX IF NOT EXISTS idx_events_source_ip
ON events(source_ip);

CREATE INDEX IF NOT EXISTS idx_events_event_type
ON events(event_type);

CREATE INDEX IF NOT EXISTS idx_alerts_severity
ON alerts(severity);

CREATE INDEX IF NOT EXISTS idx_alerts_status
ON alerts(status);
