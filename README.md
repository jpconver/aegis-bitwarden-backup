# Aegis / Bitwarden Backup Workflow

Utilities for keeping encrypted Aegis and Bitwarden exports in one encrypted
archive, with optional Dropbox upload and temporary plaintext generation for
local inspection.

The project uses three concepts:

- `source/`: encrypted exports from Aegis and Bitwarden. This is the source of truth.
- `source.7z`: encrypted archive of `source/`. This is the persistent backup.
- `target/`: decrypted derived output for inspection. This is temporary and contains plaintext secrets.

## Security Model

- Normal workflows prompt for passwords interactively.
- The shell scripts pass decoder passwords to Python through `stdin`, not through argv or environment variables.
- `target/` is cleaned automatically by default. Use `--keep-target` only when you need to inspect the derived files.
- `source.7z.sha256` detects accidental corruption only. It is not an authenticity check if an attacker can replace both files.
- `7z` requires passwords via `-p...`, so `zipSource.sh` and `generateSourceFromZipFile.sh` still have residual argv exposure while `7z` is running.

## Requirements

- `bash`
- `python3`
- `7z`
- `sha256sum`
- Python packages from `requirements.txt`

Setup:

```bash
./setup_venv.sh
```

Or install dependencies manually:

```bash
pip install -r requirements.txt
```

## Configuration

Scripts resolve paths in this order:

1. CLI flags such as `--secrets-path`
2. Environment variables
3. `~/.config/aegis/config.env`, or the file pointed to by `AEGIS_CONFIG_FILE`
4. Defaults under `~/projects/security/secrets` and `~/.config/aegis`

Supported config values:

```text
AEGIS_SECRETS_PATH
AEGIS_STATE_DIR
AEGIS_DROPBOX_CREDENTIALS_FILE
```

Use the recovery checklist below to create the local config file and directories.

## Full PC Setup Or Recovery

Use this checklist when setting up a fresh machine or rebuilding the workflow
from scratch.

Clone the repository:

```bash
mkdir -p ~/workspaces
cd ~/workspaces
git clone git@github.com:YOUR_USER/aegis-bitwarden-backup.git
cd aegis-bitwarden-backup
```

Create the local config:

```bash
mkdir -p ~/.config/aegis
cat > ~/.config/aegis/config.env <<'EOF'
AEGIS_SECRETS_PATH="$HOME/projects/security/secrets"
AEGIS_STATE_DIR="$HOME/.config/aegis"
AEGIS_DROPBOX_CREDENTIALS_FILE="$HOME/.config/aegis/dropbox.json"
EOF
```

Create the secrets directory:

```bash
mkdir -p "$HOME/projects/security/secrets/source"
```

The secrets directory uses this layout:

```text
$AEGIS_SECRETS_PATH/
  source/            encrypted exports
  source.7z          encrypted backup archive
  source.7z.sha256   checksum for accidental corruption detection
  target/            temporary derived plaintext output
  backups/           previous source.7z copies
```

Configure Dropbox credentials if you want to upload backups:

```bash
python3 ./authenticateDropbox.py \
  --app-key YOUR_DROPBOX_APP_KEY \
  --app-secret YOUR_DROPBOX_APP_SECRET \
  --credentials-file ~/.config/aegis/dropbox.json
```

This command writes `~/.config/aegis/dropbox.json` with `app_key`,
`app_secret`, and `refresh_token`. If you already have those values from a
separate secure record, you can create that JSON file manually instead. Do not
commit it.

Place encrypted exports in `$HOME/projects/security/secrets/source/`:

```text
aegis-diario.json
aegis-vault.json
bitwarden-diario.json
bitwarden-vault.json
```

Create the encrypted archive:

```bash
./zipSource.sh
```

Upload it after Dropbox credentials are configured:

```bash
./uploadToDropbox.sh
```

## Standard Operation

Use this flow when Aegis or Bitwarden changed and you need to refresh the
backup.

Export the changed vaults from Aegis or Bitwarden, then copy the encrypted JSON
files into:

```text
$AEGIS_SECRETS_PATH/source/
```

Use the expected filenames from the next section. Replace only the files that
changed.

Rebuild the encrypted archive:

```bash
cd ~/workspaces/aegis-bitwarden-backup
./zipSource.sh
```

The archive password is requested twice and must match. The script writes
`source.7z`, writes `source.7z.sha256`, and backs up any previous archive under
`backups/`.

Upload the new archive if Dropbox upload is configured:

```bash
./uploadToDropbox.sh
```

## Expected Source Files

Place encrypted exports in `source/` with these names:

```text
aegis-diario.json
aegis-vault.json
bitwarden-diario.json
bitwarden-vault.json
```

The Aegis files must be encrypted Aegis JSON exports.

Bitwarden files are optional, but when present they must be password-protected
encrypted JSON exports. The derived plaintext Bitwarden JSON is written only to
`target/`.

## Inspect Derived Plaintext

Generate `target/` from the current source:

```bash
./generateTargetFromSource.sh --keep-target
```

Expected derived files:

```text
aegis-diario-json
aegis-vault-json
bitwarden-diario-json
bitwarden-vault-json
```

Without `--keep-target`, `target/` is removed automatically before the script exits.

## RAM-Backed Paths

When `/dev/shm` exists and is writable, restore and target generation default to
RAM-backed paths. You can also pass explicit roots:

```bash
./generateSourceFromZipFile.sh --source-root /dev/shm/aegis-source
./generateTargetFromSource.sh --source-root /dev/shm/aegis-source --target-root /dev/shm/aegis-target
./zipSource.sh --source-root /dev/shm/aegis-source
```

Use `--paranoid` to require `/dev/shm` for restore or target generation.

## Exporting Files

### Aegis

In Aegis:

1. Open `Settings -> Import & Export -> Export`.
2. Select `Aegis (.json)`.
3. Enable `Encrypt the vault`.
4. Save the file.
5. Copy it into `source/` as either `aegis-diario.json` or `aegis-vault.json`.

### Bitwarden

In each Bitwarden vault:

1. Open `Settings -> Vault Options -> Export`.
2. Select `Json (Encrypted)`.
3. Select `Use same vault password`.
4. Save the file.
5. Copy it into `source/` as either `bitwarden-diario.json` or `bitwarden-vault.json`.

## Dropbox Upload

Dropbox upload is optional. It uploads `source.7z` and, when requested,
`source.7z.sha256`.

### Create A Dropbox App

In the Dropbox App Console:

```text
https://www.dropbox.com/developers/apps
```

Create a scoped app, enable `files.content.write`, and add this redirect URI:

```text
http://127.0.0.1:53682/callback
```

### Create Local Credentials

Edit `authenticateDropbox.sh` and replace the placeholder app key and app
secret, or run the Python command directly:

```bash
python3 ./authenticateDropbox.py \
  --app-key YOUR_DROPBOX_APP_KEY \
  --app-secret YOUR_DROPBOX_APP_SECRET \
  --credentials-file ~/.config/aegis/dropbox.json
```

This stores a local credentials JSON containing the app key, app secret, and
refresh token. Do not commit that file.

### Upload

Use the wrapper:

```bash
./uploadToDropbox.sh
```

Or call Python directly:

```bash
python3 ./uploadToDropbox.py \
  --credentials-file ~/.config/aegis/dropbox.json \
  --include-checksum
```

Upload to a specific Dropbox folder:

```bash
python3 ./uploadToDropbox.py \
  --credentials-file ~/.config/aegis/dropbox.json \
  --dropbox-folder /backups/aegis
```

You can also pass credentials through flags:

```bash
python3 ./uploadToDropbox.py \
  --app-key YOUR_DROPBOX_APP_KEY \
  --app-secret YOUR_DROPBOX_APP_SECRET \
  --refresh-token YOUR_DROPBOX_REFRESH_TOKEN
```

## Scripts

- `zipSource.sh`: compresses `source/` into `source.7z` and writes `source.7z.sha256`.
- `generateSourceFromZipFile.sh`: verifies the checksum when present and restores `source/`.
- `generateTargetFromSource.sh`: generates temporary decrypted `target/` output.
- `generateTargetFromZipFile.sh`: restores `source/` and then generates `target/`.
- `decodeAegis.py`: decrypts encrypted Aegis JSON exports.
- `decodeBitwarden.py`: decrypts password-protected encrypted Bitwarden JSON exports.
- `authenticateDropbox.py`: creates the initial Dropbox refresh-token credentials file.
- `uploadToDropbox.py`: uploads `source.7z` and optionally its checksum.
- `copyToUsb.sh`: copies the archive, checksum, and backups to removable storage.
- `testSmoke.sh`: runs smoke tests.

Most scripts support `--help`:

```bash
./zipSource.sh --help
./generateSourceFromZipFile.sh --help
./generateTargetFromSource.sh --help
./generateTargetFromZipFile.sh --help
```

## Password Handling

Use interactive prompts for normal operation.

The Python decoders also support:

- `--password-stdin` for tests or controlled local automation.
- `--password` as an unsafe compatibility mode. It prints a warning because it exposes secrets through argv.
- `--no-output` to validate password and format without writing decrypted output.

Examples:

```bash
python3 ./decodeAegis.py export-aegis.json --no-output
python3 ./decodeBitwarden.py export-bitwarden.json --no-output
printf '%s\n' 'password' | python3 ./decodeBitwarden.py export-bitwarden.json --password-stdin --no-output
```

## Physical Recovery Codes

Keep physical recovery or verification codes separately from this digital
backup. Include the generation date, group labels, and enough context to know
which service each code belongs to. Store the paper in a secure physical
location and destroy outdated versions.

## Testing

Run the smoke suite:

```bash
./testSmoke.sh
```

## Public Repository Checklist

Before publishing a repository that uses these scripts, make sure these are not
tracked:

- `source/`
- `target/`
- `source.7z`
- `source.7z.sha256`
- `backups/`
- local Dropbox credentials JSON files
- real Aegis or Bitwarden exports
