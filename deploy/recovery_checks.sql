\set ON_ERROR_STOP on
BEGIN TRANSACTION READ ONLY;
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector') THEN
        RAISE EXCEPTION 'Restored database lacks pgvector';
    END IF;
    IF (SELECT count(*) FROM public.alembic_version) <> 1 THEN
        RAISE EXCEPTION 'Restored database must have one migration head';
    END IF;
    IF EXISTS (
        SELECT 1 FROM pg_constraint AS constraint_row
        JOIN pg_namespace AS namespace_row ON namespace_row.oid = constraint_row.connamespace
        WHERE namespace_row.nspname = 'public' AND NOT constraint_row.convalidated
    ) THEN
        RAISE EXCEPTION 'Restored constraints are not fully validated';
    END IF;
END $$;
ROLLBACK;