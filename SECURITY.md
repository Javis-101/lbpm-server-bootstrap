# Security Policy

## Supported code

The immutable v1.0.3 artifact is the validated historical release line. Security fixes are developed on `main` and ship only in a new version after appropriate validation; the original v1.0.3 ZIP is never rewritten in place.

## Sensitive material

Never commit credentials, SSH keys, tokens, private `bootstrap.env`, server addresses, hostnames, cloud instance identifiers, private paths, research RAW, or unredacted evidence archives.

The v1.0.3 installer was validated with its documented default stack path. Do not supply `/`, a system directory, a relative path, or a dot-segment path as a custom installer prefix. Repository `main` adds a fail-closed prefix guard for the future v1.0.4 line.

## Reporting

For destructive-path, shell-injection, archive-integrity, command-execution, or credential-exposure issues, use GitHub's private vulnerability reporting or a private Security Advisory when available. Do not include secrets or exploit-sensitive server details in a public issue.

If private reporting is not enabled, open a minimal public issue requesting a private contact channel and omit all sensitive details. Ordinary non-sensitive defects may use the bug-report issue template.

## Scope expectations

Reports should identify the affected version or commit, operating environment, minimal reproduction, expected fail-closed behavior, and whether any archive or research data may have been exposed. Do not attach real credentials, RAW files, or full server evidence.
