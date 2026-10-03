import json
import shutil
from dataclasses import dataclass
from pathlib import Path

import polars as pl
import streamlit as st
import yaml

from srptn.common.components.logs import log_selector
from srptn.common.data import Address, DataStore, Entity, FileType
from srptn.common.data.entities.dataset import Dataset
from srptn.common.tmux import TmuxSessionManager
from srptn.common.utils.polars_utils import load_data_table, save_data_table
from srptn.common.utils.yaml_utils import CustomSafeDumper, CustomSafeLoader
from srptn.common.utils.snakedeploy import CachedWorkflowDeployer


@dataclass
class WorkflowManager:
    """Manages workflow configurations, deployments, and validations."""

    url: str
    tag: str | None
    branch: str | None
    data_store: DataStore
    address: Address

    @classmethod
    def load(cls, data_store: DataStore, address: Address):
        """Create a workflow instance from stored metadata."""
        meta_path = data_store.files_path(address, FileType.META)
        with (meta_path / "details.yml").open("r") as file:
            details = yaml.safe_load(file)
        workflow_manager = cls(
            url=details["url"],
            tag=details["tag"],
            branch=details["branch"],
            data_store=data_store,
            address=address,
        )
        workflow_manager.check()
        return workflow_manager

    def store(self):
        """Deploys the workflow and copies required files."""
        self.data_store.clean(self.address)
        self.data_path.mkdir(parents=True, exist_ok=True)
        self.meta_path.mkdir(parents=True, exist_ok=True)
        with CachedWorkflowDeployer(
            self.url,
            self.data_path,
            tag=self.tag,
            branch=self.branch,
            cache=self.data_store.cache,
        ) as wd:
            wd.deploy(self.address.name)
            schema_path = Path(wd.repo_clone) / "workflow" / "schemas"
            if schema_path.exists():
                shutil.copytree(
                    schema_path,
                    self.schema_dir,
                )
            # TODO: store commit hash, tag (or None), branch (or None)
            # to avoid re-deploying
        self.check()
        self.export_metadata()

    @property
    def config_dir(self):
        """Configuration directory path."""
        return self.data_path / "config"

    @property
    def config_path(self):
        """Path to configuration file if it exists."""
        for ext in ("yml", "yaml"):
            path = self.config_dir / f"config.{ext}"
            if path.exists():
                return path

    @property
    def data_path(self):
        """Workflow data directory path."""
        return self.data_store.files_path(self.address, FileType.DATA)

    @property
    def log_path(self):
        """Snakemake log directory path if it exists."""
        hidden_snankemake_path = self.data_path / Path(".snakemake")
        if hidden_snankemake_path.is_dir():
            log_path = hidden_snankemake_path / Path("log")
            if log_path.is_dir():
                return log_path

    @property
    def meta_path(self):
        """Metadata directory path."""
        return self.data_store.files_path(self.address, FileType.META)

    @property
    def schema_dir(self):
        """Schema directory path."""
        return self.workflow_dir / "schemas"

    @property
    def snakefile_path(self):
        """Path to Snakefile if it exists."""
        for snakefile_dir in (self.workflow_dir, self.data_path):
            path = snakefile_dir / "Snakefile"
            if path.exists():
                return path

    @property
    def workflow_dir(self):
        """Workflow directory path."""
        return self.data_path / "workflow"

    def check(self):
        """Validate key workflow files."""
        if not self.config_path:
            st.error("No config file found!")
            st.stop()

        if not self.snakefile_path:
            st.error("No Snakefile found!")
            st.stop()

    def export_metadata(self):
        """Save workflow metadata to YAML file."""
        details = {
            "url": self.url,
            "tag": self.tag,
            "branch": self.branch,
        }
        with (self.meta_path / "details.yml").open("w") as f:
            yaml.safe_dump(details, f)

    def get_config(self) -> dict | None:
        """Load workflow configuration."""
        try:
            if self.config_path:
                return yaml.load(self.config_path.read_text(), Loader=CustomSafeLoader)
        except yaml.YAMLError as e:
            st.error(f"Error parsing config YAML: {e}")
            st.stop()

    def get_log(self, log_file_name: Path):
        """Load log file for specified log file name."""
        log = self.log_path
        if log is None:
            return ""
        with (log / log_file_name).open("r") as file:
            return file.read()

    def get_log_names(self) -> list[str]:
        """Gather names of all available logs."""
        if self.log_path:
            return [logfile.name for logfile in list(self.log_path.iterdir())]
        return []

    def get_schema(self, item: str) -> dict | None:
        """Load schema for specified item."""
        for ext in ("yaml", "yml", "json"):
            path = self.schema_dir / f"{item}.schema.{ext}"
            if path.exists():
                if ext != "json":
                    return yaml.load(path.read_text(), Loader=CustomSafeLoader)
                return json.load(path.read_text())  # type: ignore[reportArgumentType]
        return None

    def update_configs_from_session_state(self):
        """Update configuration files from Streamlit session state."""
        self.write_config(st.session_state["workflow-config-form"])
        entry: str
        for entry in st.session_state:
            if (
                entry.endswith("-data")
                and entry.startswith("workflow-config-")
                and isinstance(st.session_state[entry], pl.DataFrame)
            ):
                data = st.session_state[entry]
                data_path = self.data_path / st.session_state[entry[:-5]]
                save_data_table(data, data_path)

    def write_config(self, config: dict):
        """Overwrite configuration file."""
        config_path = self.config_path
        if config_path is None:
            self.config_dir.mkdir(parents=True, exist_ok=True)
            config_path = self.config_dir / "config.yaml"
        with config_path.open("w") as f:
            f.write(yaml.dump(config, sort_keys=False, Dumper=CustomSafeDumper))


class AnalysisRuntimeManager:
    """Manages workflow execution in tmux sessions."""

    def __init__(self, analysis_name: str):
        self.analysis_name = analysis_name
        self.session_name = f"{analysis_name}_session"
        self.tmux_manager = TmuxSessionManager()
        self.output: str | None = None

    @st.dialog("Analysis Progress", width="large")
    def show(self):
        """Show analysis progress dialog & displays real-time output."""
        self.check_status()

        @st.fragment(run_every=2 if self.output else None)
        def progress():
            self.check_status()
            with st.container(height=650):
                st.text(self.output if self.output else "No analysis started.")

        progress()

        c1, c2 = st.columns([0.12, 0.88])
        if c1.button("Close", key=f"{self.analysis_name}-close"):
            st.rerun()
        if c2.button("Stop Analysis", key=f"{self.analysis_name}-stop"):
            self.tmux_manager.close_session(self.session_name)

    def check_status(self) -> None:
        """Update stored analysis output from tmux session."""
        output = self.tmux_manager.capture_output(self.session_name)
        self.output = output

    def launch_analysis(self, command: str):
        """Start analysis in new tmux session."""
        session = self.tmux_manager.create_session(self.session_name)
        session.active_window.resize(width=500)  # Extra wide for no artificial \n
        assert session.active_pane is not None
        session.active_pane.send_keys(command)


@dataclass
class Analysis(Entity):
    """Represents an analysis with datasets, workflow, and an analysis manager."""

    datasets: list[Dataset]
    workflow_manager: WorkflowManager
    analysis_run_manager: AnalysisRuntimeManager | None = None

    def show(self):
        """Display analysis UI components."""
        if self.analysis_run_manager is None:
            self.analysis_run_manager = AnalysisRuntimeManager(str(self.address))
        st.header(self.address, divider=True)
        st.markdown(self.desc)

        parent_tabs = st.tabs(["Datasets", "Logs"])
        with parent_tabs[0]:
            dataset_tabs = st.tabs([str(data.address) for data in self.datasets])
            for dataset_tab, dataset in zip(dataset_tabs, self.datasets, strict=True):
                with dataset_tab:
                    st.dataframe(dataset.sheet)
        with parent_tabs[1]:
            log_selector(self.workflow_manager.data_store, self.address)

        c1, c2 = st.columns([0.21, 0.79])
        if c1.button("Run Analysis", key=f"{self.address.__str__}-run_button"):
            command = f"cd {self.workflow_manager.data_path} && snakemake -c 2"
            self.analysis_run_manager.launch_analysis(command)
        if c2.button(
            "Check Status",
            key=f"{self.analysis_run_manager.analysis_name}-status_open",
        ):
            self.analysis_run_manager.show()

    @classmethod
    def load(cls, data_store, address):
        """Create Analysis instance from stored data."""
        desc = data_store.load_desc(address)
        datasets = [
            Dataset.load(data_store, Address.from_filename(Path(f["name"]).stem))
            for f in data_store.list_files(address, FileType.META).iter_rows(named=True)
            if f["name"].endswith(".parquet")
        ]
        workflow_manager = WorkflowManager.load(data_store, address)
        analysis_run_manager = AnalysisRuntimeManager(str(address))
        return cls(address, desc, datasets, workflow_manager, analysis_run_manager)

    def store(self, data_store: DataStore):
        """Save analysis state to storage."""
        # FIXME: mixed data_store from .store and .load
        data_store.store_desc(self.address, self.desc)
        dataset_entities = {}
        for dataset in self.datasets:
            if dataset.sheet is not None:
                dataset_entities[str(dataset.address)] = dataset.list_files(
                    FileType.DATA
                )["name"].to_list()
                data_store.store_sheet(
                    self.address,
                    dataset.sheet,
                    dataset.address.to_filename(),
                )

        self.workflow_manager.update_configs_from_session_state()
        # FIXME: only update tables for 'workflow-config-*-data'
        for path_obj in self.workflow_manager.data_path.rglob("*"):
            if path_obj.is_file() and path_obj.suffix in (".tsv", ".csv", ".xlsx"):
                self.update_data_paths(path_obj, dataset_entities)
        for key in st.session_state:
            if key.startswith("workflow-"):
                del st.session_state[key]
        st.session_state["workflow-refresh"] = True  # Removing cache of the workflow

    def update_data_paths(self, path_obj: Path, dataset_entities: dict[str, list]):
        """Update dataset paths in data tables."""
        data = load_data_table(path_obj)
        if data is None:
            return
        updated_groups = []
        relative_to_analysis = "../" * (len(self.address.categories) + 3)
        for datasetid, group in data.group_by("datasetid"):
            if not datasetid:
                updated_groups.append(group)
                continue
            dataset_entries = dataset_entities.get(datasetid[0], [])
            updated_group = group.with_columns(
                [
                    pl.when(pl.col(col).is_in(dataset_entries).all())
                    .then(
                        pl.format(relative_to_analysis + f"{pl.col('datasetid')}/{col}")
                    )
                    .otherwise(col)
                    .alias(col)
                    for col in group.columns
                ],
            )
            updated_groups.append(updated_group)

        updated_data = (
            pl.concat(updated_groups) if len(updated_groups) > 1 else updated_groups[0]
        )
        save_data_table(updated_data, path_obj)
