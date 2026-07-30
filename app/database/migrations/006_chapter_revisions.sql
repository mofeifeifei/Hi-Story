UPDATE chapters
SET memory_revision = revision
WHERE COALESCE(TRIM(memory_json), '') <> '';
