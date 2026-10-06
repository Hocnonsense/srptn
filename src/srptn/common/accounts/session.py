"""Streamlit session authentication adapter.

The entrypoint calls :func:`current_actor` on every rerun: it re-reads the
account from the database and caches the resulting :class:`Actor` so that a
password change, role change or disable revokes the session.  Pages only read
that cached actor through :func:`require_actor`; they never touch the
database or raw session keys.
"""

from typing import TYPE_CHECKING

import streamlit as st

from .service import AccountDisabled, AccountService, InvalidCredentials
from .settings import resolve_database_path

if TYPE_CHECKING:
    from .policy import Actor

_SESSION_KEY = "srptn-session"
_ACTOR_KEY = "srptn-actor"
_REVOKED_KEY = "srptn-session-revoked"

_services: dict[str, AccountService] = {}
"""AccountService is stateless (it opens a connection per operation),
 so a process-wide cache keyed by database path is safe and shared across sessions."""


def account_service(database_path: str | None = None):
    """Return the shared account service for the resolved database path."""
    path = resolve_database_path(database_path)
    if path not in _services:
        _services[path] = AccountService.open(path)
    return _services[path]


def logout():
    """End the session and clear all account drafts and UI state."""
    st.session_state.clear()


def current_account(service: AccountService):
    """Return the session's account, re-validating it against the database.

    A missing account, a disabled account or a ``version`` mismatch
    (password/role change or disable) ends the session.
    """
    session = st.session_state.get(_SESSION_KEY)
    if not session:
        return None
    account = service.get_account(session.get("id", ""))
    if (
        account is None
        or not account.is_active
        or account.version != session.get("version")
    ):
        st.session_state.pop(_SESSION_KEY, None)
        st.session_state.pop(_ACTOR_KEY, None)
        st.session_state[_REVOKED_KEY] = True
        return None
    st.session_state[_ACTOR_KEY] = account.actor()
    return account


def current_actor(service: AccountService):
    """Return the current actor, or ``None`` if not authenticated."""
    account = current_account(service)
    return account.actor() if account is not None else None


def login_form(service: AccountService):
    """Render the login form, logging in the user on success."""
    st.subheader("Login")
    if st.session_state.pop(_REVOKED_KEY, False):
        st.warning("The last session has ended. Please log in again.")
    with st.form("srptn-login-form"):
        id_ = st.text_input("ID")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Login")
    if not submitted:
        return
    try:
        account = service.verify_credentials(id_, password)
    except InvalidCredentials:
        st.error("ID or password is incorrect")
    except AccountDisabled:
        st.error("This account is disabled")
    except ValueError as exc:
        st.error(str(exc))
    else:
        st.session_state[_SESSION_KEY] = {
            "id": account.id,
            "version": account.version,
        }
        st.session_state[_ACTOR_KEY] = account.actor()
        st.session_state.pop(_REVOKED_KEY, None)
        st.rerun()


def require_actor():
    """Return the actor cached by the entrypoint, or stop the page.

    Pages run only through the navigation entrypoint, which validates the
    session and caches the actor; an absent actor means the page was reached
    without authentication.
    """
    actor: Actor | None = st.session_state.get(_ACTOR_KEY)
    if actor is None:
        st.error("Not authenticated")
        st.stop()
    return actor
