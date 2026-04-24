#!/usr/bin/env python3
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import config
import uploadToDropbox


ROOT = Path(__file__).resolve().parent
DECODE_AEGIS = ROOT / "decodeAegis.py"
DECODE_BITWARDEN = ROOT / "decodeBitwarden.py"
ZIP_SOURCE = ROOT / "zipSource.sh"
RESTORE_SOURCE = ROOT / "generateSourceFromZipFile.sh"
GENERATE_TARGET = ROOT / "generateTargetFromSource.sh"


class DecodeSmokeTests(unittest.TestCase):
    """Smoke tests for the Python decoder entrypoints."""

    def test_decode_aegis_exits_with_error_when_input_file_is_missing(self):
        """Verifies decodeAegis.py basic error handling for a missing input file."""
        result = subprocess.run(
            [sys.executable, str(DECODE_AEGIS), "missing-file.json"],
            capture_output=True,
            text=True,
            cwd=ROOT,
        )

        self.assertEqual(result.returncode, 1)
        self.assertIn("no existe el archivo de entrada", result.stderr.lower())

    def test_decode_bitwarden_exits_with_error_when_input_file_is_missing(self):
        """Verifies decodeBitwarden.py basic error handling for a missing input file."""
        result = subprocess.run(
            [sys.executable, str(DECODE_BITWARDEN), "missing-file.json"],
            capture_output=True,
            text=True,
            cwd=ROOT,
        )

        self.assertEqual(result.returncode, 1)
        self.assertIn("no existe el archivo de entrada", result.stderr.lower())


@unittest.skipUnless(shutil.which("7z"), "7z no esta instalado")
class SourceArchiveTests(unittest.TestCase):
    """Smoke tests for the source-based archive workflow."""

    def test_zip_source_and_restore_source_roundtrip_with_bash_scripts(self):
        """Verifies zipSource.sh and generateSourceFromZipFile.sh keep source contents intact."""
        with tempfile.TemporaryDirectory() as temp_dir:
            secrets_path = Path(temp_dir)
            home_path = Path(temp_dir) / "home"
            state_dir = Path(temp_dir) / "state"
            source_path = secrets_path / "source"
            archive_path = secrets_path / "source.7z"
            checksum_path = secrets_path / "source.7z.sha256"
            last_source_root_file = state_dir / "last_source_root"

            home_path.mkdir(parents=True)
            state_dir.mkdir(parents=True)
            source_path.mkdir(parents=True)
            (source_path / "aegis-diario.json").write_text("enc-diario\n", encoding="utf-8")
            (source_path / "aegis-vault.json").write_text("enc-vault\n", encoding="utf-8")
            (source_path / "bitwarden-vault.json").write_text("bw-vault\n", encoding="utf-8")

            env = os.environ.copy()
            env["SECRETS_PATH"] = str(secrets_path)
            env["AEGIS_STATE_DIR"] = str(state_dir)
            env["HOME"] = str(home_path)

            zip_result = subprocess.run(
                ["bash", str(ZIP_SOURCE)],
                input="test-password\n",
                capture_output=True,
                text=True,
                cwd=ROOT,
                env=env,
            )
            self.assertEqual(zip_result.returncode, 0, zip_result.stderr)
            self.assertTrue(archive_path.is_file())
            self.assertTrue(checksum_path.is_file())

            shutil.rmtree(source_path)

            restore_result = subprocess.run(
                ["bash", str(RESTORE_SOURCE)],
                input="test-password\n",
                capture_output=True,
                text=True,
                cwd=ROOT,
                env=env,
            )
            self.assertEqual(restore_result.returncode, 0, restore_result.stderr)
            self.assertTrue(last_source_root_file.is_file())
            restored_source_path = Path(
                last_source_root_file.read_text(encoding="utf-8").strip()
            ) / "source"
            self.assertTrue((restored_source_path / "aegis-diario.json").is_file())
            self.assertTrue((restored_source_path / "aegis-vault.json").is_file())
            self.assertTrue((restored_source_path / "bitwarden-vault.json").is_file())
            self.assertEqual(
                (restored_source_path / "bitwarden-vault.json").read_text(encoding="utf-8"),
                "bw-vault\n",
            )

    def test_zip_source_creates_backup_of_previous_archive_by_default(self):
        """Verifies zipSource.sh preserves the previous source.7z in backups/ before overwriting it."""
        with tempfile.TemporaryDirectory() as temp_dir:
            secrets_path = Path(temp_dir)
            source_path = secrets_path / "source"
            archive_path = secrets_path / "source.7z"
            backup_dir = secrets_path / "backups"

            source_path.mkdir(parents=True)
            (source_path / "aegis-diario.json").write_text("diario-v1\n", encoding="utf-8")
            (source_path / "aegis-vault.json").write_text("vault-v1\n", encoding="utf-8")

            env = os.environ.copy()
            env["SECRETS_PATH"] = str(secrets_path)
            env["AEGIS_STATE_DIR"] = str(secrets_path / "state")

            first_zip = subprocess.run(
                ["bash", str(ZIP_SOURCE)],
                input="test-password\n",
                capture_output=True,
                text=True,
                cwd=ROOT,
                env=env,
            )
            self.assertEqual(first_zip.returncode, 0, first_zip.stderr)
            first_bytes = archive_path.read_bytes()

            (source_path / "aegis-diario.json").write_text("diario-v2\n", encoding="utf-8")

            second_zip = subprocess.run(
                ["bash", str(ZIP_SOURCE)],
                input="test-password\n",
                capture_output=True,
                text=True,
                cwd=ROOT,
                env=env,
            )
            self.assertEqual(second_zip.returncode, 0, second_zip.stderr)
            self.assertTrue(backup_dir.is_dir())
            backups = list(backup_dir.glob("source_*.7z"))
            self.assertEqual(len(backups), 1)
            self.assertEqual(backups[0].read_bytes(), first_bytes)

    def test_zip_and_restore_work_with_source_root_flag(self):
        """Verifies --source-root can be separated from --secrets-path, like a RAM-backed source area."""
        with tempfile.TemporaryDirectory() as temp_dir:
            secrets_path = Path(temp_dir) / "disk"
            home_path = Path(temp_dir) / "home"
            source_root = Path(temp_dir) / "ram"
            source_path = source_root / "source"
            archive_path = secrets_path / "source.7z"
            last_source_root_file = home_path / ".config" / "aegis" / "last_source_root"

            secrets_path.mkdir(parents=True)
            home_path.mkdir(parents=True)
            source_path.mkdir(parents=True)
            (source_path / "aegis-diario.json").write_text("diario\n", encoding="utf-8")
            (source_path / "aegis-vault.json").write_text("vault\n", encoding="utf-8")

            env = os.environ.copy()
            env["SECRETS_PATH"] = str(secrets_path)
            env["HOME"] = str(home_path)
            env["AEGIS_STATE_DIR"] = str(home_path / ".config" / "aegis")

            zip_result = subprocess.run(
                ["bash", str(ZIP_SOURCE), "--source-root", str(source_root)],
                input="test-password\n",
                capture_output=True,
                text=True,
                cwd=ROOT,
                env=env,
            )
            self.assertEqual(zip_result.returncode, 0, zip_result.stderr)
            self.assertTrue(archive_path.is_file())

            shutil.rmtree(source_path)

            restore_result = subprocess.run(
                ["bash", str(RESTORE_SOURCE), "--source-root", str(source_root)],
                input="test-password\n",
                capture_output=True,
                text=True,
                cwd=ROOT,
                env=env,
            )
            self.assertEqual(restore_result.returncode, 0, restore_result.stderr)
            self.assertTrue((source_root / "source" / "aegis-diario.json").is_file())
            self.assertTrue((source_root / "source" / "aegis-vault.json").is_file())
            self.assertTrue(last_source_root_file.is_file())
            self.assertEqual(last_source_root_file.read_text(encoding="utf-8").strip(), str(source_root))

            rezip_result = subprocess.run(
                ["bash", str(ZIP_SOURCE)],
                input="test-password\n",
                capture_output=True,
                text=True,
                cwd=ROOT,
                env=env,
            )
            self.assertEqual(rezip_result.returncode, 0, rezip_result.stderr)
            self.assertIn("Using last saved source root", rezip_result.stdout)


class UploadDefaultsTests(unittest.TestCase):
    """Smoke tests for upload defaults without doing network requests."""

    def test_upload_default_files_point_to_source_archive_and_checksum(self):
        """Verifies uploadToDropbox.py defaults now target source.7z and source.7z.sha256."""
        with tempfile.TemporaryDirectory() as temp_dir:
            secrets_path = Path(temp_dir)
            archive_path = secrets_path / "source.7z"
            checksum_path = secrets_path / "source.7z.sha256"
            archive_path.write_bytes(b"dummy")
            checksum_path.write_text("hash  source.7z\n", encoding="utf-8")

            files = uploadToDropbox.default_files(secrets_path, include_checksum=True)

            self.assertEqual(files, [archive_path, checksum_path])


class ConfigResolutionTests(unittest.TestCase):
    """Tests for shared config resolution across Python entrypoints."""

    def test_load_config_file_reads_simple_env_style_values(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_file = Path(temp_dir) / "config.env"
            config_file.write_text(
                "\n".join(
                    (
                        "# comment",
                        "AEGIS_SECRETS_PATH=/tmp/aegis-secrets",
                        'AEGIS_DROPBOX_CREDENTIALS_FILE="/tmp/aegis/dropbox.json"',
                    )
                )
                + "\n",
                encoding="utf-8",
            )

            values = config.load_config_file(config_file)

            self.assertEqual(values["AEGIS_SECRETS_PATH"], "/tmp/aegis-secrets")
            self.assertEqual(
                values["AEGIS_DROPBOX_CREDENTIALS_FILE"],
                "/tmp/aegis/dropbox.json",
            )

    def test_config_file_can_define_python_defaults_without_env_vars(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_file = Path(temp_dir) / "config.env"
            state_dir = Path(temp_dir) / "state"
            credentials_file = state_dir / "dropbox.json"
            config_file.write_text(
                "\n".join(
                    (
                        f"AEGIS_SECRETS_PATH={temp_dir}/secrets",
                        f"AEGIS_STATE_DIR={state_dir}",
                        f"AEGIS_DROPBOX_CREDENTIALS_FILE={credentials_file}",
                    )
                )
                + "\n",
                encoding="utf-8",
            )

            original_config_file = os.environ.get("AEGIS_CONFIG_FILE")
            original_secrets_path = os.environ.get("SECRETS_PATH")
            original_aegis_secrets_path = os.environ.get("AEGIS_SECRETS_PATH")
            original_state_dir = os.environ.get("AEGIS_STATE_DIR")
            original_credentials = os.environ.get("AEGIS_DROPBOX_CREDENTIALS_FILE")
            try:
                os.environ["AEGIS_CONFIG_FILE"] = str(config_file)
                for key in (
                    "SECRETS_PATH",
                    "AEGIS_SECRETS_PATH",
                    "AEGIS_STATE_DIR",
                    "AEGIS_DROPBOX_CREDENTIALS_FILE",
                ):
                    os.environ.pop(key, None)

                loaded = config.load_config_file()

                self.assertEqual(
                    config.resolve_secrets_path(loaded),
                    Path(temp_dir) / "secrets",
                )
                self.assertEqual(config.resolve_state_dir(config=loaded), state_dir)
                self.assertEqual(
                    config.resolve_dropbox_credentials_file(config=loaded),
                    credentials_file,
                )
            finally:
                if original_config_file is None:
                    os.environ.pop("AEGIS_CONFIG_FILE", None)
                else:
                    os.environ["AEGIS_CONFIG_FILE"] = original_config_file
                if original_secrets_path is None:
                    os.environ.pop("SECRETS_PATH", None)
                else:
                    os.environ["SECRETS_PATH"] = original_secrets_path
                if original_aegis_secrets_path is None:
                    os.environ.pop("AEGIS_SECRETS_PATH", None)
                else:
                    os.environ["AEGIS_SECRETS_PATH"] = original_aegis_secrets_path
                if original_state_dir is None:
                    os.environ.pop("AEGIS_STATE_DIR", None)
                else:
                    os.environ["AEGIS_STATE_DIR"] = original_state_dir
                if original_credentials is None:
                    os.environ.pop("AEGIS_DROPBOX_CREDENTIALS_FILE", None)
                else:
                    os.environ["AEGIS_DROPBOX_CREDENTIALS_FILE"] = original_credentials


class TargetGenerationTests(unittest.TestCase):
    """Tests for target lifecycle and password passing in generateTargetFromSource.sh."""

    def _write_fake_decoder(self, path: Path, label: str) -> None:
        path.write_text(
            """#!/usr/bin/env python3
import argparse
import sys
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--password-stdin", action="store_true")
parser.add_argument("--password", default=None)
parser.add_argument("-o", "--output", required=True)
parser.add_argument("input_json")
args = parser.parse_args()

if not args.password_stdin:
    print("expected --password-stdin", file=sys.stderr)
    raise SystemExit(9)

password = sys.stdin.readline().rstrip("\\r\\n")
if not password:
    print("missing password on stdin", file=sys.stderr)
    raise SystemExit(10)

out = Path(args.output)
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text("%s:" + password + "\\n", encoding="utf-8")
"""
            % label,
            encoding="utf-8",
        )
        path.chmod(0o700)

    def test_generate_target_cleans_target_by_default(self):
        """Verifies generateTargetFromSource.sh removes plaintext target on exit by default."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            secrets_path = temp_root / "secrets"
            source_path = secrets_path / "source"
            fake_aegis = temp_root / "fakeDecodeAegis.py"
            fake_bitwarden = temp_root / "fakeDecodeBitwarden.py"

            source_path.mkdir(parents=True)
            (source_path / "aegis-diario.json").write_text("a\n", encoding="utf-8")
            (source_path / "aegis-vault.json").write_text("a\n", encoding="utf-8")
            (source_path / "bitwarden-vault.json").write_text("b\n", encoding="utf-8")

            self._write_fake_decoder(fake_aegis, "aegis")
            self._write_fake_decoder(fake_bitwarden, "bitwarden")

            env = os.environ.copy()
            env["SECRETS_PATH"] = str(secrets_path)
            env["AEGIS_DECODER_PATH"] = str(fake_aegis)
            env["BITWARDEN_DECODER_PATH"] = str(fake_bitwarden)

            result = subprocess.run(
                ["bash", str(GENERATE_TARGET), "--target-root", str(temp_root / "target-root")],
                input="aegis-pass\nbitwarden-pass\n",
                capture_output=True,
                text=True,
                cwd=ROOT,
                env=env,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            target_path = temp_root / "target-root" / "target"
            self.assertFalse(target_path.exists())
            self.assertIn("Target will be cleaned automatically", result.stdout)

    def test_generate_target_keep_target_preserves_plaintext_outputs(self):
        """Verifies --keep-target preserves target and decoders receive passwords via stdin."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            secrets_path = temp_root / "secrets"
            source_path = secrets_path / "source"
            target_root = temp_root / "target-root"
            fake_aegis = temp_root / "fakeDecodeAegis.py"
            fake_bitwarden = temp_root / "fakeDecodeBitwarden.py"

            source_path.mkdir(parents=True)
            (source_path / "aegis-diario.json").write_text("a\n", encoding="utf-8")
            (source_path / "aegis-vault.json").write_text("a\n", encoding="utf-8")
            (source_path / "bitwarden-vault.json").write_text("b\n", encoding="utf-8")

            self._write_fake_decoder(fake_aegis, "aegis")
            self._write_fake_decoder(fake_bitwarden, "bitwarden")

            env = os.environ.copy()
            env["SECRETS_PATH"] = str(secrets_path)
            env["AEGIS_DECODER_PATH"] = str(fake_aegis)
            env["BITWARDEN_DECODER_PATH"] = str(fake_bitwarden)

            result = subprocess.run(
                ["bash", str(GENERATE_TARGET), "--target-root", str(target_root), "--keep-target"],
                input="aegis-pass\nbitwarden-pass\n",
                capture_output=True,
                text=True,
                cwd=ROOT,
                env=env,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            target_path = target_root / "target"
            self.assertTrue((target_path / "aegis-diario-json").is_file())
            self.assertTrue((target_path / "aegis-vault-json").is_file())
            self.assertTrue((target_path / "bitwarden-vault-json").is_file())
            self.assertEqual(
                (target_path / "aegis-diario-json").read_text(encoding="utf-8"),
                "aegis:aegis-pass\n",
            )
            self.assertEqual(
                (target_path / "bitwarden-vault-json").read_text(encoding="utf-8"),
                "bitwarden:bitwarden-pass\n",
            )
            self.assertIn("WARNING: keeping plaintext target", result.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
