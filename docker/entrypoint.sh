#!/bin/bash
# Docker entrypoint script

set -e

# Initialize logs directory if needed
mkdir -p /app/logs
chmod 755 /app/logs

# Execute provided command or show help
exec "$@"
