# SOC Backend

## Overview

The SOC backend provides the central API for the
Security Operations Center.

It receives normalized security events, stores events
and alerts in PostgreSQL, executes detection rules,
and provides information through REST API endpoints.

## Location

VM4 - SOC-CORE

## Technologies

- Python
- FastAPI
- SQLAlchemy
- PostgreSQL
- Pydantic

## Installation

1. Create a Python virtual environment.
2. Activate the environment.
3. Install requirements.txt.
4. Configure the .env file.
5. Configure the SOC PostgreSQL database.

## Run

From the repository root:

uvicorn soc.backend.main:app --host 0.0.0.0 --port 8000

## API Documentation

http://VM4_IP:8000/docs

## Endpoints

GET /api/events
GET /api/alerts
GET /api/alerts/{id}
GET /api/stats
PATCH /api/alerts/{id}
POST /api/ingest

## Dependencies

- SOC PostgreSQL database
- Event processing system
- Detection engine
- Event collection agents
