CREATE TABLE schema_migrations (
    version INTEGER PRIMARY KEY,
    filename VARCHAR(255) NOT NULL UNIQUE,
    checksum CHAR(64) NOT NULL,
    applied_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT ck_schema_migrations_version_positive CHECK (version > 0),
    CONSTRAINT ck_schema_migrations_checksum_sha256 CHECK (
        checksum ~ '^[0-9a-f]{64}$'
    )
);
