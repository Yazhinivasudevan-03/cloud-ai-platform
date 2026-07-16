-- Runs once on first MySQL container initialization (docker-entrypoint-initdb.d).
-- Creates the dedicated test databases alongside the primary application database
-- (which is created automatically from the MYSQL_DATABASE env var) and grants
-- the application user access to all of them.
--   cloud_ai_platform_test    - backend pytest suite (Base.metadata.create_all)
--   cloud_ai_platform_ml_test - ml-models pytest suite (own lightweight DDL)
CREATE DATABASE IF NOT EXISTS cloud_ai_platform_test
    CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE DATABASE IF NOT EXISTS cloud_ai_platform_ml_test
    CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

GRANT ALL PRIVILEGES ON cloud_ai_platform_test.* TO 'cloudai'@'%';
GRANT ALL PRIVILEGES ON cloud_ai_platform_ml_test.* TO 'cloudai'@'%';
FLUSH PRIVILEGES;
