CREATE EXTENSION pg_trgm;

CREATE TABLE IF NOT EXISTS people (
    id VARCHAR(36),
    name VARCHAR(100),
    nick VARCHAR(32) CONSTRAINT ID_PK PRIMARY KEY,
    birth_date CHAR(10),
    stack VARCHAR(1024),
    search TEXT GENERATED ALWAYS AS (
      name || ' ' || nick || ' ' || stack
  ) STORED
);


CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_search ON People USING GIST (search GIST_TRGM_OPS(SIGLEN=64));
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_id ON People (id);