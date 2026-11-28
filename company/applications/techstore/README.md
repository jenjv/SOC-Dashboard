# TechStore

TechStore is a sample electronics store application developed
for the SOC Dashboard project.

## Features

- Product listing and product details API
- User registration and login
- Password hashing using Argon2
- Shopping cart and order creation
- Structured JSON application logging
- FastAPI backend
- HTML, CSS, and JavaScript frontend

## Technology

- Python
- FastAPI
- SQLAlchemy
- PostgreSQL
- HTML, CSS, JavaScript

## Requirements

Install dependencies:

    cd backend
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt

## Database Configuration

Copy `.env.example` to `.env` and configure DATABASE_URL
with the project PostgreSQL connection details.

The database connection must be configured before
registration, login, and order operations can work.

## Running the Application

    cd backend
    source venv/bin/activate
    uvicorn main:app --host 0.0.0.0 --port 8000

## API Documentation

Once running, visit:

    http://localhost:8000/docs

## Logging

TechStore generates structured JSON application logs
including timestamps, severity levels, application name,
and event messages.
