CREATE EXTENSION pg_trgm;

CREATE TABLE IF NOT EXISTS pessoa (
    id VARCHAR(36),
    apelido VARCHAR(32) CONSTRAINT ID_PK PRIMARY KEY,
    nome VARCHAR(100),
    nascimento CHAR(10),
    stack VARCHAR(1024),
    search TEXT GENERATED ALWAYS AS (
      apelido || ' ' || nome || ' ' || stack
  ) STORED
);


CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_search ON pessoa USING GIST (search GIST_TRGM_OPS(SIGLEN=64));
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_id ON pessoa (id);