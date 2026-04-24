#!/usr/bin/env python3
import argparse
import base64
import json
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from config import (
    load_config_file,
    resolve_dropbox_credentials_file,
    resolve_secrets_path,
    resolve_state_dir,
)

TOKEN_URL = "https://api.dropbox.com/oauth2/token"
CONTENT_API_URL = "https://content.dropboxapi.com/2"
CHUNK_SIZE = 8 * 1024 * 1024
SIMPLE_UPLOAD_LIMIT = 150 * 1024 * 1024


def basic_auth_header(app_key: str, app_secret: str) -> str:
    raw = f"{app_key}:{app_secret}".encode("utf-8")
    return "Basic " + base64.b64encode(raw).decode("ascii")


def load_credentials(args) -> dict:
    if args.credentials_file:
        payload = json.loads(Path(args.credentials_file).read_text(encoding="utf-8"))
        return {
            "app_key": payload["app_key"],
            "app_secret": payload["app_secret"],
            "refresh_token": payload["refresh_token"],
        }

    missing = [
        name
        for name, value in (
            ("--app-key", args.app_key),
            ("--app-secret", args.app_secret),
            ("--refresh-token", args.refresh_token),
        )
        if not value
    ]
    if missing:
        raise SystemExit(f"Faltan credenciales: {', '.join(missing)}")

    return {
        "app_key": args.app_key,
        "app_secret": args.app_secret,
        "refresh_token": args.refresh_token,
    }


def refresh_access_token(*, app_key: str, app_secret: str, refresh_token: str) -> str:
    data = urllib.parse.urlencode(
        {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        }
    ).encode("utf-8")
    request = urllib.request.Request(TOKEN_URL, data=data, method="POST")
    request.add_header("Authorization", basic_auth_header(app_key, app_secret))
    request.add_header("Content-Type", "application/x-www-form-urlencoded")
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return payload["access_token"]


def content_request(*, endpoint: str, access_token: str, api_arg: dict, body: bytes) -> dict:
    request = urllib.request.Request(
        f"{CONTENT_API_URL}{endpoint}",
        data=body,
        method="POST",
    )
    request.add_header("Authorization", f"Bearer {access_token}")
    request.add_header("Dropbox-API-Arg", json.dumps(api_arg))
    request.add_header("Content-Type", "application/octet-stream")
    with urllib.request.urlopen(request, timeout=120) as response:
        raw = response.read()
    return json.loads(raw.decode("utf-8")) if raw else {}


def upload_small_file(*, local_path: Path, dropbox_path: str, access_token: str) -> dict:
    data = local_path.read_bytes()
    return content_request(
        endpoint="/files/upload",
        access_token=access_token,
        api_arg={
            "path": dropbox_path,
            "mode": "overwrite",
            "autorename": False,
            "mute": False,
            "strict_conflict": False,
        },
        body=data,
    )


def upload_large_file(*, local_path: Path, dropbox_path: str, access_token: str) -> dict:
    with local_path.open("rb") as handle:
        first_chunk = handle.read(CHUNK_SIZE)
        start_result = content_request(
            endpoint="/files/upload_session/start",
            access_token=access_token,
            api_arg={"close": False},
            body=first_chunk,
        )
        session_id = start_result["session_id"]
        offset = len(first_chunk)

        while True:
            chunk = handle.read(CHUNK_SIZE)
            if not chunk:
                break

            if handle.tell() == local_path.stat().st_size:
                return content_request(
                    endpoint="/files/upload_session/finish",
                    access_token=access_token,
                    api_arg={
                        "cursor": {"session_id": session_id, "offset": offset},
                        "commit": {
                            "path": dropbox_path,
                            "mode": "overwrite",
                            "autorename": False,
                            "mute": False,
                            "strict_conflict": False,
                        },
                    },
                    body=chunk,
                )

            content_request(
                endpoint="/files/upload_session/append_v2",
                access_token=access_token,
                api_arg={
                    "cursor": {"session_id": session_id, "offset": offset},
                    "close": False,
                },
                body=chunk,
            )
            offset += len(chunk)

    raise RuntimeError("Upload session terminó sin commit final.")


def upload_file(*, local_path: Path, dropbox_folder: str, access_token: str) -> dict:
    dropbox_folder = "/" + dropbox_folder.strip("/") if dropbox_folder.strip("/") else ""
    dropbox_path = f"{dropbox_folder}/{local_path.name}" if dropbox_folder else f"/{local_path.name}"
    if local_path.stat().st_size <= SIMPLE_UPLOAD_LIMIT:
        return upload_small_file(
            local_path=local_path,
            dropbox_path=dropbox_path,
            access_token=access_token,
        )
    return upload_large_file(
        local_path=local_path,
        dropbox_path=dropbox_path,
        access_token=access_token,
    )


def default_files(secrets_path: Path, include_checksum: bool) -> list[Path]:
    files = [secrets_path / "source.7z"]
    checksum = secrets_path / "source.7z.sha256"
    if include_checksum and checksum.exists():
        files.append(checksum)
    return files


def main() -> int:
    config = load_config_file()
    default_secrets_path = resolve_secrets_path(config)
    default_state_dir = resolve_state_dir(default_secrets_path, config)
    default_credentials_file = resolve_dropbox_credentials_file(default_state_dir, config)

    parser = argparse.ArgumentParser(
        description="Sube source.7z a Dropbox usando refresh token."
    )
    parser.add_argument("--app-key", default=None, help="Dropbox app key")
    parser.add_argument("--app-secret", default=None, help="Dropbox app secret")
    parser.add_argument("--refresh-token", default=None, help="Dropbox refresh token")
    parser.add_argument(
        "--credentials-file",
        default=str(default_credentials_file),
        help="Archivo JSON con app_key, app_secret y refresh_token",
    )
    parser.add_argument(
        "--secrets-path",
        default=str(default_secrets_path),
        help="Ruta base donde vive source.7z",
    )
    parser.add_argument(
        "--dropbox-folder",
        default="/backups",
        help="Carpeta destino en Dropbox (default: /backups)",
    )
    parser.add_argument(
        "--file",
        action="append",
        default=[],
        help="Archivo local a subir. Se puede repetir. Si no se pasa, usa source.7z",
    )
    parser.add_argument(
        "--include-checksum",
        action="store_true",
        help="Sube también source.7z.sha256 si existe",
    )
    args = parser.parse_args()

    credentials = load_credentials(args)
    access_token = refresh_access_token(**credentials)

    if args.file:
        files = [Path(item) for item in args.file]
    else:
        files = default_files(Path(args.secrets_path), args.include_checksum)

    for file_path in files:
        if not file_path.is_file():
            raise SystemExit(f"No existe el archivo a subir: {file_path}")

    for file_path in files:
        try:
            metadata = upload_file(
                local_path=file_path,
                dropbox_folder=args.dropbox_folder,
                access_token=access_token,
            )
        except urllib.error.HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            raise SystemExit(f"Dropbox upload failed for {file_path}: {exc.code} {error_body}") from exc

        print(f"Uploaded {file_path} -> {metadata.get('path_display', '')}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
