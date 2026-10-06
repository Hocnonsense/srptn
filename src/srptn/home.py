import streamlit as st

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
        st.caption(f"Hello, {actor.role.value} {actor.id}!")
        change_password_form(service, session)
        if st.button("Logout", use_container_width=True):
            logout()
            st.rerun()

    navigation = [
        st.Page("views/1 New Dataset.py", title="New Dataset"),
        st.Page("views/2 Datasets.py", title="Datasets"),
        st.Page("views/3 New Analysis.py", title="New Analysis"),
        st.Page("views/4 Analyses.py", title="Analyses"),
        st.Page("views/5 Notebook (Mockup).py", title="Notebook (Mockup)"),
        st.Page("views/6 Compose Figure (Mockup).py", title="Compose Figure (Mockup)"),
        st.Page(account_page, title="Account"),
    ]

st.navigation(navigation).run()
