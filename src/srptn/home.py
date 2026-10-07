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
from srptn.views import visible_pages

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
        session = current_session()
        if actor is None or session is None:
            # Unreachable via the authenticated navigation, but a session can
            # end mid-run; report it instead of raising an AssertionError.
            st.error("Your session has ended. Please log in again.")
            logout(revoked=True)
            st.stop()
        st.title(f"Hello, {actor.role.label} {actor.id}!")
        change_password_form(service, session)
        if st.button("Logout", use_container_width=True):
            logout()
            st.rerun()

    navigation = [*visible_pages(actor)]
    navigation.append(st.Page(account_page, title="Account"))

st.navigation(navigation).run()
