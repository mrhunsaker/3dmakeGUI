# Security

This page summarizes the project's vulnerability handling policy. For the full
policy text, see [SECURITY.md](https://github.com/mrhunsaker/3dmakeGUI/blob/main/SECURITY.md).

## Supported Versions

Only the most recent release line is actively supported with security fixes.

## Reporting a Vulnerability

Do **not** open a public issue for security reports.

Use one of the private channels:

- GitHub Security Advisory form:
  <https://github.com/mrhunsaker/3dmakeGUI/security/advisories/new>
- Email: `github@mail.hunsakerweb.com`

## Include in Your Report

1. Vulnerability description and potential impact
2. Reproduction steps or proof-of-concept
3. Affected versions
4. Suggested mitigations (if available)

## Response Targets

- Acknowledgement: 3 days
- Initial triage: 7 days
- Fix/advisory target: 30 days

## Security Notes for Containers

Container images and compose specs are designed with a secure default posture:

- non-root runtime user
- dropped Linux capabilities
- read-only root filesystem where practical
- localhost-only published port by default
