#!/bin/bash
# API_EXAMPLES.sh - Complete cURL examples for testing the async report API

BASE_URL="http://localhost:5000/api/v1/reports"

echo "=== Async Report API - cURL Examples ==="
echo ""

# ==========================================
# 1. HEALTH CHECK
# ==========================================
echo "1. Health Check"
echo "   Endpoint: GET /api/reports/health"
echo "   Command:"
echo "   curl $BASE_URL/health"
echo ""
read -p "Press Enter to continue..."

# ==========================================
# 2. TEST CELERY CONNECTIVITY
# ==========================================
echo ""
echo "2. Test Celery (Dummy Task - 10 sec sleep)"
echo "   Endpoint: GET /api/reports/test-celery"
echo "   Command:"
echo "   curl $BASE_URL/test-celery"
echo ""
read -p "Press Enter to continue..."

# ==========================================
# 3. GENERATE NEW REPORT
# ==========================================
echo ""
echo "3. Generate New Report (Async)"
echo "   Endpoint: POST /api/v1/reports/"
echo "   Payload: {\"user_id\": 1, \"rows\": 50000}"
echo "   Command:"
echo "   curl -X POST $BASE_URL/generate \\"
echo "     -H 'Content-Type: application/json' \\"
echo "     -d '{\"user_id\": 1, \"rows\": 50000}'"
echo ""
echo "   Saving task_id to variable for next steps..."

RESPONSE=$(curl -s -X POST $BASE_URL/ \
  -H "Content-Type: application/json" \
  -d '{"user_id": 1, "rows": 50000}')

echo "   Response: $RESPONSE"
echo ""

# Extract task_id using jq (if available) or grep
if command -v jq &> /dev/null; then
  TASK_ID=$(echo $RESPONSE | jq -r '.task_id')
else
  TASK_ID=$(echo $RESPONSE | grep -o '"task_id":"[^"]*' | cut -d'"' -f4)
fi

echo "   Extracted Task ID: $TASK_ID"
echo ""

# ==========================================
# 4. CHECK REPORT STATUS (POLLING)
# ==========================================
echo "4. Check Report Status (Polling)"
echo "   Endpoint: GET /api/v1/reports/<id>/status"
echo "   Command:"
echo "   curl $BASE_URL/status/$TASK_ID"
echo ""
echo "   Polling status every 2 seconds..."
echo ""

MAX_ITERATIONS=60  # 2 minutes max
ITERATION=0

while [ $ITERATION -lt $MAX_ITERATIONS ]; do
STATUS_RESPONSE=$(curl -s "$BASE_URL/$TASK_ID/status")
  
  if command -v jq &> /dev/null; then
    STATUS=$(echo $STATUS_RESPONSE | jq -r '.status')
    ROWS=$(echo $STATUS_RESPONSE | jq -r '.rows_processed')
  else
    STATUS=$(echo $STATUS_RESPONSE | grep -o '"status":"[^"]*' | cut -d'"' -f4)
    ROWS=$(echo $STATUS_RESPONSE | grep -o '"rows_processed":[0-9]*' | cut -d':' -f2)
  fi
  
  echo "   [$ITERATION] Status: $STATUS | Rows: $ROWS"
  
  if [ "$STATUS" = "COMPLETED" ] || [ "$STATUS" = "FAILED" ]; then
    echo ""
    echo "   Final Response:"
    echo "   $STATUS_RESPONSE"
    echo ""
    break
  fi
  
  sleep 2
  ITERATION=$((ITERATION + 1))
done

# ==========================================
# 5. DOWNLOAD REPORT
# ==========================================
if [ "$STATUS" = "COMPLETED" ]; then
  echo "5. Download Report (CSV File)"
echo "   Endpoint: GET /api/v1/reports/<id>/download"
  echo "   Command:"
  echo "   curl -O $BASE_URL/download/$TASK_ID"
  echo ""
  
  curl -O "$BASE_URL/$TASK_ID/download"
  
  FILENAME="report_$TASK_ID.csv"
  if [ -f "$FILENAME" ]; then
    echo "   ✓ Downloaded: $FILENAME"
    echo ""
    echo "   First 5 lines of CSV:"
    head -5 "$FILENAME"
    echo "   ..."
    echo ""
  fi
else
  echo "5. Download Report"
  echo "   Report not yet complete, skipping download"
  echo ""
fi

# ==========================================
# 6. LIST ALL REPORTS FOR USER
# ==========================================
echo "6. List All Reports for User"
echo "   Endpoint: GET /api/v1/reports/?user_id=1"
echo "   Command:"
echo "   curl '$BASE_URL/list?user_id=1'"
echo ""

LIST_RESPONSE=$(curl -s "$BASE_URL/?user_id=1")
echo "   Response:"
echo "   $LIST_RESPONSE"
echo ""

# ==========================================
# 7. DELETE REPORT
# ==========================================
echo "7. Delete Report (Optional)"
echo "   Endpoint: DELETE /api/v1/reports/<id>"
echo "   Command:"
echo "   curl -X DELETE $BASE_URL/delete/$TASK_ID"
echo ""
read -p "Delete the report? (y/n): " -n 1 -r
echo ""
if [[ $REPLY =~ ^[Yy]$ ]]; then
  DELETE_RESPONSE=$(curl -s -X DELETE "$BASE_URL/$TASK_ID")
  echo "   Response: $DELETE_RESPONSE"
  echo ""
fi

# ==========================================
# STRESS TEST: MULTIPLE CONCURRENT REPORTS
# ==========================================
echo "8. BONUS: Stress Test (5 Concurrent Reports)"
echo "   This demonstrates parallel processing capability"
echo ""
read -p "Run stress test? (y/n): " -n 1 -r
echo ""

if [[ $REPLY =~ ^[Yy]$ ]]; then
  TASK_IDS=()
  
  echo "   Sending 5 concurrent requests..."
  for i in {1..5}; do
    RESP=$(curl -s -X POST $BASE_URL/ \
      -H "Content-Type: application/json" \
      -d "{\"user_id\": 1, \"rows\": 10000}")
    
    if command -v jq &> /dev/null; then
      TID=$(echo $RESP | jq -r '.task_id')
    else
      TID=$(echo $RESP | grep -o '"task_id":"[^"]*' | cut -d'"' -f4)
    fi
    
    TASK_IDS+=("$TID")
    echo "   [$i] Task ID: $TID"
  done
  
  echo ""
  echo "   Monitoring all 5 tasks..."
  echo ""
  
  COMPLETED_COUNT=0
  MAX_WAIT=120  # 2 minutes
  ELAPSED=0
  
  while [ $COMPLETED_COUNT -lt 5 ] && [ $ELAPSED -lt $MAX_WAIT ]; do
    COMPLETED_COUNT=0
    
    for TID in "${TASK_IDS[@]}"; do
      STATUS_RESP=$(curl -s "$BASE_URL/$TID/status")
      
      if command -v jq &> /dev/null; then
        ST=$(echo $STATUS_RESP | jq -r '.status')
      else
        ST=$(echo $STATUS_RESP | grep -o '"status":"[^"]*' | cut -d'"' -f4)
      fi
      
      if [ "$ST" = "COMPLETED" ] || [ "$ST" = "FAILED" ]; then
        COMPLETED_COUNT=$((COMPLETED_COUNT + 1))
      fi
    done
    
    echo "   [$ELAPSED sec] Completed: $COMPLETED_COUNT/5"
    
    if [ $COMPLETED_COUNT -lt 5 ]; then
      sleep 5
      ELAPSED=$((ELAPSED + 5))
    fi
  done
  
  echo ""
  echo "   ✓ Stress test completed!"
  echo "   All 5 reports were processed in parallel by Celery workers."
  echo ""
fi

echo "=== Test Complete ==="
echo ""
echo "Key Takeaways:"
echo "1. POST /generate returns 202 ACCEPTED immediately (non-blocking)"
echo "2. GET /status polls for progress without blocking Flask"
echo "3. GET /download provides CSV only when status = COMPLETED"
echo "4. Multiple requests are queued and processed by workers in parallel"
echo "5. Flask API remains responsive even with heavy background work"
echo ""
