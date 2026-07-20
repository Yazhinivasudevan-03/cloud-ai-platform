-- Runs once on first MySQL container initialization (docker-entrypoint-initdb.d).
-- Creates the dedicated test databases alongside the primary application database
-- (which is created automatically from the MYSQL_DATABASE env var) and grants
-- the application user access to all of them.
--   cloud_ai_platform_test    - backend pytest suite (Base.metadata.create_all)
--   cloud_ai_platform_ml_test - ml-models pytest suite (own lightweight DDL)
--   cloud_ai_auth             - login credentials only (users/roles/user_roles),
--                               separate from the main application database
--                               (see docs/PHASE_13.md) - not auto-created by
--                               MYSQL_DATABASE since it's a second database
--   cloud_ai_auth_test        - same, for the backend pytest suite
CREATE DATABASE IF NOT EXISTS cloud_ai_platform_test
    CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE DATABASE IF NOT EXISTS cloud_ai_platform_ml_test
    CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE DATABASE IF NOT EXISTS cloud_ai_auth
    CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE DATABASE IF NOT EXISTS cloud_ai_auth_test
    CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

GRANT ALL PRIVILEGES ON cloud_ai_platform_test.* TO 'cloudai'@'%';
GRANT ALL PRIVILEGES ON cloud_ai_platform_ml_test.* TO 'cloudai'@'%';
GRANT ALL PRIVILEGES ON cloud_ai_auth.* TO 'cloudai'@'%';
GRANT ALL PRIVILEGES ON cloud_ai_auth_test.* TO 'cloudai'@'%';
FLUSH PRIVILEGES;
