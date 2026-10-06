"""Server-side account settings and service factory.

The database path comes from the server configuration, never from business
users.  Keeping this separate from the account service keeps configuration
resolution out of the package import path and out of the domain logic.
"""

import os

DEFAULT_DATABASE_PATH = "datastore/accounts.db"


def resolve_database_path(database_path: str | None = None):
    """Resolve the account database path.

    Precedence: explicit argument, ``SRPTN_ACCOUNTS_DB`` environment
    variable, ``accounts.database_path`` in the server config, then the
    default.
    """
    if database_path:
        return database_path
    return DEFAULT_DATABASE_PATH
