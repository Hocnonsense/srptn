import polars as pl
import streamlit as st

from srptn.common.accounts.policy import Actor, Role
from srptn.common.components.forms import entity_meta_editor
from srptn.common.components.table_editor import column_controls, editable_table
from srptn.common.data.entities.dataset import Dataset
from srptn.common.data.fs import fs_data_store
from srptn.common.utils.polars_utils import load_data_table
from srptn.views import PageInfo

_SHEET_KEY = "new-dataset-sheet"
_FILE_COLUMN = "file"


def _blank(value):
    return value is None or str(value).strip() == ""


def _sync_sheet(sheet: pl.DataFrame, file_names: list[str]):
    """Align generated rows with the uploaded files.

    A new file gets a row with every column except ``file`` left empty; a row
    whose file is gone is dropped only while its other columns are all empty,
    so a row that still holds data is kept (and later reported by
    :func:`_sheet_errors`).  Duplicate rows are preserved.  Returns the
    aligned frame, or ``None`` when nothing changed.
    """
    columns = list(sheet.columns)
    if _FILE_COLUMN not in columns:
        return
    known = set(file_names)
    others = [column for column in columns if column != _FILE_COLUMN]
    kept = []
    changed = False
    for row in sheet.iter_rows(named=True):
        if row[_FILE_COLUMN] in known or not all(
            _blank(row[column]) for column in others
        ):
            kept.append(row)
        else:
            changed = True
    present = {row[_FILE_COLUMN] for row in kept}
    for name in file_names:
        if name not in present:
            kept.append({_FILE_COLUMN: name} | dict.fromkeys(others))
            changed = True
    if changed:
        return pl.DataFrame(kept, schema=sheet.schema)


def _sample_sheet_editor(file_names: list[str]):
    """Upload-or-generate, then edit, the sample sheet.

    A generated sheet keeps in step with the files: new files add empty rows,
    and only emptied rows are dropped when a file disappears.  An upload
    replaces the sheet outright.  Returns the sheet when valid, else ``None``.
    """
    upload = st.file_uploader(
        "Sample Sheet",
        type=("tsv", "csv", "xlsx"),
        key=f"{_SHEET_KEY}-upload",
    )
    data_key = f"{_SHEET_KEY}-data"
    if upload is not None:
        identity = ("upload", upload.name, upload.size)
        reset = st.session_state.get(f"{_SHEET_KEY}-source") != identity
        if reset:
            sheet = load_data_table(upload, "upload")
            if sheet is None:
                st.error("Failed to load sample sheet")
                st.stop()
            if _FILE_COLUMN in sheet.columns:
                sheet = sheet.with_columns(pl.col(_FILE_COLUMN).cast(pl.String))
            st.session_state[data_key] = sheet.with_columns(
                pl.col(pl.String).str.strip_chars()
            )
        st.session_state[f"{_SHEET_KEY}-source"] = identity
    elif file_names:
        if (
            st.session_state.get(f"{_SHEET_KEY}-source") != ("generated",)
            or data_key not in st.session_state
        ):
            st.session_state[data_key] = pl.DataFrame(
                {_FILE_COLUMN: list(file_names), "sample": list(file_names)},
                schema={_FILE_COLUMN: pl.String, "sample": pl.String},
            )
            st.session_state[f"{_SHEET_KEY}-source"] = ("generated",)
            reset = True
        else:
            synced = _sync_sheet(st.session_state[data_key], file_names)
            reset = synced is not None
            if reset:
                st.session_state[data_key] = synced
    else:
        return None

    change = column_controls(_SHEET_KEY)
    st.text("Sample sheet")
    sheet = editable_table(_SHEET_KEY, reset=reset or bool(change))
    errors = _sheet_errors(sheet, file_names)
    if not errors:
        return sheet
    for error in errors:
        st.error(error)


def _sheet_errors(sheet: pl.DataFrame, file_names: list[str]):
    """Reasons the sample sheet cannot be stored, if any.

    The first column must be named ``file`` and its entries non-empty, unique
    and matching exactly the uploaded files (no unknown entry, no unused file).
    Each row must also carry at least one non-empty value besides ``file``.
    """
    errors: list[str] = []
    if sheet.width == 0:
        return errors
    if sheet.columns[0] != _FILE_COLUMN:
        return [f"The first column must be named '{_FILE_COLUMN}'."]

    others = sheet.columns[1:]
    known = set(file_names)
    seen = set()
    for index, row in enumerate(sheet.iter_rows(named=True), start=1):
        entry = row[_FILE_COLUMN]
        if entry is None or entry == "":
            errors.append(f"Row {index}: empty '{_FILE_COLUMN}' entry.")
            continue
        if entry in seen:
            errors.append(f"Duplicate file entry: {entry}")
        else:
            seen.add(entry)
            if entry not in known:
                errors.append(f"Unknown file entry: {entry}")
        if all(_blank(row[column]) for column in others):
            errors.append(f"Row {index}: no value besides '{_FILE_COLUMN}'.")
    missing = sorted(known - seen)
    if missing:
        errors.append("Missing file entries: " + ", ".join(missing))
    return errors


@PageInfo.wrap("New Dataset", Role.HOST)
def page_new_dataset(actor: Actor):
    data_store = fs_data_store()

    address, desc = entity_meta_editor(
        "new_dataset", "Dataset name", actor, Dataset, data_store
    )

    files = st.file_uploader("Files", accept_multiple_files=True)

    multi_file = len(files) > 1
    if multi_file:
        file_names = [file.name for file in files] if files else []
        sheet = _sample_sheet_editor(file_names)
    else:
        sheet = None

    meta_files = st.file_uploader("Metadata files", accept_multiple_files=True)

    if not desc:
        st.error("Please describe the dataset before storing.")
        st.stop()
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
