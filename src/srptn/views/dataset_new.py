import polars as pl
import polars.selectors as cs
import streamlit as st

from srptn.common.accounts.policy import Actor
from srptn.common.components.categories import category_editor
from srptn.common.components.descriptions import desc_editor
from srptn.common.data import Address
from srptn.common.data.entities.dataset import Dataset
from srptn.common.data.fs import FSDataStore
from srptn.common.utils.polars_utils import load_data_table


def page_new_dataset(actor: Actor):
    data_store = FSDataStore()

    categories = category_editor("new_dataset-meta")
    dataset_name = st.text_input("Dataset name")

    address = Address(actor.id, Dataset, categories=categories, name=dataset_name)
    if data_store.occupied(address):
        st.error(f"Dataset {address} already exists")
        st.stop()

    desc = desc_editor("new_dataset-meta")

    files = st.file_uploader("Files", accept_multiple_files=True)

    multi_file = len(files) > 1

    sheet = st.file_uploader("Sample Sheet") if multi_file else None

    if sheet:
        sheet = load_data_table(sheet, "upload")
        if sheet is None:
            st.error("Failed to load sample sheet")
            st.stop()

        sheet = sheet.with_columns([pl.col(pl.Utf8).str.strip_chars()])

        st.text("Sample sheet")
        st.dataframe(sheet)
        # TODO: highlight sample-sheet cells that match an uploaded file;
        #       for path columns, warn for non-empty cells with no matching file,
        #       also warn for uploaded files referenced by no cell (unused).
        # TODO: support folder ingestion: browser directory picker where available,
        #       otherwise a zip/tar upload.
        for f in files:
            if not sheet.select(
                pl.any_horizontal((cs.string() == f.name).any())
            ).item():
                st.error(f"Uploaded file {f.name} not found in sample sheet")
                st.stop()

    meta_files = st.file_uploader("Metadata files", accept_multiple_files=True)

    store = st.button(
        "Store",
        disabled=not desc or not files or (multi_file and sheet is None),
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
