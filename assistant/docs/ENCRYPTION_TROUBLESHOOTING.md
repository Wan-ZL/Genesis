# Encryption Troubleshooting Guide

## Overview

Genesis encrypts sensitive settings (API keys, calendar passwords) at rest using AES-256-GCM encryption. The encryption key is derived from your machine's UUID and a salt file stored at `memory/.encryption_key_salt`.

**Critical**: If you lose the salt file, all encrypted data becomes permanently undecryptable.

## Common Issues

### 1. "Decryption failed: InvalidTag" Errors

**Symptoms:**
- Server logs show repeated decryption errors
- Settings appear empty even though they were set before
- `python -m cli settings encryption-status` shows "cannot decrypt"

**Root Causes:**
- Encryption key salt file was deleted or corrupted
- Database was copied from another machine
- Salt file was regenerated (e.g., by deleting and recreating it)

**Solutions:**

#### Option A: Restore Encryption Key Salt (Recommended if you have a backup)

1. Restore `assistant/memory/.encryption_key_salt` from your backup
2. Re-encrypt all keys with the restored key:
   ```bash
   cd assistant
   python -m cli settings reencrypt
   ```
3. Verify encryption health:
   ```bash
   python -m cli settings encryption-status
   ```

#### Option B: Clear Invalid Keys and Re-enter (If no backup available)

1. Check which keys cannot be decrypted:
   ```bash
   cd assistant
   python -m cli settings encryption-status
   ```

2. Clear all undecryptable keys:
   ```bash
   python -m cli settings clear-invalid --confirm
   ```

3. Re-enter your API keys via the Settings UI at http://127.0.0.1:8080

4. Verify they're encrypted:
   ```bash
   python -m cli settings encryption-status
   ```

### 2. Plaintext API Keys

**Symptoms:**
- `encryption-status` shows "WARN" status
- Keys are marked as "plaintext" instead of "encrypted"

**Cause:**
- Keys were set before encryption was enabled
- Encryption library wasn't installed when keys were set

**Solution:**

Encrypt all plaintext keys:
```bash
cd assistant
python -m cli settings encrypt
```

### 3. Encryption Library Not Available

**Symptoms:**
- `encryption-status` shows "Encryption available: No"
- Errors about missing `cryptography` module

**Solution:**

Install the cryptography library:
```bash
pip install cryptography
```

## CLI Commands Reference

### Check Encryption Status

```bash
python -m cli settings encryption-status [--json]
```

Shows detailed status for all sensitive keys:
- Whether encryption is available
- Which keys are encrypted
- Which keys can be decrypted
- Any logged decryption errors

### Encrypt Plaintext Keys

```bash
python -m cli settings encrypt [--json]
```

Migrates any plaintext sensitive keys to encrypted format.

### Clear Invalid Keys

```bash
python -m cli settings clear-invalid --confirm [--json]
```

Deletes all encrypted keys that cannot be decrypted. Use this when:
- You've lost your encryption key salt and have no backup
- You want to start fresh with new API keys

**Warning**: This is destructive. You'll need to re-enter your API keys.

### Re-encrypt with Current Key

```bash
python -m cli settings reencrypt [--json]
```

Re-encrypts all sensitive keys using the current encryption key. Use this after:
- Restoring the encryption key salt from backup
- Fixing corruption in the salt file
- Upgrading encryption algorithm (future)

## Backup Best Practices

### What to Back Up

1. **Encryption Key Salt** (Critical):
   ```bash
   cp assistant/memory/.encryption_key_salt ~/backups/encryption_key_salt.$(date +%Y%m%d)
   ```

2. **Full Assistant Data** (Includes encrypted keys):
   ```bash
   python -m cli backup create --output ~/backups/assistant_backup.tar.gz
   ```

### Backup Schedule

- **Encryption key salt**: Back up immediately after first run, then whenever you change API keys
- **Full data backup**: Daily automated backups (see `backup` CLI)

### Portable Backups

If you need to move encrypted data to another machine:

1. Export your data with the backup command (includes salt):
   ```bash
   python -m cli backup create --output backup.tar.gz
   ```

2. On the new machine, restore:
   ```bash
   python -m cli backup restore --input backup.tar.gz
   ```

The backup includes the encryption salt, so your keys will remain decryptable.

## Startup Health Check

Genesis automatically checks encryption health on startup. If issues are detected, you'll see a single warning in the logs:

```
WARNING: Encryption health check found issues:
  - openai_api_key: encrypted but cannot decrypt (key changed or data corrupted)
Run 'python -m cli settings encryption-status' for details.
```

This check runs once per startup to avoid log spam.

## Log Noise Reduction

If you see repeated decryption errors in the logs, Genesis now:
- Logs each unique error **once per key** (not per request)
- Clears error tracking when decryption succeeds
- Shows accumulated errors in `encryption-status` output

To silence the errors:
1. Fix the underlying issue (restore salt or clear invalid keys)
2. Restart the server - errors won't re-log unless they occur again

## Security Notes

### What Happens on Decryption Failure?

When a key cannot be decrypted:
1. An empty string is returned (NOT the encrypted value)
2. The error is logged once
3. The API client validation will reject the empty key
4. No encrypted data can leak to external services

This "fail-safe" behavior prevents accidentally sending encrypted gibberish to OpenAI/Anthropic APIs.

### Encryption Algorithm

- **Algorithm**: AES-256-GCM (authenticated encryption)
- **Key Derivation**: PBKDF2-HMAC-SHA256, 480,000 iterations (OWASP 2023 recommendation)
- **Key Source**: Machine UUID + persistent salt file
- **Nonce**: Random 96 bits per encryption (never reused)
- **Format**: `ENC:v1:base64(salt):base64(nonce):base64(ciphertext)`

### Key Rotation

Currently, key rotation is not automated. If you need to rotate keys:

1. Back up your current salt:
   ```bash
   cp assistant/memory/.encryption_key_salt assistant/memory/.encryption_key_salt.backup
   ```

2. Generate a new salt (this will break existing encrypted data):
   ```bash
   rm assistant/memory/.encryption_key_salt
   ```

3. Re-enter all API keys via Settings UI (they'll be encrypted with new key)

Future versions may support automated key rotation with grace period.

## Getting Help

If you're still experiencing issues:

1. Run diagnostic:
   ```bash
   python -m cli settings encryption-status --json > encryption_status.json
   ```

2. Check server logs:
   ```bash
   python -m cli logs tail --name error --lines 100
   ```

3. Check if salt file exists:
   ```bash
   ls -la assistant/memory/.encryption_key_salt
   ```

4. Create a GitHub issue with:
   - Output of `encryption-status` (redact any partial key info)
   - Relevant log excerpts (redact API keys)
   - Steps to reproduce
