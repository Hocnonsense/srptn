"""Local snakemake logger plugin `srp-dag`

Writes snakemake run events to a separate SQLite (see srp_dag.store) for srptn to read.

Useage:
    PYTHONPATH=<prototypes/srp_dag> snakemake ... --logger srp-dag \
        --logger-srp-dag-db /path/to/run.db
"""

from dataclasses import dataclass, field
from logging import Handler, LogRecord
from pathlib import Path
from typing import TYPE_CHECKING

from snakemake_interface_logger_plugins.base import LogHandlerBase
from snakemake_interface_logger_plugins.settings import LogHandlerSettingsBase

from srp_dag import store

if TYPE_CHECKING:
    from snakemake_interface_logger_plugins.common import LogEvent


@dataclass
class LogHandlerSettings(LogHandlerSettingsBase):
    db: Path | None = field(
        default=None,
        metadata={
            "help": "Path to SQLite database file to write run events to. "
            "If not specified, defaults to .snakemake/log/srp_dag.db",
            "env_var": False,
            "required": False,
        },
    )


class LogHandler(LogHandlerBase):
    def __post_init__(self):
        Handler.__init__(self)
        settings: LogHandlerSettings = getattr(self, "settings")
        if settings.db is None:
            raise ValueError("Database path must be specified in settings")
        self.store = store.Store(settings.db, dryrun=self.common_settings.dryrun)
        self.workflow_id: str | None = None

    def _current(self):
        assert self.workflow_id
        return self.workflow_id

    @property
    def writes_to_stream(self):
        return False

    @property
    def writes_to_file(self):
        return False

    @property
    def has_filter(self):
        return True

    @property
    def has_formatter(self):
        return True

    @property
    def needs_rulegraph(self):
        return False

    def emit(self, record: LogRecord):
        event: LogEvent | None = getattr(record, "event", None)
        if event is None:
            return
        key = str(event).lower()
        handler = getattr(self, f"_on_{key}", None)
        if handler is None:
            return
        try:
            handler(record)
        except Exception:
            self.handleError(record)

    def _on_workflow_started(self, record: LogRecord):
        """
        >>> import snakemake.api
        >>> snakemake.api.DAGApi.execute_workflow

        logger.info(
            None,
            extra=dict(
                event=LogEvent.WORKFLOW_STARTED,
                workflow_id=uuid.uuid4(),
                snakefile=self.workflow_api.snakefile,
            ),
        )
        """

        self.workflow_id = str(getattr(record, "workflow_id"))
        snakefile = getattr(record, "snakefile", None)
        self.store.start_workflow(self.workflow_id, str(snakefile or ""))

    def _on_job_info(self, record: LogRecord):
        """
        >>> import snakemake.jobs
        >>> snakemake.jobs.Job.log_info

        logger.info(
            f" Rule: {self.rule.name}, Jobid: {self.dag.jobid(self)}",
            extra=dict(
                event=LogEvent.JOB_INFO,
                jobid=self.dag.jobid(self),
                rule_msg=self.message,
                rule_name=self.rule.name,
                # in dryrun, we don't want to display a decision whether local or not
                # since we don't know how the user wants to execute
                local=(
                    not self.dag.workflow.dryrun
                    and self.dag.workflow.is_local(self.rule)
                ),
                input=format_files(self.input, is_input=True),
                output=format_files(self.output, is_input=False),
                log=format_files(self.log, is_input=False),
                benchmark=benchmark,
                wildcards=self.wildcards_dict,
                reason=str(self.dag.reason(self)),
                resources=self.resources,
                priority=(
                    "highest"
                    if priority == JobExecutorInterface.HIGHEST_PRIORITY
                    else priority
                ),
                threads=self.threads,
                indent=indent,
                is_checkpoint=self.rule.is_checkpoint,
                printshellcmd=printshellcmd,
                is_handover=self.rule.is_handover,
                shellcmd=self.shellcmd,
            ),
        )
        """
        wid = self._current()
        jobid = getattr(record, "jobid", None)
        if not wid or jobid is None:
            return
        files = {
            "INPUT": list(getattr(record, "input", []) or []),
            "OUTPUT": list(getattr(record, "output", []) or []),
            "LOG": list(getattr(record, "log", []) or []),
        }
        benchmark = getattr(record, "benchmark", None)
        if benchmark:
            files["BENCHMARK"] = [benchmark]
        self.store.job_info(
            workflow_id=wid,
            jobid=jobid,
            rule_name=getattr(record, "rule_name", ""),
            rule_msg=getattr(record, "rule_msg", None),
            wildcards=dict(getattr(record, "wildcards", {}) or {}),
            threads=getattr(record, "threads", 0) or 0,
            reason=getattr(record, "reason", None),
            files=files,
        )

    def _on_job_started(self, record: LogRecord):
        """
        >>> import snakemake.scheduler
        >>> snakemake.scheduler.JobScheduler.schedule

        if run:
            if not self.dryrun:
                logger.info(
                    f"Execute {len(run)} jobs...",
                    extra=dict(
                        event=LogEvent.JOB_STARTED, jobs=[j.jobid for j in run]
                    ),
                )
        """

        wid = self._current()
        if not wid:
            return
        for jobid in getattr(record, "jobs", []) or []:
            if isinstance(jobid, int):
                self.store.job_started(wid, jobid)

    def _on_job_finished(self, record: LogRecord):
        """
        >>> import snakemake.scheduler
        >>> snakemake.scheduler.JobScheduler.schedule

        if self.print_progress:
            if job.is_group():
                for j in job:
                    logger.info(
                        f"Finished jobid: {j.jobid} (Rule: {j.rule.name})",
                        extra=dict(event=LogEvent.JOB_FINISHED, job_id=j.jobid),
                    )
            else:
                logger.info(
                    f"Finished jobid: {job.jobid} (Rule: {job.rule.name})",
                    extra=dict(event=LogEvent.JOB_FINISHED, job_id=job.jobid),
                )
            self.progress()
        """

        wid = self._current()
        jobid = getattr(record, "job_id", None)
        if not wid or jobid is None:
            return
        self.store.job_finished(wid, jobid)

    def _on_job_error(self, record: LogRecord):
        """
        >>> import snakemake.jobs
        >>> snakemake.jobs.Job.get_log_error_info

        return dict(
            rule_name=self.rule.name,
            rule_msg=msg,
            jobid=self.dag.jobid(self),
            input=format_files(self.input, is_input=True),
            output=format_files(self.output, is_input=False),
            log=format_files(self.log, is_input=False) + aux_logs,
            conda_env=conda_env_adress,
            container_img=self.container_img,
            aux=kwargs,
            indent=indent,
            shellcmd=self.shellcmd,
            event=LogEvent.JOB_ERROR,
        )
        """

        wid = self._current()
        jobid = getattr(record, "jobid", None)
        if not wid or jobid is None:
            return
        self.store.job_error(wid, jobid)

    def _on_error(self, record: LogRecord):
        """
        >>> import snakemake.exceptions
        >>> snakemake.exceptions.print_exception

        log_verbose_traceback(ex)
        logger.error(
            format_exception_to_string(ex, linemaps),
            extra=dict(event=LogEvent.ERROR, exception=ex.__class__.__name__),
        )
        """
        wid = self._current()
        if not wid:
            return
        self.store.add_error(
            wid,
            exception=getattr(record, "exception", None),
            message=record.getMessage(),
        )

    def close(self):
        wid = self._current()
        if wid:
            self.store.close_workflow(wid)
        self.store.close()
        super().close()
