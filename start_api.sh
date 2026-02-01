#!/bin/bash
# Startup script for Retraction Watch API

echo "=================================================="
echo "Retraction Watch API - Startup Script"
echo "=================================================="

# Check if database exists
if [ ! -f "api/retractions.db" ]; then
    echo "Database not found. Initializing database from CSV..."
    python -m api.database
    echo "Database initialized successfully."
else
    echo "Database already exists. Skipping initialization."
fi

echo ""
echo "Starting API server..."
echo "=================================================="
echo "API will be available at: http://localhost:8000"
echo "Swagger docs: http://localhost:8000/docs"
echo "ReDoc: http://localhost:8000/redoc"
echo "OpenAPI schema: http://localhost:8000/openapi.json"
echo "=================================================="
echo ""

# Start the server
uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
