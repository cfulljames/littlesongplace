ALTER TABLE users ADD COLUMN bgcolor TEXT;
ALTER TABLE users ADD COLUMN fgcolor TEXT;
ALTER TABLE users ADD COLUMN accolor TEXT;

PRAGMA user_version = 2;

