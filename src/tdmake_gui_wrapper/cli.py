# Copyright 2026 Michael Ryan Hunsaker, M.Ed., Ph.D.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Spec-driven construction of real ``3dm`` command lines.

Every GUI control that runs 3dm goes through :func:`build_argv`. It produces an
argument *list* (never a shell string) and enforces the same rules as
``3dm.py`` in tdeck/3dmake, so the GUI cannot emit syntax the CLI rejects.

The rules come from ``data/3dm_spec.json``, which ``scripts/sync_spec.py``
derives from the 3dmake source.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
import json
from pathlib import Path
import re
import shlex
import subprocess
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

SPEC_PATH = Path(__file__).with_name("data") / "3dm_spec.json"
_SCALE_RE = re.compile(r"^\d+(\.\d+)?%?$|^\.\d+%?$")
_SIZE_RE = re.compile(r"^\d+x\d+$")


class CliError(ValueError):
    """Raised when a requested invocation would be rejected by ``3dm``."""


@lru_cache(maxsize=1)
def load_spec() -> dict:
    """Load the generated 3dm spec."""
    return json.loads(SPEC_PATH.read_text(encoding="utf-8"))


def public_actions() -> list[dict]:
    """User-invokable actions in 3dm's internal execution order."""
    return [a for a in load_spec()["actions"] if not a["internal"]]


def action_names() -> list[str]:
    return [a["name"] for a in public_actions()]


def _action(name: str) -> dict:
    for a in public_actions():
        if a["name"] == name:
            return a
    raise CliError(f"Unknown action '{name}'")


@dataclass
class Options:
    """Global 3dm options. ``None``/empty means "leave to 3dm's config"."""

    model: str | None = None
    view: str | None = None
    profile: str | None = None
    overlays: list[str] = field(default_factory=list)
    scale: str | None = None
    scale_x: str | None = None
    scale_y: str | None = None
    scale_z: str | None = None
    angles: list[str] = field(default_factory=list)
    interactive: bool = False
    copies: int | None = None
    colorscheme: str | None = None
    image_size: str | None = None
    debug: bool = False


def _clean(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _check_scale(flag: str, value: str) -> str:
    if not _SCALE_RE.match(value):
        raise CliError(f"Invalid value for {flag}, must be a number or percentage (e.g. 1.5 or 150%)")
    return value


def build_argv(
    actions: Sequence[str],
    options: Options | None = None,
    input_file: str | Path | None = None,
) -> list[str]:
    """Build the argument list that follows the ``3dm`` binary.

    Parameters
    ----------
    actions
        One or more 3dm verbs. Order is irrelevant to 3dm (it runs them in its
        fixed internal order); they are emitted as given.
    options
        Global options to translate into flags.
    input_file
        Optional single input file (``.scad``, ``.stl``, ``.gcode`` or ``.ini``).

    Raises
    ------
    CliError
        If 3dm itself would reject the combination.
    """
    opts = options or Options()
    verbs = [str(a).strip().lower() for a in actions if str(a).strip()]
    if not verbs:
        raise CliError("Must provide an action verb")

    # 3dm.py quietly adds `build` when the input file is a .scad (so `3dm info foo.scad`
    # works), *before* it validates the verb set. Mirror that exactly.
    effective = set(verbs)
    if input_file and Path(input_file).suffix.lower() == ".scad":
        effective.add("build")

    spec_actions = [_action(v) for v in sorted(effective)]
    for a in spec_actions:
        if a["isolated"] and len(effective) > 1:
            raise CliError(f"The action '{a['name']}' can only be used on its own")

    order = load_spec()["action_order"]
    ranked = sorted(effective, key=order.index)
    for i, name in enumerate(ranked):
        if _action(name)["last_in_chain"] and ranked[i + 1 :]:
            raise CliError(f"Action '{name}' cannot be followed by other actions. Found: {', '.join(ranked[i + 1:])}")

    argv: list[str] = []

    model = _clean(opts.model)
    infile = Path(input_file) if input_file else None
    if infile is not None:
        accepted = {t for a in spec_actions for t in a["input_file_types"]}
        ext = infile.suffix.lower()
        if not accepted:
            raise CliError("This action does not take an input file")
        if ext not in accepted:
            raise CliError(f"This action does not accept an input file of type {ext}")
        if model:
            raise CliError("Cannot select a model name when using an input file")

    scale = _clean(opts.scale)
    axes = {"--scale-x": _clean(opts.scale_x), "--scale-y": _clean(opts.scale_y), "--scale-z": _clean(opts.scale_z)}
    if scale and any(axes.values()):
        raise CliError("Cannot use 'scale' and per-axis scale options (scale_x/y/z) together")
    enums = load_spec()["enums"]

    if model:
        argv += ["-m", model]
    view = _clean(opts.view)
    if view:
        argv += ["-v", view]
    profile = _clean(opts.profile)
    if profile:
        argv += ["-p", profile]
    for overlay in opts.overlays:
        if _clean(overlay):
            argv += ["-o", _clean(overlay)]
    if scale:
        argv += ["-s", _check_scale("--scale", scale)]
    for flag, value in axes.items():
        if value:
            argv += [flag, _check_scale(flag, value)]
    for angle in opts.angles:
        if angle not in enums["image_angles"]:
            raise CliError(f"Invalid viewpoint angle '{angle}'")
        argv += ["-a", angle]
    scheme = _clean(opts.colorscheme)
    if scheme:
        if scheme not in enums["colorschemes"]:
            raise CliError(f"Invalid color scheme '{scheme}'")
        argv += ["--colorscheme", scheme]
    size = _clean(opts.image_size)
    if size:
        if not _SIZE_RE.match(size):
            raise CliError("Image size must look like 1080x720")
        argv += ["--image-size", size]
    if opts.copies is not None and int(opts.copies) != 1:
        if int(opts.copies) < 1:
            raise CliError("Copies must be at least 1")
        argv += ["-c", str(int(opts.copies))]
    if opts.interactive:
        argv.append("-i")
    if opts.debug:
        argv.append("--debug")

    argv += verbs
    if infile is not None:
        argv.append(str(infile))
    return argv


def needs_terminal(actions: Sequence[str], options: Options | None = None) -> bool:
    """True when the invocation reads stdin or launches an editor.

    Such commands cannot work through a captured pipe, so the GUI must run them
    in a real terminal. ``info`` only reads stdin with ``-i``.
    """
    opts = options or Options()
    for name in actions:
        a = _action(str(name).strip().lower())
        if a["name"] == "info":
            if opts.interactive:
                return True
            continue
        if a["reads_stdin"] or a["launches_editor"]:
            return True
    return False


def with_binary(binary: str | None, argv: Sequence[str]) -> list[str]:
    """Prefix ``argv`` with the resolved binary (or bare ``3dm`` if unknown)."""
    return [binary or "3dm", *argv]


def format_command(argv: Sequence[str]) -> str:
    """Render an argv list as a copy-pasteable, correctly quoted command."""
    if sys.platform.startswith("win"):
        return subprocess.list2cmdline(list(argv))
    return shlex.join(argv)


def parse_custom_command(text: str, binary: str | None) -> list[str]:
    """Turn a user-typed custom command into an argv list (no shell involved).

    A leading ``3dm`` token is replaced by the resolved binary. The result is
    validated like any other invocation, so typos fail before anything is run.
    """
    try:
        tokens = shlex.split(text, posix=not sys.platform.startswith("win"))
    except ValueError as exc:
        raise CliError(f"Could not parse command: {exc}") from exc
    if tokens and tokens[0].lower() in {"3dm", "3dm.exe"}:
        tokens = tokens[1:]
    if not tokens:
        raise CliError("Enter a command first.")
    validate_tokens(tokens)
    return with_binary(binary, tokens)


def split_tokens(tokens: Sequence[str]) -> tuple[list[str], list[str], bool]:
    """Split raw ``3dm`` arguments into ``(verbs, files, interactive)``.

    Unknown dashed options raise :class:`CliError` exactly like ``3dm.py``.
    """
    spec = load_spec()
    flags: dict[str, dict] = {f: o for o in spec["options"] for f in o["flags"]}
    verbs: list[str] = []
    files: list[str] = []
    interactive = False
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok.startswith("-"):
            opt = flags.get(tok)
            if opt is None:
                raise CliError(f"Unknown option(s): {tok}")
            if opt["takes_value"]:
                i += 1
                if i >= len(tokens):
                    raise CliError(f"Option {tok} needs a value")
            elif tok in {"-i", "--interactive"}:
                interactive = True
        elif "." in tok:
            files.append(tok)
        else:
            verbs.append(tok.lower())
        i += 1
    return verbs, files, interactive


def validate_tokens(tokens: Sequence[str]) -> None:
    """Check raw ``3dm`` arguments against the spec's flags and verbs."""
    verbs, files, _ = split_tokens(tokens)
    if verbs:
        build_argv(verbs, Options(), files[-1] if files else None)


def tokens_need_terminal(tokens: Sequence[str]) -> bool:
    """:func:`needs_terminal` for a raw token list (custom commands)."""
    verbs, _, interactive = split_tokens(tokens)
    return bool(verbs) and needs_terminal(verbs, Options(interactive=interactive))
