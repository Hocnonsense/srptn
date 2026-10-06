import streamlit as st

from srptn.common.accounts.session import (
    account_service,
    current_actor,
    login_form,
    logout,
)

st.set_page_config(page_title="SRPTN")


def login_page():
    st.title("SRPTN - the Snakemake research platform")
    login_form(service)


service = account_service()
actor = current_actor(service)

if actor is None:
    navigation = [st.Page(login_page, title="Log in")]
else:
    with st.sidebar:
        st.caption(f"Hello, {actor.id}!")
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
    ]

st.navigation(navigation).run()
