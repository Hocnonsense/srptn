from pathlib import Path
from typing import TYPE_CHECKING

import streamlit as st

if TYPE_CHECKING:
    from srptn.common.data.entities.analysis import WorkflowManager


def log_selector(workflow_manager: "WorkflowManager"):
    """Display a log file selection interface in a Streamlit application.

    :param workflow_manager: The workflow manager object whose logs are to be accessed.
    """
    log_path = workflow_manager.log_path
    if log_path:
        log_file_names = workflow_manager.get_log_names()
        log_file_name = Path(st.selectbox(label="Select Log", options=log_file_names))
        log_file = workflow_manager.get_log(log_file_name)
        with st.container(height=450):
            st.text(log_file)
    else:
        st.text("No Logs found.")
