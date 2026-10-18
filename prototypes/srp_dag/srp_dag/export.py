"""Export job DAG from snakemake workflow to json stdout
by patching snakemake.api.DAGApi.execute_workflow.

Usage:
    python -m srp_dag.export --cmd "snakemake -c 2 ..."

Params: `--cmd`
    the raw snakemake command should be passed to `--cmd` via shlex.quote

Output
    {"created_at": ..., "nodes": [...], "edges": [...]}

    where node: {
        "dag_id": int,
        "jobid": int,
        "rule_name": str,
        "group_id": str | None,
        "wildcards": dict,
        "input": list[str],
        "output": list[str],
        "log": list[str],
        "benchmark": list[str],
        "is_checkpoint": bool,
        "needrun": bool,
    }
    and edge: {
        "source": int,
        "target": int,
        "files": list[str],
    }
"""

from __future__ import annotations

import argparse
import contextlib
import json
import shlex
import sys
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from snakemake.workflow import Workflow
    from snakemake.dag import DAG
    from snakemake.jobs import Job


def _group_id(job: Job):
    group = getattr(job.rule, "_group", None)
    return group if isinstance(group, str) else None


def _node(dag: DAG, job: Job, dag_id: int):
    return {
        "dag_id": dag_id,
        "jobid": job.jobid,
        "rule_name": job.rule.name,
        "group_id": _group_id(job),
        "wildcards": dict(job.wildcards_dict or {}),
        "is_checkpoint": bool(getattr(job.rule, "is_checkpoint", False)),
        "needrun": bool(dag.needrun(job)),
        "output": [str(f) for f in job.output],
        "input": [str(f) for f in job.input],
        "log": [str(f) for f in job.log],
        "benchmark": [str(job.benchmark)] if job.benchmark is not None else [],
    }


def build_payload(workflow: Workflow):
    dag = workflow.dag
    if dag is None:
        return {}
    jobs = sorted(dag.jobs, key=lambda job: job.jobid)
    dag_ids = {job: i for i, job in enumerate(jobs)}
    nodes = [_node(dag, job, dag_ids[job]) for job in jobs]

    edges = []
    for job in jobs:
        for dep, files in dag.dependencies[job].items():
            edges.append(
                {
                    "source": dag_ids[dep],
                    "target": dag_ids[job],
                    "files": sorted(str(f) for f in files),
                }
            )

    return {"created_at": time.time(), "nodes": nodes, "edges": edges}


def _install():
    from snakemake import api as sm

    def patched_execute_workflow(self: sm.DAGApi, *args, **kwargs):
        wf = self.workflow_api._workflow
        wf._prepare_dag(
            forceall=wf.dag_settings.forceall,  # type: ignore
            ignore_incomplete=True,
            lock_warn_only=True,
        )
        wf._build_dag()
        _payload.update(build_payload(wf))
        return True

    sm.DAGApi.execute_workflow = patched_execute_workflow  # type: ignore
    _payload: dict = {}
    return _payload


def _snakemake_argv(cmd: str | None, rest: list[str]):
    if cmd is None:
        return rest
    tokens = shlex.split(cmd)
    if tokens and tokens[0].split("/")[-1] == "snakemake":
        tokens = tokens[1:]
    return tokens


def main(argv: list[str] | None = None):
    parser = argparse.ArgumentParser(prog="srp_dag.export")
    parser.add_argument("--cmd", default=None)
    args, rest = parser.parse_known_args(argv)

    snakemake_argv = _snakemake_argv(args.cmd, rest)
    _payload = _install()

    from snakemake.cli import main as snakemake_main

    real_stdout = sys.stdout
    code = 0
    try:
        with contextlib.redirect_stdout(sys.stderr):
            snakemake_main(snakemake_argv)
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else 1

    if code != 0 or not _payload:
        sys.exit(code or 1)

    real_stdout.write(json.dumps(_payload, default=str) + "\n")


if __name__ == "__main__":
    main()
