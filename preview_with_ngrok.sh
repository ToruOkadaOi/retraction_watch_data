#!/bin/bash
# Quick preview testing with ngrok

set -e

echo "======================================================"
echo "Retraction Watch API - Preview URL Setup"
echo "======================================================"
echo ""

# Check if ngrok is installed
if ! command -v ngrok &> /dev/null; then
    echo "❌ ngrok is not installed."
    echo ""
    echo "Please install ngrok:"
    echo "  macOS:  brew install ngrok/ngrok/ngrok"
    echo "  Linux:  https://ngrok.com/download"
    echo ""
    echo "Or visit: https://ngrok.com/download"
    exit 1
fi

echo "✅ ngrok is installed"
echo ""

# Check if API is already running
if curl -s http://localhost:8000/ > /dev/null 2>&1; then
    echo "✅ API is already running on http://localhost:8000"
else
    echo "Starting API server..."
    ./start_api.sh &
    API_PID=$!
    
    # Wait for API to start
    echo "Waiting for API to start..."
    for i in {1..30}; do
        if curl -s http://localhost:8000/ > /dev/null 2>&1; then
            echo "✅ API started successfully"
            break
        fi
        sleep 1
    done
fi

echo ""
echo "======================================================"
echo "Starting ngrok tunnel..."
echo "======================================================"
echo ""

# Start ngrok
echo "Creating public URL for http://localhost:8000"
echo ""
echo "📱 Your preview URL will appear below:"
echo "   (Press Ctrl+C to stop)"
echo ""
echo "📊 Web Interface: http://127.0.0.1:4040"
echo ""

ngrok http 8000
