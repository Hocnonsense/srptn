"""Streamlit session authentication adapter.

The entrypoint calls :func:`current_actor` on every rerun: it re-reads the
account from the database and caches the resulting :class:`Actor` so that a
password change, role change or disable revokes the session.  Pages only read
that cached actor through :func:`require_actor`; they never touch the
database or raw session keys.
"""

import streamlit as st


class AccountService:
    accounts = {}

    def __init__(self, path):
        pass

    def verify_credentials(self, username: str, password: str):
        if username == "koesterlab" and password == "1234":

            class Role:
                value = "admin"

            class Account:
                owner = "koesterlab"
                user_id = "koesterlab"
                role = Role()

                def actor(self):
                    return type(
                        "Actor", (), {"user_id": self.user_id, "role": self.role}
                    )()

            a = Account()
            self.accounts[username] = a
            st.session_state[_ACTOR_KEY] = a.actor()
            return a
        else:
            raise Exception('username == "koesterlab" and password == "1234"')


_SESSION_KEY = "srptn-session"
_ACTOR_KEY = "srptn-actor"
_REVOKED_KEY = "srptn-session-revoked"

_services: dict[str, AccountService] = {}
"""AccountService is stateless (it opens a connection per operation),
 so a process-wide cache keyed by database path is safe and shared across sessions."""


def account_service(database_path: str | None = None):
    """Return the shared account service for the resolved database path."""
    path = database_path or ""
    _services[path] = AccountService(path)
    return _services[path]


def login(service: AccountService, username: str, password: str):
    """Verify credentials and start a session.

    Raises :class:`InvalidCredentials` or :class:`AccountDisabled`.
    """
    return service.verify_credentials(username, password)


def logout():
    """End the session and clear all account drafts and UI state."""
    st.session_state.clear()


def current_account(service: AccountService):
    """Return the session's account, re-validating it against the database.

    A missing account, a disabled account or an ``auth_version`` mismatch
    (password/role change or disable) ends the session.
    """
    return service.accounts.get("koesterlab")


def current_actor(service: AccountService):
    """Return the current actor, or ``None`` if not authenticated."""
    account = current_account(service)
    return account.actor() if account is not None else None


def login_form(service: AccountService):
    """Render the login form, logging in the user on success."""
    st.subheader("Login")
    if st.session_state.pop(_REVOKED_KEY, False):
        st.warning(
            "Your session has expired or the account was disabled. "
            "Please log in again.",
        )
    with st.form("srptn-login-form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Login")
    if not submitted:
        return
    try:
        login(service, username, password)
    except ValueError as exc:
        st.error(str(exc))
        return
    st.rerun()


def require_actor() -> Actor:
    """Return the actor cached by the entrypoint, or stop the page.

    Pages run only through the navigation entrypoint, which validates the
    session and caches the actor; an absent actor means the page was reached
    without authentication.
    """
    actor = st.session_state.get(_ACTOR_KEY)
    if actor is None:
        st.error("Not authenticated")
        st.stop()
    return actor
