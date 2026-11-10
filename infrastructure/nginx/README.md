# Nginx on SOC-NGINX

## Purpose

SOC-NGINX is the project's web entry point. Nginx runs on Ubuntu 26.04.1 LTS and will reverse proxy requests to TechStore and Juice Shop on SOC-APPLICATION.

## Current status

- Nginx version: 1.28.3
- Nginx is enabled and running.
- The current site serves `/health`, which returns `SOC-NGINX is up`.
- The application proxy routes are pending confirmation that the applications are running on SOC-APPLICATION.
- SOC-NGINX Tailscale IP: `100.91.198.37`

## Configuration

The project site configuration is in `sites-available/techstore`. On SOC-NGINX, the active copy is:

`/etc/nginx/sites-available/techstore`

It is enabled through:

`/etc/nginx/sites-enabled/techstore`

After application ports and routes are confirmed, configure Nginx to proxy:

- `/techstore/` to the TechStore FastAPI app on SOC-APPLICATION.
- `/juiceshop/` to Juice Shop on SOC-APPLICATION.

Confirm the upstream address, ports, and URL prefix behavior with the application owner before adding these routes.

## Install and operate

Install Nginx on Ubuntu:

```bash
sudo apt update
sudo apt install nginx
sudo systemctl enable --now nginx
