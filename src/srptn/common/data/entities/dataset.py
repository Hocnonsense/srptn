import io
from dataclasses import dataclass
from typing import Sequence

import polars as pl
import streamlit as st

from ...components.files import file_browser
from ...data import DataStore, Entity, FileType


@dataclass
class Dataset(Entity):
    """Represents a dataset with associated metadata and data files."""

    sheet: pl.DataFrame | None
    data_files: Sequence[io.BytesIO] | None = None
    meta_files: Sequence[io.BytesIO] | None = None
    _data_store: DataStore | None = None

    def show(self, actor, access):
        """Display the dataset details, sample sheet, and downloadable files.

        The dataset is already authorized; its own files are read directly.
        """
        st.header(self.address, divider=True)
        st.markdown(self.desc)
        if self.sheet is not None:
            st.subheader("Sample Sheet")
            st.dataframe(self.sheet)

        if self._data_store is not None:
            meta_files = self.list_files(FileType.META)
            if meta_files is not None and not meta_files.is_empty():
                st.subheader("Meta Files")
                for name in meta_files["name"]:
                    key = f"{self.address}/meta/{name}"
                    with self._data_store.load_file(
                        self.address, name, FileType.META
                    ) as file:
                        st.download_button(name, file, key=key, file_name=name)

        files = self.list_files(FileType.DATA)
        if files is not None:
            st.subheader("Files")
            file_browser(files)

    @classmethod
    def load(cls, data_store, address):
        """Load a dataset from the data store using its address."""
        workspace = data_store.workspace(address)
        sheet_name = "sheet"
        if workspace.has_sheet(sheet_name):
            sheet = workspace.load_sheet(sheet_name)
        else:
            sheet = None

        return cls(address, workspace.load_desc(), sheet, _data_store=data_store)

    def store(self, data_store: DataStore):
        """Store the dataset, including files and sample sheet, in the data store."""
        workspace = data_store.workspace(self.address)
        workspace.clean()
        workspace.store_desc(self.desc)
        if self.sheet is not None:
            workspace.store_sheet(self.sheet, "sheet")
        for file in self.data_files if self.data_files is not None else []:
            workspace.store_file(
                file,
                file.name,
                file_type=FileType.DATA,
            )
        for file in self.meta_files if self.meta_files is not None else []:
            workspace.store_file(
                file,
                file.name,
                file_type=FileType.META,
            )

    def list_files(self, file_type: FileType):
        """List files of a specific type (DATA or META) in the data store."""
        if self._data_store is None:
            raise ValueError("Data store is not set for this dataset.")
        return self._data_store.list_files(self.address, file_type=file_type)
