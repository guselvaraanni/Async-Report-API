-- Async Reports Database - Sample Data Script
-- Run this after services are up: docker exec async-reports-db mysql -u appuser -p async_reports < init_data.sql

USE async_reports;

-- Clear existing data (optional)
DELETE FROM transactions;
DELETE FROM reports;
DELETE FROM users;

-- Create sample users
INSERT INTO users (username, email) VALUES
  ('john_doe', 'john@example.com'),
  ('jane_smith', 'jane@example.com'),
  ('bob_johnson', 'bob@example.com');

-- Insert 50,000 dummy transactions
-- This uses a UNION to generate rows, adjust multiplier for different counts
INSERT INTO transactions (user_id, amount, currency, status, created_at)
SELECT 
  FLOOR(RAND() * 3) + 1 as user_id,
  ROUND(RAND() * 10000, 2) as amount,
  ELT(FLOOR(RAND() * 3) + 1, 'USD', 'EUR', 'GBP') as currency,
  ELT(FLOOR(RAND() * 4) + 1, 'PENDING', 'COMPLETED', 'FAILED', 'REFUNDED') as status,
  DATE_ADD(NOW(), INTERVAL -FLOOR(RAND() * 90) DAY) as created_at
FROM (
  SELECT 1 UNION SELECT 2 UNION SELECT 3 UNION SELECT 4 UNION SELECT 5
) t1, (
  SELECT 1 UNION SELECT 2 UNION SELECT 3 UNION SELECT 4 UNION SELECT 5
) t2, (
  SELECT 1 UNION SELECT 2 UNION SELECT 3 UNION SELECT 4 UNION SELECT 5
) t3, (
  SELECT 1 UNION SELECT 2 UNION SELECT 3 UNION SELECT 4 UNION SELECT 5
) t4
LIMIT 50000;

-- Verify data
SELECT 'Users created:' as info, COUNT(*) as count FROM users
UNION ALL
SELECT 'Transactions created:', COUNT(*) FROM transactions
UNION ALL
SELECT 'Reports created:', COUNT(*) FROM reports;

-- Show sample transactions
SELECT 'Sample transactions:' as info;
SELECT * FROM transactions LIMIT 10;
