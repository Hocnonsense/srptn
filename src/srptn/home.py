import streamlit as st

from srptn.common.accounts.policy import Role
from srptn.common.accounts.session import (
    account_service,
    change_password_form,
    current_actor,
    current_session,
    login_form,
    logout,
    register_form,
)

st.set_page_config(page_title="SRPTN")


service = account_service()

actor = current_actor(service)
if actor is None:

    def login_page():
        st.title("SRPTN - the Snakemake research platform")
        login_form(service)

    def register_page():
        st.title("Register for SRPTN")
        register_form(service)

    navigation = [
        st.Page(login_page, title="Log in"),
        st.Page(register_page, title="Register"),
    ]
else:

    def account_page():
        st.title("Account")
        session = current_session()
        if actor is None or session is None:
            # Unreachable via the authenticated navigation, but a session can
            # end mid-run; report it instead of raising an AssertionError.
            st.error("Your session has ended. Please log in again.")
            logout()
            st.stop()
        st.caption(f"Hello, {actor.role.label} {actor.id}!")
        change_password_form(service, session)
        if st.button("Logout", use_container_width=True):
            logout()
            st.rerun()

    entries = [
        ("views/1 New Dataset.py", "New Dataset", Role.HOST),
        ("views/2 Datasets.py", "Datasets", Role.VISITOR),
        ("views/3 New Analysis.py", "New Analysis", Role.HOST),
        ("views/4 Analyses.py", "Analyses", Role.VISITOR),
        ("views/5 Notebook (Mockup).py", "Notebook (Mockup)", Role.VISITOR),
        ("views/6 Compose Figure (Mockup).py", "Compose Figure (Mockup)", Role.VISITOR),
        (account_page, "Account", None),
    ]
    navigation = [
        st.Page(page, title=title)
        for page, title, role in entries
        if actor.role.permitted(role)
    ]

st.navigation(navigation).run()
