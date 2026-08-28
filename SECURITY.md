# Security Policy

## Supported code

Only the current `main` source candidate is considered for security fixes. No public release is currently designated as supported.

## Sensitive material

Never commit credentials, SSH keys, tokens, private `bootstrap.env`, server addresses, hostnames, cloud instance identifiers, private paths, research RAW, or unredacted evidence archives.

## Reporting

For destructive-path, shell-injection, archive-integrity, command-execution, or credential-exposure issues, use GitHub's private vulnerability reporting or a private Security Advisory when available. Do not include secrets or exploit-sensitive server details in a public issue.

If private reporting is not enabled, open a minimal public issue requesting a private contact channel and omit all sensitive details. Ordinary non-sensitive defects may use the bug-report issue template.

## Scope expectations

Reports should identify the affected version or commit, operating environment, minimal reproduction, expected fail-closed behavior, and whether any archive or research data may have been exposed. Do not attach real credentials, RAW files, or full server evidence.
