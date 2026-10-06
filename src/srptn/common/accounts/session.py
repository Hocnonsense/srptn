"""Streamlit session authentication adapter.

The entrypoint calls :func:`current_actor` on every rerun: it re-reads the
account from the database and caches the resulting :class:`Actor` so that a
password or status change revokes the session.  Pages only read that cached
actor through :func:`require_actor`; they never touch the database or raw
session keys.
"""

import streamlit as st

from .models import Account, Session
from .policy import Actor, Role
from .service import AccountService
from .settings import resolve_database_path

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
    session = current_session()
    if session is None:
        return None
    account = service.get_account(session.id)
    if account is None or not account.is_active or account.version != session.version:
        st.session_state.pop(_SESSION_KEY, None)
        st.session_state.pop(_ACTOR_KEY, None)
        st.session_state[_REVOKED_KEY] = True
        return None
    st.session_state[_ACTOR_KEY] = account.actor()
    return account


def current_session() -> Session | None:
    """Return the session token (id + version) or ``None``."""
    return st.session_state.get(_SESSION_KEY)


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
    except Account.InvalidCredentials:
        st.error("ID or password is incorrect")
    except Account.OnHold:
        st.error("Account is on hold, please contact an administrator")
    except ValueError as exc:
        st.error(str(exc))
    else:
        st.session_state[_SESSION_KEY] = account.session()
        st.session_state[_ACTOR_KEY] = account.actor()
        st.session_state.pop(_REVOKED_KEY, None)
        st.rerun()


def register_form(service: AccountService):
    """Render the self-registration form.

    The account is created on hold; a maintainer must approve it before it
    can log in.
    """
    st.subheader("Register")
    with st.form("srptn-register-form"):
        id_ = st.text_input("ID")
        password = st.text_input("Password", type="password")
        repeat = st.text_input("Repeat password", type="password")
        submitted = st.form_submit_button("Register")
    if not submitted:
        return
    if password != repeat:
        st.error("Passwords do not match")
        return
    try:
        service.register(id_, password)
    except Account.Occupied:
        st.error("This ID is already taken")
        return
    except ValueError as exc:
        st.error(str(exc))
        return
    st.success(
        "Registered. An administrator must approve your account before you can log in.",
    )


def change_password_form(service: AccountService, session: Session):
    """Render the self-service password change form for the logged-in session."""
    st.subheader("Change password")
    with st.form("srptn-password-form"):
        current = st.text_input("Current password", type="password")
        new = st.text_input("New password", type="password")
        repeat = st.text_input("Repeat new password", type="password")
        submitted = st.form_submit_button("Change password")
    if not submitted:
        return
    if new != repeat:
        st.error("Passwords do not match")
        return
    try:
        account = service.change_password(session, current, new)
    except Account.NotFound:
        logout()
        st.session_state[_REVOKED_KEY] = True
        st.rerun()
    except ValueError as exc:
        st.error(str(exc))
        return
    # Keep the current session logged in with the bumped version.
    st.session_state[_SESSION_KEY] = account.session()
    st.success("Password changed. Use the new password next time.")


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


def require_role(actor: Actor, minimum: Role):
    """Stop the page unless the actor's role is at least ``minimum``.

    This is the server-side gate that also covers direct access to a page;
    hiding a page from the navigation only affects convenience.
    """
    if actor.role < minimum:
        st.error("You do not have permission to view this page.")
        st.stop()
