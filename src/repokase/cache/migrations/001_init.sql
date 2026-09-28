-- Repokase cache schema v1. Phase 2 tables are created now so later
-- milestones only add data, not structure.

CREATE TABLE account (
    id          INTEGER PRIMARY KEY,          -- GitHub user databaseId
    login       TEXT NOT NULL UNIQUE,
    name        TEXT,
    avatar_url  TEXT,
    profile_url TEXT,
    updated_at  TEXT NOT NULL
);

CREATE TABLE repo (
    account_id        INTEGER NOT NULL REFERENCES account(id) ON DELETE CASCADE,
    node_id           TEXT NOT NULL,
    database_id       INTEGER,
    owner             TEXT NOT NULL,
    name              TEXT NOT NULL,
    full_name         TEXT NOT NULL,
    description       TEXT,
    url               TEXT NOT NULL,
    visibility        TEXT NOT NULL,          -- PUBLIC | PRIVATE | INTERNAL
    is_archived       INTEGER NOT NULL DEFAULT 0,
    is_fork           INTEGER NOT NULL DEFAULT 0,
    is_template       INTEGER NOT NULL DEFAULT 0,
    is_mirror         INTEGER NOT NULL DEFAULT 0,
    primary_language  TEXT,
    stargazers        INTEGER NOT NULL DEFAULT 0,
    forks             INTEGER NOT NULL DEFAULT 0,
    watchers          INTEGER NOT NULL DEFAULT 0,
    open_issues       INTEGER NOT NULL DEFAULT 0,
    open_prs          INTEGER NOT NULL DEFAULT 0,
    default_branch    TEXT,
    license_spdx      TEXT,
    has_readme        INTEGER,                -- NULL = unknown (phase 2 health)
    disk_kb           INTEGER,
    viewer_permission TEXT,                   -- ADMIN | MAINTAIN | WRITE | TRIAGE | READ
    pushed_at         TEXT,
    created_at        TEXT,
    updated_at        TEXT,
    fetched_at        TEXT NOT NULL,
    PRIMARY KEY (account_id, node_id)
);
CREATE INDEX repo_full_name ON repo(full_name);

CREATE TABLE repo_topic (
    account_id INTEGER NOT NULL,
    repo_id    TEXT NOT NULL,
    topic      TEXT NOT NULL,
    PRIMARY KEY (account_id, repo_id, topic),
    FOREIGN KEY (account_id, repo_id) REFERENCES repo(account_id, node_id) ON DELETE CASCADE
);

-- Local, user-defined. Survive refreshes; assignments go when the repo does.
CREATE TABLE category (
    id         INTEGER PRIMARY KEY,
    name       TEXT NOT NULL UNIQUE COLLATE NOCASE,
    color_role TEXT,                          -- a Theme series key, never a hex value
    sort_order INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE repo_category (
    account_id  INTEGER NOT NULL,
    repo_id     TEXT NOT NULL,
    category_id INTEGER NOT NULL REFERENCES category(id) ON DELETE CASCADE,
    PRIMARY KEY (account_id, repo_id, category_id),
    FOREIGN KEY (account_id, repo_id) REFERENCES repo(account_id, node_id) ON DELETE CASCADE
);

CREATE TABLE workflow_run (
    id          INTEGER PRIMARY KEY,
    account_id  INTEGER NOT NULL,
    repo_id     TEXT NOT NULL,
    workflow_id INTEGER,
    name        TEXT,
    status      TEXT,
    conclusion  TEXT,
    event       TEXT,
    head_branch TEXT,
    run_number  INTEGER,
    created_at  TEXT,
    html_url    TEXT,
    fetched_at  TEXT NOT NULL,
    FOREIGN KEY (account_id, repo_id) REFERENCES repo(account_id, node_id) ON DELETE CASCADE
);
CREATE INDEX workflow_run_repo ON workflow_run(account_id, repo_id, created_at DESC);

CREATE TABLE sync_state (
    account_id   INTEGER NOT NULL,
    resource     TEXT NOT NULL,
    last_success TEXT,
    last_error   TEXT,
    etag         TEXT,
    PRIMARY KEY (account_id, resource)
);

CREATE TABLE setting (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL                       -- JSON
);

-- Phase 2 ------------------------------------------------------------------
-- Traffic is keyed by full_name, not node_id, so history survives the repo
-- leaving and re-entering the cache (e.g. access regained).
CREATE TABLE traffic_daily (
    full_name TEXT NOT NULL,
    day       TEXT NOT NULL,                  -- YYYY-MM-DD (UTC)
    kind      TEXT NOT NULL CHECK (kind IN ('views', 'clones')),
    count     INTEGER NOT NULL,
    uniques   INTEGER NOT NULL,
    PRIMARY KEY (full_name, day, kind)
);

CREATE TABLE traffic_referrer (
    full_name    TEXT NOT NULL,
    snapshot_day TEXT NOT NULL,
    referrer     TEXT NOT NULL,
    count        INTEGER NOT NULL,
    uniques      INTEGER NOT NULL,
    PRIMARY KEY (full_name, snapshot_day, referrer)
);

CREATE TABLE workflow (
    id           INTEGER PRIMARY KEY,
    account_id   INTEGER NOT NULL,
    repo_id      TEXT NOT NULL,
    name         TEXT,
    path         TEXT,
    state        TEXT,
    has_dispatch INTEGER NOT NULL DEFAULT 0,
    inputs_json  TEXT,
    FOREIGN KEY (account_id, repo_id) REFERENCES repo(account_id, node_id) ON DELETE CASCADE
);

CREATE TABLE health (
    account_id        INTEGER NOT NULL,
    repo_id           TEXT NOT NULL,
    computed_at       TEXT NOT NULL,
    flags_json        TEXT NOT NULL,
    alert_counts_json TEXT,
    PRIMARY KEY (account_id, repo_id),
    FOREIGN KEY (account_id, repo_id) REFERENCES repo(account_id, node_id) ON DELETE CASCADE
);
