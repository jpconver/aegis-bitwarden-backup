#!/usr/bin/env python3
import argparse
import base64
import getpass
import hashlib
import hmac
import json
import os
import sys
import uuid
from pathlib import Path

from cryptography.hazmat.primitives import hashes, padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.hkdf import HKDFExpand
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

try:
    from argon2.low_level import Type as Argon2Type
    from argon2.low_level import hash_secret_raw
except ImportError:  # pragma: no cover - optional unless kdfType=1 is used
    Argon2Type = None
    hash_secret_raw = None


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def require_password_protected_export(payload: dict) -> None:
    if not payload.get("encrypted"):
        raise ValueError("El archivo no esta marcado como encrypted=true.")
    if not payload.get("passwordProtected"):
        raise ValueError("Solo se soportan exports passwordProtected=true.")


def derive_kdf_material(*, password: str, salt_b64_string: str, payload: dict) -> bytes:
    kdf_type = int(payload["kdfType"])
    kdf_iterations = int(payload["kdfIterations"])
    salt_bytes = salt_b64_string.encode("utf-8")

    if kdf_type == 0:
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt_bytes,
            iterations=kdf_iterations,
        )
        return kdf.derive(password.encode("utf-8"))

    if kdf_type == 1:
        if hash_secret_raw is None:
            raise RuntimeError(
                "kdfType=1 (Argon2id) requiere instalar argon2-cffi."
            )
        memory = int(payload.get("kdfMemory") or 0)
        parallelism = int(payload.get("kdfParallelism") or 0)
        if memory <= 0 or parallelism <= 0:
            raise ValueError("Faltan kdfMemory/kdfParallelism para Argon2id.")
        return hash_secret_raw(
            secret=password.encode("utf-8"),
            salt=salt_bytes,
            time_cost=kdf_iterations,
            memory_cost=memory,
            parallelism=parallelism,
            hash_len=32,
            type=Argon2Type.ID,
        )

    raise ValueError(f"kdfType no soportado: {kdf_type}")


def stretch_key(kdf_material: bytes) -> tuple[bytes, bytes]:
    enc_key = HKDFExpand(
        algorithm=hashes.SHA256(),
        length=32,
        info=b"enc",
    ).derive(kdf_material)
    mac_key = HKDFExpand(
        algorithm=hashes.SHA256(),
        length=32,
        info=b"mac",
    ).derive(kdf_material)
    return enc_key, mac_key


def parse_enc_string(value: str) -> tuple[int, bytes, bytes, bytes]:
    try:
        enc_type_str, payload_str = value.split(".", 1)
        parts = payload_str.split("|")
    except ValueError as exc:
        raise ValueError("EncString invalido.") from exc

    enc_type = int(enc_type_str)
    if enc_type != 2:
        raise ValueError(f"EncString no soportado: tipo {enc_type}.")
    if len(parts) != 3:
        raise ValueError("EncString tipo 2 debe tener iv|data|mac.")

    iv = base64.b64decode(parts[0])
    ciphertext = base64.b64decode(parts[1])
    mac = base64.b64decode(parts[2])

    if len(iv) != 16:
        raise ValueError("IV invalido en EncString.")
    if len(mac) != 32:
        raise ValueError("MAC invalido en EncString.")

    return enc_type, iv, ciphertext, mac


def decrypt_enc_string(*, enc_string: str, enc_key: bytes, mac_key: bytes) -> bytes:
    _, iv, ciphertext, mac = parse_enc_string(enc_string)
    expected_mac = hmac.new(mac_key, iv + ciphertext, hashlib.sha256).digest()
    if not hmac.compare_digest(mac, expected_mac):
        raise ValueError("MAC invalido. Password incorrecta o archivo alterado.")

    cipher = Cipher(algorithms.AES(enc_key), modes.CBC(iv))
    decryptor = cipher.decryptor()
    padded = decryptor.update(ciphertext) + decryptor.finalize()

    unpadder = padding.PKCS7(128).unpadder()
    return unpadder.update(padded) + unpadder.finalize()


def validate_enc_key(enc_key_validation: str, enc_key: bytes, mac_key: bytes) -> None:
    validation_plain = decrypt_enc_string(
        enc_string=enc_key_validation,
        enc_key=enc_key,
        mac_key=mac_key,
    ).decode("utf-8")
    uuid.UUID(validation_plain)


def main() -> int:
    os.umask(0o077)

    parser = argparse.ArgumentParser(
        description="Descifra un export password-protected de Bitwarden."
    )
    parser.add_argument("input_json", help="Archivo exportado por Bitwarden")
    parser.add_argument(
        "-o",
        "--output",
        default="bitwarden-decrypted.json",
        help="Archivo JSON de salida",
    )
    parser.add_argument(
        "--password",
        default=None,
        help="UNSAFE: password del export de Bitwarden por argv. Evitar en uso normal.",
    )
    parser.add_argument(
        "--password-stdin",
        action="store_true",
        help="Lee la password del export de Bitwarden desde stdin.",
    )
    parser.add_argument(
        "--no-output",
        action="store_true",
        help="Valida el descifrado sin escribir el JSON resultante.",
    )
    args = parser.parse_args()

    if args.password is not None and args.password_stdin:
        print("Error: --password y --password-stdin no se pueden usar juntos.", file=sys.stderr)
        return 1

    input_path = Path(args.input_json)
    output_path = Path(args.output)

    if not input_path.is_file():
        print(f"Error: no existe el archivo de entrada: {input_path}", file=sys.stderr)
        return 1

    try:
        payload = load_json(input_path)
        require_password_protected_export(payload)
    except Exception as exc:
        print(f"Error leyendo export de Bitwarden: {exc}", file=sys.stderr)
        return 1

    password = args.password
    if password is not None:
        print("Warning: --password expone secretos en argv y es inseguro.", file=sys.stderr)
    elif args.password_stdin:
        password = sys.stdin.readline().rstrip("\r\n")
    else:
        password = getpass.getpass("Password del export de Bitwarden: ")

    try:
        kdf_material = derive_kdf_material(
            password=password,
            salt_b64_string=payload["salt"],
            payload=payload,
        )
        enc_key, mac_key = stretch_key(kdf_material)
        validate_enc_key(payload["encKeyValidation_DO_NOT_EDIT"], enc_key, mac_key)
        decrypted = decrypt_enc_string(
            enc_string=payload["data"],
            enc_key=enc_key,
            mac_key=mac_key,
        )
        plain_json = json.loads(decrypted.decode("utf-8"))
    except Exception as exc:
        print(
            f"No se pudo descifrar el export de Bitwarden. Password incorrecta o formato no soportado: {exc}",
            file=sys.stderr,
        )
        return 2

    password = None
    kdf_material = None
    enc_key = None
    mac_key = None

    if args.no_output:
        print("OK: descifrado validado.")
        return 0

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(plain_json, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"OK: JSON descifrado escrito en {output_path}")
    print("ADVERTENCIA: el archivo de salida contiene secrets en claro.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
