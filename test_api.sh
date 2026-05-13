#!/bin/bash

# Async Report API - Testing Script
# Usage: bash test_api.sh

API_URL="http://localhost:5000/api/reports"

echo "================================================"
echo "Async Report Export API - Testing Script"
echo "================================================"
echo ""

# Test 1: Health Check
echo "Test 1: Health Check"
echo "-------------------"
curl -s -X GET "$API_URL/health" | jq .
echo ""

# Test 2: Test Celery
echo "Test 2: Test Celery Connectivity"
echo "--------------------------------"
CELERY_RESPONSE=$(curl -s -X GET "$API_URL/test-celery")
echo "$CELERY_RESPONSE" | jq .
CELERY_TASK_ID=$(echo "$CELERY_RESPONSE" | jq -r '.task_id')
echo "Celery task ID: $CELERY_TASK_ID"
echo ""

# Test 3: Generate Report
echo "Test 3: Generate Report (50,000 rows)"
echo "------------------------------------"
GENERATE_RESPONSE=$(curl -s -X POST "$API_URL/generate" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": 1,
    "rows": 50000
  }')
echo "$GENERATE_RESPONSE" | jq .
TASK_ID=$(echo "$GENERATE_RESPONSE" | jq -r '.task_id')
echo "Task ID: $TASK_ID"
echo ""

# Test 4: Poll Status
echo "Test 4: Poll Report Status (polling every 2 seconds)"
echo "---------------------------------------------------"
MAX_POLLS=30
POLL_COUNT=0

while [ $POLL_COUNT -lt $MAX_POLLS ]; do
  STATUS_RESPONSE=$(curl -s -X GET "$API_URL/status/$TASK_ID")
  STATUS=$(echo "$STATUS_RESPONSE" | jq -r '.status')
  ROWS=$(echo "$STATUS_RESPONSE" | jq -r '.rows_processed')
  
  echo "Poll #$((POLL_COUNT + 1)): Status=$STATUS, Rows=$ROWS"
  
  if [ "$STATUS" = "COMPLETED" ] || [ "$STATUS" = "FAILED" ]; then
    echo ""
    echo "Final Status Response:"
    echo "$STATUS_RESPONSE" | jq .
    break
  fi
  
  POLL_COUNT=$((POLL_COUNT + 1))
  sleep 2
done

if [ "$STATUS" = "COMPLETED" ]; then
  echo ""
  echo "Test 5: Download Report"
  echo "----------------------"
  DOWNLOAD_PATH="/tmp/report_$TASK_ID.csv"
  curl -s -X GET "$API_URL/download/$TASK_ID" -o "$DOWNLOAD_PATH"
  echo "Downloaded to: $DOWNLOAD_PATH"
  echo "File size: $(du -h $DOWNLOAD_PATH | cut -f1)"
  echo "First 5 rows:"
  head -5 "$DOWNLOAD_PATH"
fi

echo ""
echo "Test 6: List All Reports"
echo "------------------------"
curl -s -X GET "$API_URL/list?user_id=1" | jq .
echo ""

echo "================================================"
echo "Testing Complete!"
echo "================================================"
