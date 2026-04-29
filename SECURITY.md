<!--
 Copyright 2026 Michael Ryan Hunsaker, M.Ed., Ph.D.

 Licensed under the Apache License, Version 2.0 (the "License");
 you may not use this file except in compliance with the License.
 You may obtain a copy of the License at

     https://www.apache.org/licenses/LICENSE-2.0

 Unless required by applicable law or agreed to in writing, software
 distributed under the License is distributed on an "AS IS" BASIS,
 WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 See the License for the specific language governing permissions and
 limitations under the License.
-->

# Security Policy

## Supported Versions

Only the latest release is actively supported with security fixes.

| Version   | Supported |
| --------- | --------- |
| 2026.04.x | Yes       |
| < 2026.04 | No        |

## Reporting a Vulnerability

**Please do not open a public GitHub Issue for security vulnerabilities.**

Report security issues privately via one of the following channels:

- **GitHub Private Security Advisory**: Use the
  [Security tab → Report a vulnerability](https://github.com/mrhunsaker/3dmakeGUI/security/advisories/new)
  form in this repository.
- **Email**: Send details to `github@mail.hunsakerweb.com` with the subject line
  `[3dmakeGUI SECURITY] <short description>`.

### What to include

A useful report includes:

1. A description of the vulnerability and its potential impact.
2. Steps to reproduce or a minimal proof-of-concept.
3. The version(s) affected.
4. Any suggested mitigations or patches, if known.

### Response timeline

| Milestone                   | Target  |
| --------------------------- | ------- |
| Acknowledgement of report   | 3 days  |
| Initial assessment / triage | 7 days  |
| Patch / advisory published  | 30 days |

If a fix will take longer than 30 days we will notify you and agree on a
coordinated disclosure date.

## Scope

This project is a **GUI wrapper** that launches external CLI tools
(`3dmake`, `openscad`, etc.) supplied by the user. The security boundary is:

- **In scope**: vulnerabilities in the Python application code, dependency
  chain (`nicegui`, `pywebview`, `trimesh`, etc.), and the packaged binary.
- **Out of scope**: vulnerabilities in the underlying `3dmake` / OpenSCAD
  binaries, the host operating system, or user-supplied `.scad` / `.stl`
  files processed by those tools.

## Dependency security

Dependencies are tracked in `pyproject.toml`. To audit the installed
environment for known CVEs run:

```bash
uv run pip-audit
# or
uv run safety check
```

Automated dependency scanning via Dependabot is enabled in `.github/dependabot.yml`.

## Container / packaged-binary notes

- The Dockerfile and Podman configs in this repository run the application as
  a **non-root user** (`appuser`, UID 1001).
- The NiceGUI web server listens on `127.0.0.1:8080` inside the container;
  only bind it to a public interface if you have an authenticating reverse
  proxy in front of it.
- Do **not** mount the host Docker / Podman socket into the container.

## Acknowledgements

We follow the [GitHub coordinated vulnerability disclosure guidelines](https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing-information-about-vulnerabilities/about-coordinated-disclosure-of-security-vulnerabilities).
