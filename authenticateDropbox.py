#!/usr/bin/env python3
import argparse
import base64
import json
import os
import secrets
import threading
import time
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from config import load_config_file, resolve_dropbox_credentials_file, resolve_secrets_path, resolve_state_dir


AUTH_URL = "https://www.dropbox.com/oauth2/authorize"
TOKEN_URL = "https://api.dropbox.com/oauth2/token"


def basic_auth_header(app_key: str, app_secret: str) -> str:
    raw = f"{app_key}:{app_secret}".encode("utf-8")
    return "Basic " + base64.b64encode(raw).decode("ascii")


class OAuthCallbackHandler(BaseHTTPRequestHandler):
    server_version = "DropboxOAuthCallback/1.0"

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(parsed.query)
        self.server.auth_code = query.get("code", [None])[0]
        self.server.auth_state = query.get("state", [None])[0]
        self.server.auth_error = query.get("error", [None])[0]

        if self.server.auth_code:
            body = (
                "<html><body><h1>Dropbox authorization complete.</h1>"
                "<p>You can close this window and return to the terminal.</p>"
                "</body></html>"
            )
            self.send_response(200)
        else:
            body = (
                "<html><body><h1>Dropbox authorization failed.</h1>"
                "<p>Return to the terminal and inspect the error.</p>"
                "</body></html>"
            )
            self.send_response(400)

        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body.encode("utf-8"))))
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))

    def log_message(self, format, *args):
        return


def build_authorize_url(*, app_key: str, redirect_uri: str, state: str) -> str:
    params = {
        "client_id": app_key,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "token_access_type": "offline",
        "scope": "files.content.write",
        "state": state,
    }
    return AUTH_URL + "?" + urllib.parse.urlencode(params)


def exchange_code_for_token(*, app_key: str, app_secret: str, code: str, redirect_uri: str) -> dict:
    data = urllib.parse.urlencode(
        {
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        }
    ).encode("utf-8")
    request = urllib.request.Request(TOKEN_URL, data=data, method="POST")
    request.add_header("Authorization", basic_auth_header(app_key, app_secret))
    request.add_header("Content-Type", "application/x-www-form-urlencoded")
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def write_credentials(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    os.chmod(path, 0o600)


def main() -> int:
    config = load_config_file()
    default_secrets_path = resolve_secrets_path(config)
    default_state_dir = resolve_state_dir(default_secrets_path, config)
    default_credentials_file = resolve_dropbox_credentials_file(default_state_dir, config)

    parser = argparse.ArgumentParser(
        description="Obtiene refresh token de Dropbox para uso offline."
    )
    parser.add_argument("--app-key", required=True, help="Dropbox app key")
    parser.add_argument("--app-secret", required=True, help="Dropbox app secret")
    parser.add_argument(
        "--listen-host",
        default="127.0.0.1",
        help="Host local para recibir el callback (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--listen-port",
        type=int,
        default=53682,
        help="Puerto local para recibir el callback (default: 53682)",
    )
    parser.add_argument(
        "--credentials-file",
        default=str(default_credentials_file),
        help="Archivo JSON donde guardar app_key, app_secret y refresh_token",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="No intenta abrir el navegador automáticamente",
    )
    args = parser.parse_args()

    redirect_uri = f"http://{args.listen_host}:{args.listen_port}/callback"
    state = secrets.token_urlsafe(24)
    authorize_url = build_authorize_url(
        app_key=args.app_key,
        redirect_uri=redirect_uri,
        state=state,
    )

    server = HTTPServer((args.listen_host, args.listen_port), OAuthCallbackHandler)
    server.auth_code = None
    server.auth_state = None
    server.auth_error = None

    thread = threading.Thread(target=server.handle_request, daemon=True)
    thread.start()

    print("Configura este Redirect URI en tu app de Dropbox antes de continuar:")
    print(redirect_uri)
    print()
    print("Abrí esta URL para autorizar la app:")
    print(authorize_url)
    print()

    if not args.no_browser:
        webbrowser.open(authorize_url)

    deadline = time.time() + 300
    while thread.is_alive() and time.time() < deadline:
        thread.join(timeout=0.2)

    if thread.is_alive():
        print("Timeout esperando el callback de Dropbox.")
        server.server_close()
        return 1

    server.server_close()

    if server.auth_error:
        print(f"Dropbox devolvió un error de autorización: {server.auth_error}")
        return 1

    if not server.auth_code:
        print("No se recibió authorization code.")
        return 1

    if server.auth_state != state:
        print("State inválido en callback OAuth.")
        return 1

    token_payload = exchange_code_for_token(
        app_key=args.app_key,
        app_secret=args.app_secret,
        code=server.auth_code,
        redirect_uri=redirect_uri,
    )

    refresh_token = token_payload.get("refresh_token")
    if not refresh_token:
        print("Dropbox no devolvió refresh_token. Verificá token_access_type=offline y scopes.")
        return 1

    print("Authorization OK.")
    print(f"account_id: {token_payload.get('account_id', '')}")
    print(f"scope: {token_payload.get('scope', '')}")
    print("refresh_token:")
    print(refresh_token)

    if args.credentials_file:
        payload = {
            "app_key": args.app_key,
            "app_secret": args.app_secret,
            "refresh_token": refresh_token,
        }
        write_credentials(Path(args.credentials_file), payload)
        print(f"Credentials written to {args.credentials_file}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
