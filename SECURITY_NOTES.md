# Security Notes

## What Was Fixed

- `decodeAegis.py` and `decodeBitwarden.py` now prompt interactively by default.
- Both decoders support `--password-stdin` for tests and local automation.
- `--password` remains only as an unsafe compatibility mode and prints a warning.
- `generateTargetFromSource.sh` prompts once per secret domain and passes passwords to Python via `stdin`, not via `argv` or environment variables.
- `target` is now cleaned by default on exit.
- `--keep-target` enables explicit inspection mode.
- Documentation now states clearly that `source.7z.sha256` is accidental corruption detection, not attacker-proof authenticity.

## Residual Risks

- `7z` still requires passwords through `-p...`, which leaves a residual exposure in the argv of the `7z` process.
- `source.7z.sha256` does not provide authenticity if an attacker can modify both the archive and the checksum.
- Python and bash cannot guarantee full in-memory zeroization of secrets.
- `target` contains plaintext secrets whenever `--keep-target` is used.
- Aegis and Bitwarden still share the same combined workflow and archive, so compromise impact remains high.

## Recommended Operating Practices

- Prefer the default interactive password flow.
- Avoid `--password` in normal operation.
- Use `--password-stdin` only for local tests or carefully controlled automation.
- Prefer RAM-backed restore/generation paths (`/dev/shm`) when available.
- Avoid `--keep-target` unless you are actively inspecting the derived plaintext.
- Remove or rotate old backups under `backups/` according to your retention policy.
- Treat `source.7z.sha256` as corruption detection only; add signatures or a keyed MAC if you need stronger tamper resistance.
- Run the workflow on a trusted machine and avoid multitasking in a hostile environment while secrets are loaded.
