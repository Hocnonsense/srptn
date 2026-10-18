"""Connect with snakemake via srp-dag logger plugin

Only communicate via cmd and files, currently no imports

- `run_with_logger`: 设置 PYTHONPATH/cwd,并只在原命令后追加 logger 参数;
- `build_dag`: 阻塞调用 `python -m srp_dag.export --cmd "<cmd>"`,返回 DAG(纯 stdout);
- `store_topology` / `load_latest_topology`: 原样写入 DAG,按拓扑签名去重到 `meta/dags/`;
- `logger_jobs` / `update_jobs`: 读取 logger SQLite,把每个 job 的状态合并进 DAG;
"""

import json
import os
import sqlite3
import subprocess
import sys
from copy import deepcopy
from pathlib import Path
from typing import TYPE_CHECKING

import polars as pl
import streamlit as st

if TYPE_CHECKING:
    from .data.workspace import Workspace

PLUGIN_DIR = Path(__file__).resolve().parents[3] / "prototypes" / "srp_dag"
DB_RELPATH = Path(".snakemake") / "log" / "srp_dag.db"
DAG_DIR = "dags"

STATUS_RUNNING = "RUNNING"
STATUS_SUCCESS = "SUCCESS"
STATUS_ERROR = "ERROR"
STATUS_PENDING = "PENDING"

MIN_REBUILT_JOBS = 1000
HISTORY_FACTOR = 5
"""If the logger has to read more than this factor times the number of jobs in the DAG,
It means that the DAG is too old,
should rebuild the dag so not need to read too many jobs from the logger DB.
"""


def _job_key(rule_name: str, wildcards: dict | None):
    return (
        f"{rule_name}:"
        f"{json.dumps(wildcards or {}, sort_keys=True, separators=(',', ':'))}"
    )


def _outputs_exist(node: dict, data_path: Path):
    outputs = node.get("output") or []
    if not outputs:
        return False
    base = Path(data_path)
    for path in outputs:
        file = Path(path)
        if not (file if file.is_absolute() else base / file).exists():
            return False
    return True


def strip_topology(dag: dict):
    """Keep structural fields only (drop jobid / needrun) for comparison."""
    nodes = [
        {
            "dag_id": node["dag_id"],
            "rule_name": node["rule_name"],
            "wildcards": node.get("wildcards", {}),
            "is_checkpoint": node.get("is_checkpoint", False),
            "output": node.get("output", []),
            "input": node.get("input", []),
            "log": node.get("log", []),
            "benchmark": node.get("benchmark", []),
        }
        for node in dag.get("nodes", [])
    ]
    edges = [
        {
            "source": edge["source"],
            "target": edge["target"],
            "files": edge.get("files", []),
        }
        for edge in dag.get("edges", [])
    ]
    return {"nodes": nodes, "edges": edges}


def _node_signature(node: dict):
    payload = {
        "rule_name": node["rule_name"],
        "wildcards": node.get("wildcards", {}),
        "is_checkpoint": node.get("is_checkpoint", False),
        "output": node.get("output", []),
        "input": node.get("input", []),
        "log": node.get("log", []),
        "benchmark": node.get("benchmark", []),
    }
    return json.dumps(payload, sort_keys=True, default=str)


def _signature(dag: dict):
    topology = strip_topology(dag)
    nodes = topology.get("nodes", [])
    signatures = {node["dag_id"]: _node_signature(node) for node in nodes}
    edges = sorted(
        json.dumps(
            [
                signatures.get(edge.get("source")),
                signatures.get(edge.get("target")),
                sorted(edge.get("files", [])),
            ],
            sort_keys=True,
            default=str,
        )
        for edge in topology.get("edges", [])
    )
    return json.dumps(
        {"nodes": sorted(signatures.values()), "edges": edges}, sort_keys=True
    )


def _load(path: Path | None):
    if path is None:
        return None
    try:
        dag = json.loads(Path(path).read_text())
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(dag, dict) or "nodes" not in dag:  # invalid DAG
        return None
    return dag


def _write(path: Path, payload: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(payload)
    tmp.replace(path)


class DAGTracker:
    """DAG/status tracker for one analysis.

    Holds the analysis address, the DAG topology directory, a lazy read-only
    logger DB connection, and exposes the in-memory DAG via
    ``st.session_state[f"{address}-dag"]``.
    """

    def __init__(self, workspace: Workspace):
        self.address = workspace.address
        self.data_path = workspace.data_path
        self.dag_basepath = workspace.meta_path / DAG_DIR
        self._conn: sqlite3.Connection | None = None
        self.stale = False
        """According to the last logger query,
        the DAG is too old and should be rebuilt.
        """
        self.workflow_id: str | None = None
        """The latest workflow ID from the logger DB"""
        self.running = False
        """Whether the latest workflow is still running"""

    @property
    def _key(self):
        return f"{self.address}-dag"

    @property
    def _auto_failed_key(self):
        return f"{self._key}-auto-failed"

    @property
    def dag(self) -> dict | None:
        return st.session_state.get(self._key)

    @dag.setter
    def dag(self, value: dict):
        st.session_state[self._key] = value

    @property
    def conn(self):
        if self._conn is None:
            from .utils.db import Database

            _db = Database(self.data_path / DB_RELPATH)
            self._conn = _db.readonly()
        return self._conn

    def close(self):
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    @property
    def topology_files(self):
        for file in Path(self.dag_basepath).glob("topology.*.json"):
            try:
                index = int(file.stem.rsplit(".", 1)[-1])
            except ValueError:
                index = -1
            yield index, file

    def attach_logger(self, snakemake_command: str):
        """Prepare the command with cwd/PYTHONPATH and the logger flags."""
        return (
            f'export PYTHONPATH="{PLUGIN_DIR}:$PYTHONPATH"; '
            f'cd "{self.data_path}" && {snakemake_command} '
            f'--logger srp-dag --logger-srp-dag-db "{self.data_path / DB_RELPATH}"'
        )

    def build_from(self, snakemake_command: str) -> dict | None:
        """Blocking CLI call; returns the DAG from stdout (no writes)."""
        env = dict(os.environ)
        env["PYTHONPATH"] = f"{PLUGIN_DIR}:{env.get('PYTHONPATH', '')}"

        result = subprocess.run(
            [sys.executable, "-m", "srp_dag.export", "--cmd", snakemake_command],
            cwd=str(self.data_path),
            env=env,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return None
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError:
            return None

    def build_and_store(self, command: str):
        """Build, persist, and make the accepted DAG the current one.
        Mark if failed
        """
        dag = self.build_from(command)
        if dag:
            effective = self.store(dag)
            if effective:
                st.session_state.pop(self._auto_failed_key, None)
                self.dag = effective
                return effective
        st.session_state[self._auto_failed_key] = True

    def store(self, dag: dict):
        """Persist the DAG when appropriate; return the DAG for this session.

        Same topology:
        - older/equal created_at -> keep the stored DAG;
        - not stale -> use the fresh DAG in memory without touching disk;
        - stale -> read the last two files:
          overwrite the latest when it is a duplicate of the previous one,
          otherwise create a new version.
        Different topology -> create a new version.
        """
        created_at = dag.get("created_at")
        if created_at is None:
            return None
        files = sorted(self.topology_files)
        index, file = files[-1] if files else (-1, None)
        last = _load(file)
        payload = json.dumps(dag, ensure_ascii=False, default=str)
        if last is not None:
            signature = _signature(dag)
            if _signature(last) == signature:
                old_created = last.get("created_at")
                if old_created is not None and created_at <= old_created:
                    return last
                if not self.stale:
                    return dag
                duplicate = False
                if len(files) >= 2:
                    old = _load(files[-2][1])
                    duplicate = bool(old) and _signature(old) == signature
                if duplicate and file:
                    _write(file, payload)
                    return dag
        path = self.dag_basepath / f"topology.{index + 1}.json"
        _write(path, payload)
        return dag

    def logger_jobs(self):
        """Get the latest job info from the logger DB, keyed by rule_name:wildcards.
        Returns None if the DB is not readable.
        Inform stale if too many jobs after the last DAG created
        """
        self.stale = False
        self.running = False
        self.workflow_id = None
        conn = self.conn
        if conn is None:
            return None
        dag = self.dag
        since = dag.get("created_at") if dag else None
        if since is None:
            where, params = "", ()
        else:
            where = (
                "WHERE j.started_at >= ? OR j.end_time >= ? "
                "OR (j.status = ? AND w.status = ? AND w.end_time IS NULL)"
            )
            params = (since, since, STATUS_RUNNING, STATUS_RUNNING)
        total_jobs = sum(1 for n in (dag or {}).get("nodes", []) if "rule_name" in n)
        limit = max(total_jobs * HISTORY_FACTOR, MIN_REBUILT_JOBS)
        try:
            workflow = conn.execute(
                "SELECT id, status, end_time FROM workflows "
                "ORDER BY COALESCE(started_at, 0) DESC, rowid DESC LIMIT 1"
            ).fetchone()
            if workflow is not None:
                self.workflow_id = workflow["id"]
                self.running = (
                    workflow["status"] == STATUS_RUNNING
                    and workflow["end_time"] is None
                )

            jobs: dict[str, dict] = {}
            job_rows = conn.execute(
                "SELECT j.* FROM jobs j JOIN workflows w ON w.id = j.workflow_id "
                f"{where} "
                "ORDER BY COALESCE(w.started_at, 0) DESC, w.rowid DESC, "
                "j.jobid DESC LIMIT ?",
                (*params, limit + 1),
            ).fetchall()
            if not job_rows:
                return jobs

            self.stale = bool(total_jobs) and len(job_rows) > limit
            for row in job_rows:
                wildcards = json.loads(row["wildcards"] or "{}")
                key = _job_key(row["rule_name"], wildcards)
                if key in jobs:
                    continue
                jobs[key] = {
                    "rule_name": row["rule_name"],
                    "wildcards": wildcards,
                    "status": row["status"],
                    "workflow_id": row["workflow_id"],
                    "threads": row["threads"],
                    "reason": row["reason"],
                    "started_at": row["started_at"],
                    "end_time": row["end_time"],
                }
            return jobs
        except sqlite3.Error:
            self.close()
            self.stale = False
            self.running = False
            self.workflow_id = None
            return None

    def update_jobs(self, dag: dict):
        """Return a copy of ``dag`` with per-node status and a progress summary.

        ``current`` contains only jobs logged after the DAG's ``created_at``,
        so based on node's build-time ``needrun``, the logger overrides it:
        - RUNNING/SUCCESS/ERROR of job["status"]
        - not needrun (done)
        - needrun (pending)
        - output existence
        - pending.
        """

        result = deepcopy(dag)
        jobs = self.logger_jobs() or {}
        counts = {
            STATUS_SUCCESS: 0,
            STATUS_PENDING: 0,
            STATUS_RUNNING: 0,
            STATUS_ERROR: 0,
        }
        total = 0

        for node in result.get("nodes", []):
            if "rule_name" not in node:
                continue
            job = jobs.get(_job_key(node["rule_name"], node.get("wildcards", {})))
            needrun = node.get("needrun")

            if job and job["status"] in counts:
                status = job["status"]
            elif needrun is False:
                status = STATUS_SUCCESS
            elif needrun is True:
                status = STATUS_PENDING
            elif _outputs_exist(node, self.data_path):
                status = STATUS_SUCCESS
            else:
                status = STATUS_PENDING

            node["status"] = status
            if job:
                node["started_at"] = job.get("started_at")
                node["end_time"] = job.get("end_time")
                node["threads"] = job.get("threads")
                node["reason"] = job.get("reason")
            counts[status] += 1
            total += 1

        result["progress"] = {
            "total": total,
            "done": counts[STATUS_SUCCESS],
            "pending": counts[STATUS_PENDING],
            "running": counts[STATUS_RUNNING],
            "failed": counts[STATUS_ERROR],
        }
        return result

    def refresh(self, command: str | None = None, *, rebuild: bool = False):
        """Merge logger status;
        rebuild exactly one time automatically when the history is stale."""
        if command and (rebuild or not self.dag):
            if not self.build_and_store(command) and rebuild:
                return  # failed to rebuild, report the bad news
        if not self.dag:
            return
        self.dag = self.update_jobs(self.dag)

        if (
            self.stale
            and (not rebuild and command)
            and not st.session_state.get(self._auto_failed_key, False)
        ):
            dag = self.build_and_store(command)
            if dag:
                self.dag = self.update_jobs(dag)
        return self.dag

    def files_frame(self):
        dag = self.dag or {}
        rows = []
        for node in dag.get("nodes", []):
            if "rule_name" not in node:
                continue
            wildcards = json.dumps(node.get("wildcards", {}), sort_keys=True)
            for path in node.get("output", []):
                rows.append(
                    {
                        "path": path,
                        "rule_name": node["rule_name"],
                        "wildcards": wildcards,
                        "status": node.get("status", STATUS_PENDING),
                    }
                )
        return pl.DataFrame(rows)
