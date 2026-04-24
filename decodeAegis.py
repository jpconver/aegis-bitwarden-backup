#!/usr/bin/env python3
import argparse
import base64
import binascii
import getpass
import hashlib
import json
import os
import sys
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def hx(s: str) -> bytes:
    return bytes.fromhex(s)


def decrypt_gcm(*, key: bytes, nonce_hex: str, tag_hex: str, ciphertext):
    nonce = hx(nonce_hex)
    tag = hx(tag_hex)

    if isinstance(ciphertext, str):
        ct = base64.b64decode(ciphertext)
    else:
        ct = ciphertext

    data = ct + tag
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(nonce, data, None)


def derive_password_key(slot: dict, password: str) -> bytes:
    salt = hx(slot["salt"])
    n = int(slot["n"])
    r = int(slot["r"])
    p = int(slot["p"])

    mem_est = 128 * r * n
    maxmem_env = os.getenv("AEGIS_SCRYPT_MAXMEM")
    maxmem = int(maxmem_env) if maxmem_env else (mem_est + 1024 * 1024)

    return hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=n,
        r=r,
        p=p,
        maxmem=maxmem,
        dklen=32,
    )


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def find_password_slot(vault: dict) -> dict:
    slots = vault.get("header", {}).get("slots", [])
    for slot in slots:
        if int(slot.get("type", -1)) == 1:
            return slot
    raise RuntimeError("No se encontró un slot de password (type=1).")


def decrypt_master_key(slot: dict, password: str) -> bytes:
    wrapper_key = derive_password_key(slot, password)
    encrypted_master_key = hx(slot["key"])
    master_key = decrypt_gcm(
        key=wrapper_key,
        nonce_hex=slot["key_params"]["nonce"],
        tag_hex=slot["key_params"]["tag"],
        ciphertext=encrypted_master_key,
    )
    return master_key


def decrypt_db(vault: dict, master_key: bytes) -> dict:
    header = vault["header"]
    db_plain = decrypt_gcm(
        key=master_key,
        nonce_hex=header["params"]["nonce"],
        tag_hex=header["params"]["tag"],
        ciphertext=vault["db"],
    )
    return json.loads(db_plain.decode("utf-8"))


def format_entry(entry: dict) -> str:
    name = entry.get("name", "")
    issuer = entry.get("issuer", "")
    otp_type = entry.get("type", "")
    info = entry.get("info", {}) or {}

    lines = [
        f"name={name}",
        f"issuer={issuer}",
        f"type={otp_type}",
        f"secret={info.get('secret', '')}",
        f"algo={info.get('algo', '')}",
        f"digits={info.get('digits', '')}",
    ]

    if "period" in info:
        lines.append(f"period={info['period']}")
    if "counter" in info:
        lines.append(f"counter={info['counter']}")
    if "pin" in info:
        lines.append(f"pin={info['pin']}")

    return "\n".join(lines)


def main():
    os.umask(0o077)

    parser = argparse.ArgumentParser(
        description="Descifra un export cifrado de Aegis y extrae seeds OTP."
    )
    parser.add_argument("input_json", help="Archivo exportado por Aegis")
    parser.add_argument(
        "-o",
        "--output",
        default="seeds.txt",
        help="Archivo de salida (default: seeds.txt)",
    )
    parser.add_argument(
        "--dump-decrypted-json",
        default=None,
        help="Opcional: guardar el vault descifrado completo en JSON",
    )
    parser.add_argument(
        "--password",
        default=None,
        help="UNSAFE: password del export de Aegis por argv. Evitar en uso normal.",
    )
    parser.add_argument(
        "--password-stdin",
        action="store_true",
        help="Lee la password del export de Aegis desde stdin.",
    )
    parser.add_argument(
        "--no-output",
        action="store_true",
        help="Valida el descifrado sin escribir archivos de salida.",
    )
    args = parser.parse_args()

    if args.password is not None and args.password_stdin:
        print("Error: --password y --password-stdin no se pueden usar juntos.", file=sys.stderr)
        sys.exit(1)

    in_path = Path(args.input_json)
    out_path = Path(args.output)
    dump_path = Path(args.dump_decrypted_json) if args.dump_decrypted_json else None

    if not in_path.is_file():
        print(f"Error: no existe el archivo de entrada: {in_path}", file=sys.stderr)
        sys.exit(1)

    try:
        vault = load_json(in_path)
    except Exception as e:
        print(f"Error leyendo JSON: {e}", file=sys.stderr)
        sys.exit(1)

    if vault.get("version") != 1:
        print(
            f"Advertencia: versión de vault inesperada: {vault.get('version')}",
            file=sys.stderr,
        )

    header = vault.get("header")
    if not header or header.get("slots") is None or header.get("params") is None:
        print("Ese vault no parece estar cifrado o no tiene la estructura esperada.", file=sys.stderr)
        sys.exit(1)

    password = args.password
    if password is not None:
        print("Warning: --password expone secretos en argv y es inseguro.", file=sys.stderr)
    elif args.password_stdin:
        password = sys.stdin.readline().rstrip("\r\n")
    else:
        password = getpass.getpass("Password del export de Aegis: ")

    try:
        slot = find_password_slot(vault)
        master_key = decrypt_master_key(slot, password)
        plain = decrypt_db(vault, master_key)
    except binascii.Error as e:
        print(f"Error decodificando Base64/hex: {e}", file=sys.stderr)
        sys.exit(2)
    except ValueError as e:
        msg = str(e).lower()
        if "memory limit exceeded" in msg:
            print(
                "Error en scrypt: memory limit exceeded. "
                "Probá definir AEGIS_SCRYPT_MAXMEM (bytes) a un valor mayor, "
                "por ejemplo: AEGIS_SCRYPT_MAXMEM=67108864",
                file=sys.stderr,
            )
            sys.exit(2)
        raise
    except Exception as e:
        print(f"No se pudo descifrar el vault. Password incorrecta o formato no soportado: {e}", file=sys.stderr)
        sys.exit(2)

    entries = plain.get("entries", [])
    if not isinstance(entries, list):
        print("Formato inesperado: 'entries' no es una lista.", file=sys.stderr)
        sys.exit(3)

    chunks = []
    for i, entry in enumerate(entries, start=1):
        chunks.append(f"[entry {i}]")
        chunks.append(format_entry(entry))
        chunks.append("")

    if not args.no_output:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text("\n".join(chunks), encoding="utf-8")

    if dump_path and not args.no_output:
        dump_path.parent.mkdir(parents=True, exist_ok=True)
        dump_path.write_text(
            json.dumps(plain, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    password = None
    master_key = None

    if args.no_output:
        print(f"OK: descifrado validado. {len(entries)} entries encontradas.")
    else:
        print(f"OK: {len(entries)} entries escritas en {out_path}")
        print("ADVERTENCIA: el archivo de salida contiene secrets en claro.")


if __name__ == "__main__":
    main()
