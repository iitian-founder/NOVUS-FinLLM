#!/bin/bash
source venv/bin/activate

export DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib:/opt/anaconda3/lib:/usr/local/lib:$DYLD_FALLBACK_LIBRARY_PATH
export OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES

# Start Redis if not already running via Homebrew
if ! redis-cli ping > /dev/null 2>&1; then
    echo "Starting Redis..."
    brew services start redis
fi

echo "Starting RQ Worker..."
python3 worker.py > worker.log 2>&1 &

echo "Starting Flask Server on localhost:5001..."
python3 app.py > server.log 2>&1 &

echo "Services started! View frontend at http://localhost:5001/"
