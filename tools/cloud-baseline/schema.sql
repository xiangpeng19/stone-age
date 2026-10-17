-- Disposable isolated test database only. No users, passwords or account rows.
CREATE DATABASE IF NOT EXISTS sa CHARACTER SET utf8mb4 COLLATE utf8mb4_bin;
USE sa;
CREATE TABLE user_table (
  Name VARCHAR(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  Pass VARCHAR(64) NOT NULL,
  RegTime DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  Path VARCHAR(255) NOT NULL DEFAULT '',
  PRIMARY KEY (Name)
);
CREATE TABLE user_lock (
  Name VARCHAR(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  PRIMARY KEY (Name)
);

