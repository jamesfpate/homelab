#!/bin/bash
set -e

# Check if the environment variables are set
if [ -z "$PG_USER" ] || [ -z "$PG_PASS" ]; then
    echo "❌ Error: Environment variables are not set"
    exit 1
fi

# Process template files with environment variables
envsubst < /docker-entrypoint-initdb.d/01-create-databases.sql > /docker-entrypoint-initdb.d/01-create-databases.processed.sql

# Check if the processed file exists
if [ ! -f /docker-entrypoint-initdb.d/01-create-databases.processed.sql ]; then
    echo "❌ Error: Processed file does not exist"
    exit 1
fi

