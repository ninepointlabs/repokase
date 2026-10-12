-- Whether the repo's owner is an organization (vs. a user), for the sidebar's
-- organization list. Filled in by the next refresh.
ALTER TABLE repo ADD COLUMN owner_is_org INTEGER NOT NULL DEFAULT 0
