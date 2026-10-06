"""Accounts, identity and permission contract for SRPtn.

The account database stores only identity and status; resource ownership,
read grants and post-analysis memberships remain with the run platform.

Modules:
- ``models``: account records (`Account`) and errors.
- ``passwords``: password hashing.
- ``policy``: roles, actor, resource relations and the permission policy.
- ``repository``: account SQL and row mapping.
- ``schema``: canonical account schema (create-or-verify).
- ``service``: account service (validation, hashing, orchestration).
- ``session``: Streamlit session authentication adapter.
- ``settings``: database path resolution.
"""
