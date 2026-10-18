"""Storage: workflow/rule/job/file + DAG snapshot."""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Optional

STATUS_RUNNING = "RUNNING"
STATUS_SUCCESS = "SUCCESS"
STATUS_ERROR = "ERROR"
STATUS_UNKNOWN = "UNKNOWN"

FILE_TYPES = ("INPUT", "OUTPUT", "LOG", "BENCHMARK")

SCHEMA = """
CREATE TABLE IF NOT EXISTS workflows (
    id TEXT PRIMARY KEY,
    snakefile TEXT,
    dryrun INTEGER NOT NULL DEFAULT 0,
    started_at REAL,
    updated_at REAL,
    end_time REAL,
    status TEXT NOT NULL DEFAULT 'UNKNOWN'
);
CREATE TABLE IF NOT EXISTS rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workflow_id TEXT NOT NULL,
    name TEXT NOT NULL,
    UNIQUE (workflow_id, name)
);
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workflow_id TEXT NOT NULL,
    jobid INTEGER NOT NULL,
    rule_name TEXT NOT NULL,
    rule_msg TEXT,
    wildcards TEXT,
    status TEXT NOT NULL DEFAULT 'UNKNOWN',
    threads INTEGER NOT NULL DEFAULT 0,
    started_at REAL,
    end_time REAL,
    reason TEXT,
    UNIQUE (workflow_id, jobid)
);
CREATE TABLE IF NOT EXISTS files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workflow_id TEXT NOT NULL,
    jobid INTEGER NOT NULL,
    path TEXT NOT NULL,
    file_type TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS errors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workflow_id TEXT NOT NULL,
    timestamp REAL,
    exception TEXT,
    message TEXT
);
CREATE INDEX IF NOT EXISTS idx_jobs_workflow ON jobs (workflow_id);
CREATE INDEX IF NOT EXISTS idx_jobs_started ON jobs (started_at);
CREATE INDEX IF NOT EXISTS idx_jobs_end ON jobs (end_time);
CREATE INDEX IF NOT EXISTS idx_workflows_started ON workflows (started_at);
CREATE INDEX IF NOT EXISTS idx_files_workflow ON files (workflow_id, jobid);
CREATE INDEX IF NOT EXISTS idx_files_path ON files (path);
"""


def connect(db_path: str | Path):
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=30.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 30000")
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


def _now():
    return time.time()


class Store:
    def __init__(self, db_path: str | Path, dryrun: bool):
        self.conn = connect(db_path)
        self.dryrun = dryrun

    def start_workflow(self, workflow_id: str, snakefile: str):
        now = _now()
        self.conn.execute(
            "INSERT OR REPLACE INTO workflows"
            "(id, snakefile, dryrun, started_at, updated_at, status) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (workflow_id, snakefile, int(self.dryrun), now, now, STATUS_RUNNING),
        )
        self.conn.commit()

    def _touch_rule(self, workflow_id: str, name: str):
        """Create a rule entry before add a job."""
        self.conn.execute(
            "INSERT INTO rules (workflow_id, name) VALUES (?, ?) "
            "ON CONFLICT (workflow_id, name) DO NOTHING",
            (workflow_id, name),
        )

    def job_info(
        self,
        workflow_id: str,
        jobid: int,
        rule_name: str,
        rule_msg: Optional[str],
        wildcards: Optional[dict],
        threads: int,
        reason: Optional[str],
        files: dict[str, list[str]],
    ):
        """will update table:
        - rules: ensure rule_name exists
        - jobs: for workflow_id/jobid, and other info
        - files: for workflow_id, jobid, path, directives(input/output/log)
        """

        self._touch_rule(workflow_id, rule_name)
        self.conn.execute(
            "INSERT INTO jobs"
            "(workflow_id, jobid, rule_name, rule_msg, wildcards, status, "
            " threads, started_at, reason) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT (workflow_id, jobid) DO UPDATE SET "
            " rule_name = excluded.rule_name, rule_msg = excluded.rule_msg, "
            " wildcards = excluded.wildcards, threads = excluded.threads, "
            " reason = excluded.reason",
            (
                workflow_id,
                jobid,
                rule_name,
                rule_msg,
                json.dumps(wildcards or {}, sort_keys=True),
                STATUS_RUNNING,
                threads,
                _now(),
                reason,
            ),
        )
        self.conn.execute(
            "DELETE FROM files WHERE workflow_id = ? AND jobid = ?",
            (workflow_id, jobid),
        )
        for file_type in FILE_TYPES:
            for path in files.get(file_type, []) or []:
                self.conn.execute(
                    "INSERT INTO files (workflow_id, jobid, path, file_type) "
                    "VALUES (?, ?, ?, ?)",
                    (workflow_id, jobid, path, file_type),
                )
        self.conn.commit()

    def job_started(self, workflow_id: str, jobid: int):
        self.conn.execute(
            "UPDATE jobs SET status = ?, started_at = ? "
            "WHERE workflow_id = ? AND jobid = ?",
            (STATUS_RUNNING, _now(), workflow_id, jobid),
        )
        self.conn.commit()

    def job_finished(self, workflow_id: str, jobid: int):
        self.conn.execute(
            "UPDATE jobs SET status = ?, end_time = ? "
            "WHERE workflow_id = ? AND jobid = ?",
            (STATUS_SUCCESS, _now(), workflow_id, jobid),
        )
        self.conn.commit()

    def job_error(self, workflow_id: str, jobid: int):
        self.conn.execute(
            "UPDATE jobs SET status = ?, end_time = ? "
            "WHERE workflow_id = ? AND jobid = ?",
            (STATUS_ERROR, _now(), workflow_id, jobid),
        )
        self.conn.commit()

    def add_error(
        self,
        workflow_id: str,
        exception: Optional[str],
        message: Optional[str] = None,
    ):
        self.conn.execute(
            "INSERT INTO errors (workflow_id, timestamp, exception, message) "
            "VALUES (?, ?, ?, ?)",
            (workflow_id, _now(), exception, message),
        )
        self.conn.commit()

    def has_error(self, workflow_id: str):
        row = self.conn.execute(
            "SELECT COUNT(*) AS c FROM jobs WHERE workflow_id = ? AND status = ?",
            (workflow_id, STATUS_ERROR),
        ).fetchone()
        if row["c"]:
            return True
        row = self.conn.execute(
            "SELECT COUNT(*) AS c FROM errors WHERE workflow_id = ?",
            (workflow_id,),
        ).fetchone()
        return bool(row["c"])

    def close_workflow(self, workflow_id: str):
        row = self.conn.execute(
            "SELECT COUNT(*) AS total, "
            "SUM(CASE WHEN status = ? THEN 1 ELSE 0 END) AS finished "
            "FROM jobs WHERE workflow_id = ?",
            (STATUS_SUCCESS, workflow_id),
        ).fetchone()
        total = row["total"] or 0
        finished = row["finished"] or 0
        if self.has_error(workflow_id):
            status = STATUS_ERROR
        elif total and finished >= total:
            status = STATUS_SUCCESS
        else:
            status = STATUS_UNKNOWN
        self.conn.execute(
            "UPDATE workflows SET status = ?, end_time = ?, updated_at = ? WHERE id = ?",
            (status, _now(), _now(), workflow_id),
        )
        self.conn.commit()

    def close(self):
        self.conn.close()


def job_key(rule_name: str, wildcards: Optional[dict]):
    return f"{rule_name}:{json.dumps(wildcards or {}, sort_keys=True, separators=(',', ':'))}"
