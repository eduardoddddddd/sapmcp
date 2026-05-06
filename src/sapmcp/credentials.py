from __future__ import annotations

import argparse
import getpass
import os
import sys


def _keyring_module():
    try:
        import keyring  # type: ignore
    except ModuleNotFoundError as exc:
        raise SystemExit("keyring no está instalado. Instala el extra opcional con: pip install 'sapmcp[keyring]'") from exc
    return keyring


def set_password(user: str | None = None, password: str | None = None) -> None:
    user = user or os.getenv("SAP_USER")
    if not user:
        raise SystemExit("Indica --user o define SAP_USER")
    if password is None:
        password = getpass.getpass(f"Password SAP para {user}: ")
    _keyring_module().set_password("sapmcp", user, password)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="sapmcp-credentials", description="Gestiona credenciales opcionales de sapmcp en keyring.")
    sub = parser.add_subparsers(dest="command", required=True)
    set_parser = sub.add_parser("set", help="Guardar password SAP en keyring service='sapmcp'.")
    set_parser.add_argument("--user", default=None, help="Usuario SAP. Por defecto SAP_USER.")
    args = parser.parse_args(argv)
    if args.command == "set":
        set_password(user=args.user)
        sys.stderr.write(f"Credencial guardada en keyring para service='sapmcp' user='{args.user or os.getenv('SAP_USER')}'\n")


if __name__ == "__main__":
    main()
