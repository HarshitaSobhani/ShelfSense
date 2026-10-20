-- Extra database used by the backend test-suite. Runs once when the postgres volume is first created.
CREATE DATABASE shelfsense_test OWNER shelfsense;
\connect shelfsense_test
CREATE EXTENSION IF NOT EXISTS vector;
