"""Account management CLI.

Run as ``python -m srptn.accounts_manage <command>``.  Registration and
password change are self-service in the web app; this CLI covers the
maintainer actions that are not exposed to users.  The database path comes
from ``--database``, ``SRPTN_ACCOUNTS_DB`` or the server config.

Maintainer actions are recorded with the server name as the operator unless
``--operator`` overrides it.
"""

import argparse
import socket
import sys

from ..common.accounts.models import Account, AccountStatus
from ..common.accounts.policy import Role

from .service import ManageAccountService

server_name = socket.gethostname()


def _build_parser():
    parser = argparse.ArgumentParser(
        prog="python -m srptn.accounts_manage",
        description="Manage SRPtn accounts (set-status, set-role, stat, ls).",
    )
    parser.add_argument(
        "--database",
        help="account database path (defaults to config or datastore/accounts.db)",
    )
    parser.add_argument(
        "--operator",
        default="",
        help="operator address for the audit log (defaults to the server name)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    set_status = sub.add_parser("set-status", help="activate an on-hold account")
    set_status.add_argument("id")
    set_status.add_argument("status", choices=[s.value for s in AccountStatus])

    set_role = sub.add_parser("set-role", help="change an account's role")
    set_role.add_argument("id")
    set_role.add_argument("role", choices=[r.label for r in Role])

    stat = sub.add_parser("stat", help="show an account and audit events")
    stat.add_argument("id")

    ls = sub.add_parser("ls", help="list accounts")
    ls.add_argument("--status", choices=[s.value for s in AccountStatus])
    ls.add_argument("--role", choices=[r.label for r in Role])

    return parser


def _run(args):
    service = ManageAccountService.open(args.database)
    operator = (args.operator + "@" if args.operator else "") + server_name
    try:
        if args.command == "set-status":
            account = service.set_status(
                args.id, status=AccountStatus(args.status), operator_address=operator
            )
            print(f"Status set: {account.describe()}")
        elif args.command == "set-role":
            account = service.set_role(
                args.id, Role.from_label(args.role), operator_address=operator
            )
            print(f"Role set: {account.describe()}")
        elif args.command == "stat":
            print(service.stat(args.id))
        elif args.command == "ls":
            print(service.ls(args.status, args.role))
    except (Account.NotFound, ValueError) as exc:
        raise SystemExit(str(exc)) from exc
    return 0


def main(argv: list[str] | None = None):
    args = _build_parser().parse_args(argv)
    return _run(args)


if __name__ == "__main__":
    sys.exit(main())
