#!/bin/bash
# seed_db.sh - Script to populate MySQL with dummy data

DB_USER="appuser"
DB_PASS="apppass"
DB_HOST="db"
DB_NAME="async_reports"

echo "Waiting for MySQL to be ready..."
sleep 10

echo "Seeding database with dummy data..."

# Check if we can connect
docker exec async-reports-db mysql -u $DB_USER -p$DB_PASS -h $DB_HOST -e "SELECT 1" > /dev/null 2>&1

if [ $? -ne 0 ]; then
  echo "Error: Cannot connect to MySQL"
  exit 1
fi

# SQL commands to execute
SQL_COMMANDS="
USE $DB_NAME;

-- Check if users table has data, if not insert sample user
INSERT INTO users (username, email) 
SELECT 'testuser', 'test@example.com' 
WHERE NOT EXISTS (SELECT 1 FROM users WHERE username='testuser');

INSERT INTO users (username, email) 
SELECT 'demouser', 'demo@example.com' 
WHERE NOT EXISTS (SELECT 1 FROM users WHERE username='demouser');

-- Get user ID
SET @user_id = (SELECT id FROM users WHERE username='testuser' LIMIT 1);

-- Check current transaction count
SELECT COUNT(*) as 'Current Transactions' FROM transactions;

-- Insert 50,000 dummy transactions if table is empty
INSERT INTO transactions (user_id, amount, currency, status) 
SELECT 
  @user_id,
  ROUND(10 + RAND() * 9990, 2),
  ELT(FLOOR(RAND()*3)+1, 'USD', 'EUR', 'GBP'),
  ELT(FLOOR(RAND()*3)+1, 'COMPLETED', 'PENDING', 'COMPLETED')
FROM (
  SELECT 1 UNION SELECT 2 UNION SELECT 3 UNION SELECT 4 UNION SELECT 5
) t1,
(
  SELECT 1 UNION SELECT 2 UNION SELECT 3 UNION SELECT 4 UNION SELECT 5
) t2,
(
  SELECT 1 UNION SELECT 2 UNION SELECT 3 UNION SELECT 4 UNION SELECT 5
) t3,
(
  SELECT 1 UNION SELECT 2 UNION SELECT 3 UNION SELECT 4 UNION SELECT 5
) t4
LIMIT 50000;

-- Verify data
SELECT COUNT(*) as 'Total Transactions' FROM transactions;
SELECT COUNT(*) as 'Total Users' FROM users;
"

# Execute SQL
echo "$SQL_COMMANDS" | docker exec -i async-reports-db mysql -u $DB_USER -p$DB_PASS $DB_NAME

echo "✓ Database seeding complete!"
echo ""
echo "Data Summary:"
docker exec async-reports-db mysql -u $DB_USER -p$DB_PASS $DB_NAME -e "SELECT 'Users' as Type, COUNT(*) as Count FROM users UNION SELECT 'Transactions', COUNT(*) FROM transactions;"
