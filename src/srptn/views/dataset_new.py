import streamlit as st

from srptn.common.accounts.policy import Actor, Role
from srptn.common.components.forms import entity_meta_editor
from srptn.common.components.sample_sheet import sample_sheet_editor
from srptn.common.data.entities.dataset import Dataset
from srptn.common.data.fs import fs_data_store
from srptn.views import PageInfo

_SHEET_KEY = "new-dataset-sheet"


@PageInfo.wrap("New Dataset", Role.HOST)
def page_new_dataset(actor: Actor):
    data_store = fs_data_store()

    address, desc = entity_meta_editor(
        "new_dataset", "Dataset name", actor, Dataset, data_store
    )

    files = st.file_uploader("Files", accept_multiple_files=True)
    sheet = None
    if files:
        file_names = [file.name for file in files]
        sheet, sheet_errors = sample_sheet_editor(_SHEET_KEY, file_names)
        for error in sheet_errors:
            st.error(error)

    meta_files = st.file_uploader("Metadata files", accept_multiple_files=True)

    if not desc:
        st.error("Please describe the dataset before storing.")
        st.stop()
    store = st.button(
        "Store",
        disabled=not desc or not files or sheet is None,
    )

    if store:
        Dataset(
            address=address,
            desc=desc,
            sheet=sheet,
            data_files=files,
            meta_files=meta_files,
        ).store(data_store)
        st.success(f"Stored {len(files)} files in {address}")
