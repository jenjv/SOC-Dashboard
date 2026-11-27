# SOC Dashboard Demo Runbook

## Lab layout

- **Core:** SOC API, event storage, alert processing, and dashboard.
- **Nginx:** company web entry point and access-log collection.
- **Application:** TechStore API, Juice Shop lab app, and application-log collection.
- **Database:** PostgreSQL and database monitoring agent.

## Before the demo

1. Connect the presenter’s computer to the project Tailscale network.
2. On Core, confirm `soc-backend.service` and `soc-dashboard-frontend.service` are active.
3. Open the dashboard at `http://<SOC-CORE-TAILSCALE-IP>:5173/`.
4. Confirm the monitored hosts show recent status. The dashboard refreshes every 30 seconds.

## Walkthrough

1. Show the monitored hosts and recent event and alert panels.
2. Open TechStore through the Nginx entry point and show the products page.
3. Perform a normal test action, such as loading products or placing a test order.
4. Generate only an authorized, controlled lab event, then show it arriving in the SOC dashboard.
5. Open the event or alert details and explain its host, time, severity, and status.

## Status meaning and safety

- A host is shown online when Core has recent agent data; this is a lab heartbeat/telemetry signal, not a full check of every service on that host.
- Keep the lab on the private Tailscale network for the demo.
- Juice Shop is intentionally vulnerable. Do not expose it to the public internet.
- Never commit passwords, ingestion tokens, or private keys.
