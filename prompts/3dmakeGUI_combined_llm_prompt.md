# TASK: Bring mrhunsaker/3dmakeGUI to 100% parity with tdeck/3dmake, with direct CLI execution

You are an expert TypeScript/VS Code-extension engineer. Work in a fresh clone of https://github.com/mrhunsaker/3dmakeGUI and, for reference, https://github.com/tdeck/3dmake (clone it; do not use web fetch).

## Hard requirements
1. Every GUI control must spawn the real `3dm` binary with a real argv array (shell:false). No re-implementation of 3dm behaviour, no direct file opens in place of `edit-*` verbs, no stdout regex where a deterministic output path exists.
2. Every action, global flag, and config key in DOCUMENT 1 must be reachable from the GUI and covered by an automated test that asserts the exact argv.
3. Fix every defect in DOCUMENT 2 (`defects_found`) first (7+ commands currently emit syntax that 3dm rejects).
4. Implement DOCUMENT 3 work items in the stated sequencing. Start with WI-00 (read tdeck/3dmake `actions/__init__.py` and `actions/*.py`, resolve every field marked verify/likely/inferred in DOCUMENT 1, and update the spec) before writing feature code.
5. Preserve and extend accessibility (accessibilityInformation, aria-live, toasts, keyboard shortcuts).
6. Treat DOCUMENT 1 as a starting hypothesis, not gospel: where the real CLI source or `3dm help` disagrees, the CLI wins; update the spec and note the change in CHANGELOG.

## Working method
- First output: a short written audit of the repo (all front-ends found, files to change), then proceed.
- Commit per work item with message `WI-xx: ...`. Run compile, lint, unit, contract tests after each.
- Finish with COVERAGE.md generated from the spec showing zero uncovered rows, plus docs/CLI_EQUIVALENTS.md.
- Ask a question only if blocked; otherwise state the assumption and continue.

---
## DOCUMENT 1: 3dmake_functions.json
```json
{
  "meta": {
    "title": "Complete inventory of tdeck/3dmake (3dm) CLI functions",
    "source_repo": "https://github.com/tdeck/3dmake (the URL in the request said 'fithub.com'; treated as a typo for github.com)",
    "sources_read": [
      "README.md (main)",
      "3dm.py (main, 353 lines: full argparse definition, verb resolution, pipeline loop)",
      "CLAUDE.md (architecture, action file list, preview planes)",
      "Release notes v0.2, v0.3, v0.4, v0.6, v0.65, v0.8"
    ],
    "confidence_legend": {
      "verified": "Stated in README/3dm.py/CLAUDE.md/release notes",
      "inferred": "Deduced from those sources, not seen in the action's own source file",
      "verify": "Must be confirmed by running `3dm help` and reading actions/*.py before relying on it"
    },
    "known_gaps": [
      "actions/__init__.py (ALL_ACTIONS_IN_ORDER) and each actions/*.py were not readable (GitHub robots block on tree/raw). The exact verb list and implied_actions/isolated/last_in_chain flags are reconstructed from README + 3dm.py + CLAUDE.md. Step 0 of the remediation plan regenerates this file from `3dm help` and the source to close the gap.",
      "Version of 3dmake covered: current main (README mentions scale options, preview planes, min_3dmake_version, which post-date v0.8)."
    ],
    "binary_names": ["3dm", "3dm.py (source: python 3dm.py, Python 3.13, uv)"]
  },

  "invocation_grammar": {
    "form": "3dm [global options] <action> [<action> ...] [input_file]",
    "rules": [
      "Multiple actions can be chained; they execute in the fixed internal order ALL_ACTIONS_IN_ORDER, NOT the order typed (verified: 3dm.py iterates ALL_ACTIONS_IN_ORDER and runs those present in the verb set).",
      "Verbs are case-insensitive (lowercased) (verified).",
      "Dashed options may be interleaved with actions (parse_known_args) (verified). Unknown dashed options are a hard error 'Unknown option(s): ...' (verified).",
      "Any trailing token containing a '.' is treated as an input file; more than one input file is an error 'Multiple inputs not supported yet' (verified).",
      "Any non-dashed token without a '.' is treated as an action verb; an unknown one errors \"Unknown action 'x'\" (verified). Consequence: `3dm new myproject` is invalid.",
      "If the first input file is .scad, 'build' is added to the verb set automatically (verified).",
      "Implied actions are added recursively, e.g. print implies slice (verified in README: 'print implies that 3DMake must slice').",
      "Actions flagged isolated cannot be combined with other actions: error \"The action 'x' can only be used on its own\" (verified mechanism; which verbs are isolated: setup, help, version at minimum per CLAUDE.md; self-update is checked by name in the update notice).",
      "Actions flagged last_in_chain cannot be followed by later actions in internal order (verified mechanism; likely print) .",
      "Single-file mode (input file given): build dir is a temp dir; model name derives from file stem; outputs are copied to the current directory and 'Result is in <file>' printed (verified). --model cannot be combined with an input file.",
      "Accepted input types are per action (input_file_types): .stl, .scad, .gcode (verified mechanism; exact per-action mapping: verify). Action with no input types errors 'This action does not take an input file'.",
      "Project discovery: ./3dmake.toml, else ../3dmake.toml ('Using 3DMake project in parent directory...') (verified). Project settings override global defaults.toml, CLI flags override both (verified).",
      "If the config dir does not exist and the verb is not 'setup', 3dm interactively offers to run setup (verified).",
      "Errors print 'ERORR: <message>' (sic) without stack trace unless --debug (verified). Exit codes: 1 on error, 2 on Ctrl+C (verified).",
      "After running, a background update check may print '3DMake X is available (you have Y). Run '3dm self-update' to install it.' (verified)."
    ],
    "pipeline_order_known": ["build", "measure (internal)", "orient", "preview", "slice", "print"],
    "pipeline_order_note": "Position of info, image, edit-*, list-*, test-connect, install-libraries relative to the pipeline is verify. CLAUDE.md lists pipeline: Build -> Measure -> Orient -> Preview -> Slice -> Print."
  },

  "global_options": [
    {"id": "scale", "flags": ["-s", "--scale"], "takes_value": true, "value": "factor (1.5) or percentage (150%)", "repeatable": false, "overrides_config": "scale", "constraints": "Cannot be combined with --scale-x/-y/-z or per-axis config keys", "applies_to": ["build", "orient", "slice", "preview", "info", "image"], "confidence": "verified"},
    {"id": "scale_x", "flags": ["--scale-x", "--sx"], "takes_value": true, "value": "factor or percentage", "overrides_config": "scale_x", "confidence": "verified"},
    {"id": "scale_y", "flags": ["--scale-y", "--sy"], "takes_value": true, "value": "factor or percentage", "overrides_config": "scale_y", "confidence": "verified"},
    {"id": "scale_z", "flags": ["--scale-z", "--sz"], "takes_value": true, "value": "factor or percentage", "overrides_config": "scale_z", "confidence": "verified"},
    {"id": "model", "flags": ["-m", "--model"], "takes_value": true, "value": "model name; trailing .scad is stripped", "overrides_config": "model_name", "constraints": "Invalid with an input file", "confidence": "verified"},
    {"id": "view", "flags": ["-v", "--view"], "takes_value": true, "value": "3sil | frontsil | backsil | leftsil | rightsil | topsil | <preview plane name e.g. level#1>", "overrides_config": "view", "applies_to": ["preview"], "confidence": "verified"},
    {"id": "profile", "flags": ["-p", "--profile"], "takes_value": true, "value": "printer profile name (see list-profiles)", "overrides_config": "printer_profile", "applies_to": ["slice", "print", "edit-profile", "edit-overlay", "preview"], "confidence": "verified"},
    {"id": "overlay", "flags": ["-o", "--overlay"], "takes_value": true, "repeatable": true, "value": "overlay name (see list-overlays)", "overrides_config": "overlays", "applies_to": ["slice", "print", "edit-overlay"], "confidence": "verified"},
    {"id": "angle", "flags": ["-a", "--angle"], "takes_value": true, "repeatable": true, "value": "front|back|left|right|top|bottom|above_front|above_front_left|above_front_right|above_back_left|above_back_right", "overrides_config": "image_angles", "applies_to": ["image", "info"], "confidence": "verified"},
    {"id": "interactive", "flags": ["-i", "--interactive"], "takes_value": false, "overrides_config": "interactive", "applies_to": ["info"], "note": "Opens a follow-up Q&A loop on stdin; requires a TTY/stdin passthrough", "confidence": "verified"},
    {"id": "copies", "flags": ["-c", "--copies"], "takes_value": true, "type": "int", "default": 1, "overrides_config": "copies", "applies_to": ["slice", "print"], "confidence": "verified"},
    {"id": "colorscheme", "flags": ["--colorscheme"], "takes_value": true, "value": "slicer_light | slicer_dark | light_on_dark", "overrides_config": "colorscheme", "applies_to": ["image", "info"], "confidence": "verified"},
    {"id": "image_size", "flags": ["--image-size"], "takes_value": true, "value": "WIDTHxHEIGHT e.g. 640x480", "overrides_config": "image_size", "applies_to": ["image", "info"], "confidence": "verified"},
    {"id": "debug", "flags": ["--debug"], "takes_value": false, "overrides_config": "debug", "effect": "Verbose output and full stack traces", "confidence": "verified"},
    {"id": "help_flag", "flags": ["-h", "--help"], "takes_value": false, "effect": "Prints help and exits (same as 3dm help)", "confidence": "verified"},
    {"id": "version_flag", "flags": ["--version"], "takes_value": false, "effect": "Prints version and exits (same as 3dm version)", "confidence": "verified"}
  ],

  "actions": [
    {"name": "setup", "category": "setup", "summary": "Interactive first-time/upgrade configuration: creates config dir, copies default profiles/overlays, asks for default printer profile, OctoPrint host/key, Gemini key, Ollama model. On upgrade preserves settings and optionally modified profiles/overlays.", "isolated": true, "needs_project": false, "input_files": [], "options_used": [], "interactive_stdin": true, "writes": ["<config_dir>/defaults.toml", "<config_dir>/profiles/*", "<config_dir>/overlays/*"], "confidence": "verified"},
    {"name": "new", "category": "project", "summary": "Create a new 3DMake project in the CURRENT directory (src/, build/, 3dmake.toml with strict_warnings=true; default main.scad template with $fs/$fa and a sphere). Takes no name argument.", "isolated": "verify", "needs_project": false, "input_files": [], "options_used": [], "interactive_stdin": "verify", "writes": ["3dmake.toml", "src/main.scad", "build/"], "confidence": "verified"},
    {"name": "edit-model", "category": "edit", "summary": "Open src/<model>.scad in the configured editor.", "options_used": ["model"], "needs_project": true, "uses_config": ["editor", "edit_in_background"], "launches_external_process": true, "confidence": "verified"},
    {"name": "edit-overlay", "category": "edit", "summary": "Open an overlay .ini in the editor; creates it if missing (asks whether it is printer-specific, stored under overlays/<profile>/).", "options_used": ["overlay", "profile"], "interactive_stdin": true, "launches_external_process": true, "confidence": "verified"},
    {"name": "edit-profile", "category": "edit", "summary": "Open an existing printer profile .ini in the editor (cannot create new printer profiles).", "options_used": ["profile"], "launches_external_process": true, "confidence": "verified"},
    {"name": "edit-global-config", "category": "edit", "summary": "Open defaults.toml in the editor.", "options_used": [], "launches_external_process": true, "confidence": "verified"},
    {"name": "edit-prompt", "category": "edit", "summary": "Open the LLM prompt file used by info; first run seeds the default prompt. Supports $object_count placeholder.", "options_used": [], "launches_external_process": true, "confidence": "verified"},
    {"name": "build", "category": "pipeline", "summary": "OpenSCAD .scad -> STL in build/ (live elapsed-time output). Applies libraries/local_libraries, strict_warnings, scale options. Collects preview plane names.", "options_used": ["model", "scale", "scale_x", "scale_y", "scale_z", "debug"], "input_files": [".scad"], "needs_project": "unless input file", "outputs": ["build/<model>.stl"], "confidence": "verified"},
    {"name": "orient", "category": "pipeline", "summary": "Auto-orient (Tweaker3) for printing; produces <model>-oriented.stl. Implies build for .scad sources.", "options_used": ["model", "scale"], "input_files": [".stl", ".scad"], "implied_actions": ["build"], "outputs": ["build/<model>-oriented.stl"], "confidence": "verified (implied_actions: inferred)"},
    {"name": "preview", "category": "pipeline", "summary": "Flat tactile silhouette preview as SVG plus thin extruded STL; or a cross-section at a named preview plane. Output SVG styling via svg_stroke_width / svg_fill_color.", "options_used": ["view", "model"], "input_files": [".stl", ".scad"], "outputs": ["build/<stem>-<view>.svg", "build/<stem>-<view>.stl"], "notes": ["Silhouette views: 3sil, frontsil, backsil, leftsil, rightsil, topsil", "Plane views: name defined in SCAD via xy_preview_plane/xz_preview_plane from 3dmake/preview.scad; selected with -v level#1; forces fresh build; uses un-oriented model"], "confidence": "verified"},
    {"name": "slice", "category": "pipeline", "summary": "PrusaSlicer to GCODE using profile + overlays; prints filament length, weight and per-extrusion-type breakdown; errors if object exceeds build plate in X/Y/Z; honors copies and scale.", "options_used": ["profile", "overlay", "copies", "scale", "model"], "input_files": [".stl", ".scad"], "outputs": ["build/<project>-<model>.gcode"], "confidence": "verified"},
    {"name": "print", "category": "pipeline", "summary": "Send GCODE to printer. Implies slice. print_mode: octoprint | bambu_connect | bambu_lan. auto_start_prints controls whether the print starts immediately.", "implied_actions": ["slice"], "last_in_chain": "likely", "input_files": [".stl", ".scad", ".gcode"], "uses_config": ["print_mode", "octoprint_host", "octoprint_key", "bambu_host", "bambu_access_code", "bambu_serial_number", "auto_start_prints"], "confidence": "verified"},
    {"name": "test-connect", "category": "printer", "summary": "Test connection to OctoPrint or Bambu printer without printing.", "uses_config": ["print_mode", "octoprint_host", "octoprint_key", "bambu_host", "bambu_access_code", "bambu_serial_number"], "input_files": [], "confidence": "verified (v0.8 release note)"},
    {"name": "info", "category": "inspect", "summary": "Describe a model: bounding-box dimensions always; with Gemini/OpenRouter/Ollama/OpenAI-compatible configured, renders multiple angles and returns an AI description. -i enables interactive follow-up questions.", "options_used": ["model", "angle", "interactive", "image_size", "colorscheme", "scale"], "input_files": [".stl", ".scad"], "interactive_stdin": "with -i", "uses_config": ["gemini_key", "llm_name", "openrouter_key", "openai_compat_host", "openai_api_key", "interactive", "image_angles"], "confidence": "verified"},
    {"name": "image", "category": "inspect", "summary": "Render PNG images of the model from named angles on an x-y grid, auto-centered/zoomed.", "options_used": ["angle", "image_size", "colorscheme", "model"], "input_files": [".stl", ".scad"], "outputs": ["build/<model>-<angle>.png"], "confidence": "verified"},
    {"name": "list-profiles", "category": "config", "summary": "List available printer profiles.", "input_files": [], "confidence": "verified"},
    {"name": "list-overlays", "category": "config", "summary": "List available overlays.", "input_files": [], "confidence": "verified"},
    {"name": "list-libraries", "category": "libraries", "summary": "List library-manager libraries with documentation URLs.", "input_files": [], "confidence": "verified"},
    {"name": "install-libraries", "category": "libraries", "summary": "Download libraries named in the project's libraries list that are not present. Local libraries need no install.", "needs_project": true, "confidence": "verified"},
    {"name": "self-update", "category": "maintenance", "summary": "Upgrade 3DMake to the latest release.", "isolated": "likely", "confidence": "verified"},
    {"name": "version", "category": "maintenance", "summary": "Print version and the 3DMake config folder location.", "isolated": true, "confidence": "verified"},
    {"name": "help", "category": "maintenance", "summary": "List all actions (docstrings come from handler functions).", "isolated": true, "confidence": "verified"}
  ],

  "internal_actions_not_user_invocable": [
    {"name": "measure", "note": "measure_action.py: extracts mesh metrics (bounding box); appears to be an internal pipeline step", "confidence": "inferred"}
  ],

  "config_keys": [
    {"key": "project_name", "type": "string", "default": "project folder name", "cli_flag": null},
    {"key": "model_name", "type": "string", "default": "main", "cli_flag": "-m"},
    {"key": "view", "type": "string", "default": "3sil", "cli_flag": "-v"},
    {"key": "printer_profile", "type": "string", "default": "set in setup", "cli_flag": "-p"},
    {"key": "scale", "type": "float|percent-string", "cli_flag": "-s"},
    {"key": "scale_x", "type": "float|percent-string", "cli_flag": "--scale-x"},
    {"key": "scale_y", "type": "float|percent-string", "cli_flag": "--scale-y"},
    {"key": "scale_z", "type": "float|percent-string", "cli_flag": "--scale-z"},
    {"key": "overlays", "type": "list[string]", "default": [], "cli_flag": "-o"},
    {"key": "print_mode", "type": "enum", "values": ["octoprint", "bambu_connect", "bambu_lan"], "default": "octoprint"},
    {"key": "octoprint_host", "type": "url"},
    {"key": "octoprint_key", "type": "secret"},
    {"key": "bambu_host", "type": "string"},
    {"key": "bambu_access_code", "type": "secret"},
    {"key": "bambu_serial_number", "type": "string"},
    {"key": "auto_start_prints", "type": "bool", "default": true},
    {"key": "strict_warnings", "type": "bool", "default": false, "note": "true in newly created projects"},
    {"key": "editor", "type": "string"},
    {"key": "edit_in_background", "type": "bool"},
    {"key": "gemini_key", "type": "secret"},
    {"key": "llm_name", "type": "string"},
    {"key": "openrouter_key", "type": "secret"},
    {"key": "openai_compat_host", "type": "url"},
    {"key": "openai_api_key", "type": "secret"},
    {"key": "interactive", "type": "bool", "default": false, "cli_flag": "-i"},
    {"key": "libraries", "type": "list[string]", "default": []},
    {"key": "local_libraries", "type": "list[path]", "default": []},
    {"key": "image_angles", "type": "list[string]", "default": ["above_front_left", "above_front", "above_front_right"], "cli_flag": "-a"},
    {"key": "image_size", "type": "WxH", "default": "1080x720", "cli_flag": "--image-size"},
    {"key": "copies", "type": "int", "default": 1, "cli_flag": "-c"},
    {"key": "colorscheme", "type": "enum", "values": ["slicer_light", "slicer_dark", "light_on_dark"], "default": "slicer_dark", "cli_flag": "--colorscheme"},
    {"key": "svg_stroke_width", "type": "float(mm)", "default": 1},
    {"key": "svg_fill_color", "type": "css-color-name", "default": "oldLace"},
    {"key": "debug", "type": "bool", "default": false, "cli_flag": "--debug"},
    {"key": "min_3dmake_version", "type": "version-string", "note": "Project-level; 3dm refuses to run if older (from 3dm.py)", "confidence": "verified in 3dm.py, undocumented in README table"}
  ],

  "config_files_and_locations": [
    {"path": "<config_dir>/defaults.toml", "purpose": "Global settings", "edit_action": "edit-global-config"},
    {"path": "./3dmake.toml (or ../3dmake.toml)", "purpose": "Project settings; overrides defaults.toml", "edit_action": null, "note": "No dedicated edit action; GUI must open the file directly"},
    {"path": "<config_dir>/profiles/*.ini", "purpose": "PrusaSlicer printer profiles", "edit_action": "edit-profile"},
    {"path": "<config_dir>/overlays/**/*.ini", "purpose": "Setting overlays; printer-specific under overlays/<profile>/", "edit_action": "edit-overlay"},
    {"path": "<config_dir>/<prompt file>", "purpose": "LLM prompt for info", "edit_action": "edit-prompt"},
    {"path": "<project>/src/<model>.scad", "purpose": "OpenSCAD model source", "edit_action": "edit-model"},
    {"path": "<project>/build/", "purpose": "Outputs: .stl, -oriented.stl, .gcode, .svg, .png"}
  ],

  "environment": [
    {"name": "THREEDMAKE_CONFIG_DIR", "purpose": "Overrides the config directory (default platformdirs user_config_path('3dmake'))", "confidence": "verified"},
    {"name": "VISUAL / EDITOR", "purpose": "Fallback editors on macOS/Linux when 'editor' unset (else nano)", "confidence": "verified (README footnote)"}
  ],

  "scad_library": {
    "builtin_library_path": "scad_library/3dmake",
    "modules": [
      {"name": "xy_preview_plane(name, index)", "file": "3dmake/preview.scad", "purpose": "Marks an XY cross-section plane for preview -v name#index"},
      {"name": "xz_preview_plane(name)", "file": "3dmake/preview.scad", "purpose": "Marks an XZ cross-section plane"}
    ],
    "library_manager": "libraries = [...] in 3dmake.toml then `3dm install-libraries`; imports use lowercase folder name (use <bosl/shapes.scad>)",
    "note": "Authoring-time SCAD feature; GUI can expose a plane picker populated from build metadata (preview_plane_names)"
  },

  "feature_checklist_for_gui_parity": {
    "actions_total_user_invocable": 22,
    "global_flags_total": 16,
    "config_keys_total": 35,
    "must_expose_non_obvious": [
      "Action chaining with fixed internal order and implied actions",
      "Single input file mode (stl/scad/gcode) with outputs copied to cwd",
      "Repeatable -o and -a",
      "Per-axis scale and percent syntax",
      "Interactive stdin for setup, edit-overlay, info -i, self-update confirmation",
      "Preview plane views (-v name#N)",
      "test-connect",
      "edit-prompt",
      "--debug",
      "Project config editing (3dmake.toml) and min_3dmake_version"
    ]
  }
}
```

## DOCUMENT 2: 3dmake_gui_functions.json
```json
{
  "meta": {
    "title": "Functions currently addressed by mrhunsaker/3dmakeGUI",
    "repo": "https://github.com/mrhunsaker/3dmakeGUI",
    "evidence": "The repo tree could not be fetched (GitHub blocks automated access). This inventory is taken from the published README of the repo's vscode-extension (VS Code Marketplace TVIResources.vscode-3dmake-gui, version listing 2026.5.2 / VSIX 2026.4.29), which states it is built from 3dmakeGUI/vscode-extension and 'wraps every 3dm subcommand'.",
    "limitations": [
      "If 3dmakeGUI contains other front-ends (e.g. a desktop or web GUI) beside vscode-extension/, they are NOT covered here. Step 0 of the remediation plan scans the whole repo and appends them.",
      "'cli_executed' is what the extension README says it runs. The 'cli_correct' verdicts are derived by checking each string against the argparse and verb-resolution logic in tdeck/3dmake 3dm.py, not by running it."
    ],
    "implementation_facts": {
      "language": "TypeScript (VS Code extension)",
      "process_model": "Node child_process spawn; stdout/stderr streamed to an Output Channel (README)",
      "binary_resolution": "setting 3dmake.binaryPath, else PATH, else env THREE_DM_PATH / THREEDM_PATH",
      "settings": ["3dmake.binaryPath", "3dmake.defaultModel", "3dmake.defaultView", "3dmake.defaultProfile", "3dmake.showOutputOnRun", "3dmake.announceCommandCompletion"]
    }
  },

  "gui_commands": [
    {"id": "selectProject", "label": "Select Project File or Directory", "cli_executed": null, "kind": "gui_only", "cli_correct": "n/a"},
    {"id": "build", "label": "Build STL", "cli_executed": "3dm build", "real_cli": "3dm build", "cli_correct": true, "extra": "opens .stl in built-in viewer"},
    {"id": "slice", "label": "Slice", "cli_executed": "3dm slice", "real_cli": "3dm slice (project-mode STL must exist or 3dm must imply build: verify)", "cli_correct": true, "extra": "opens .gcode in editor"},
    {"id": "orient", "label": "Orient", "cli_executed": "3dm orient", "real_cli": "3dm orient", "cli_correct": true},
    {"id": "preview", "label": "Preview (SVG)", "cli_executed": "3dm preview", "real_cli": "3dm preview [-v VIEW]", "cli_correct": true},
    {"id": "buildSlice", "label": "Build + Slice", "cli_executed": "3dm build --slice", "real_cli": "3dm build slice", "cli_correct": false, "why": "'--slice' is a dashed token not defined in argparse -> 'Unknown option(s): --slice'. Actions are positional verbs."},
    {"id": "fullPipeline", "label": "Full Pipeline (Build + Orient + Slice)", "cli_executed": "3dm build --orient --slice", "real_cli": "3dm build orient slice", "cli_correct": false, "why": "'--orient' and '--slice' are unknown options."},
    {"id": "info", "label": "Describe (Info)", "cli_executed": "3dm info", "real_cli": "3dm info [-i] [-a ANGLE ...] [--image-size WxH] [--colorscheme C]", "cli_correct": true, "gap": "No -i, -a, --image-size, --colorscheme; README mislabels it 'model metadata'"},
    {"id": "print", "label": "Print", "cli_executed": "3dm print", "real_cli": "3dm print [-p P] [-o O ...] [-c N]", "cli_correct": true},
    {"id": "editSource", "label": "Open/Edit Source", "cli_executed": null, "kind": "gui_only_opens_file", "real_cli": "3dm edit-model [-m MODEL]", "cli_correct": "bypasses CLI", "why": "Opens src/*.scad in VS Code instead of running edit-model; acceptable inside an IDE but violates 'direct execution' requirement; also ignores -m and the default-template creation."},
    {"id": "exportImages", "label": "Export Images", "cli_executed": "3dm images", "real_cli": "3dm image", "cli_correct": false, "why": "'images' is not an action -> \"Unknown action 'images'\"."},
    {"id": "newProject", "label": "New Project", "cli_executed": "3dm new <name>", "real_cli": "3dm new (run with cwd = target directory)", "cli_correct": false, "why": "'<name>' without a '.' is parsed as an action verb -> \"Unknown action '<name>'\"; 'new' takes no name."},
    {"id": "setup", "label": "Run Setup", "cli_executed": "3dm setup", "real_cli": "3dm setup", "cli_correct": "partial", "why": "Setup is interactive (stdin prompts). The extension spawns with piped output and no stdin passthrough, so prompts cannot be answered unless a terminal is used (verify)."},
    {"id": "listLibraries", "label": "List Libraries", "cli_executed": "3dm libraries --list", "real_cli": "3dm list-libraries", "cli_correct": false, "why": "'libraries' unknown action and '--list' unknown option."},
    {"id": "installLibraries", "label": "Install Libraries", "cli_executed": "3dm libraries --install", "real_cli": "3dm install-libraries", "cli_correct": false, "why": "Same as above."},
    {"id": "listProfiles", "label": "List Profiles", "cli_executed": "3dm profiles", "real_cli": "3dm list-profiles", "cli_correct": false, "why": "'profiles' is not an action."},
    {"id": "listOverlays", "label": "List Overlays", "cli_executed": "3dm overlays", "real_cli": "3dm list-overlays", "cli_correct": false, "why": "'overlays' is not an action."},
    {"id": "version", "label": "Show Version", "cli_executed": "3dm version", "real_cli": "3dm version", "cli_correct": true},
    {"id": "selfUpdate", "label": "Self-Update", "cli_executed": "3dm self-update", "real_cli": "3dm self-update", "cli_correct": "partial", "why": "May prompt for confirmation on stdin (verify); no stdin passthrough."},
    {"id": "help", "label": "Show Help", "cli_executed": "3dm help", "real_cli": "3dm help", "cli_correct": true},
    {"id": "customCommand", "label": "Run Custom Command", "cli_executed": "3dm <user args>", "real_cli": "3dm <user args>", "cli_correct": true, "note": "Escape hatch; keep it but it must not be the only route to missing features"},
    {"id": "viewStl", "label": "View STL in 3D Viewer", "cli_executed": null, "kind": "gui_only", "note": "Binary STL only"},
    {"id": "viewSvg", "label": "View Last SVG Preview", "cli_executed": null, "kind": "gui_only"},
    {"id": "setBinaryPath", "label": "Set 3dm Binary Path", "cli_executed": null, "kind": "gui_only"},
    {"id": "openGlobalConfig", "label": "Open Global Config (defaults.toml)", "cli_executed": null, "kind": "gui_only_opens_file", "real_cli": "3dm edit-global-config", "cli_correct": "bypasses CLI"},
    {"id": "openProjectConfig", "label": "Open Project Config (3dmake.toml)", "cli_executed": null, "kind": "gui_only_opens_file", "real_cli": "(no CLI equivalent)", "cli_correct": "n/a"},
    {"id": "refreshProject", "label": "Refresh Project View", "cli_executed": null, "kind": "gui_only"}
  ],

  "gui_options_exposed": [
    {"label": "Model (-m)", "flag": "-m", "free_text": true},
    {"label": "View (-v)", "flag": "-v", "note": "setting enumerates 6 silhouette values only; plane views not offered"},
    {"label": "Profile (-p)", "flag": "-p", "free_text": true, "note": "no picker from list-profiles"},
    {"label": "Overlay (-o)", "flag": "-o", "note": "single value; CLI supports repeating -o"}
  ],

  "gui_shortcuts": ["Ctrl+Alt+B build", "Ctrl+Alt+E edit source", "Ctrl+Alt+P preview", "Ctrl+Alt+O select project", "Ctrl+Alt+V view STL", "Ctrl+Alt+X custom command"],

  "coverage_summary": {
    "cli_actions_total": 22,
    "cli_actions_correctly_reachable_from_gui": ["build", "slice", "orient", "preview", "info", "print", "setup (partial)", "version", "self-update (partial)", "help"],
    "cli_actions_reachable_but_with_WRONG_command": ["image (as 'images')", "new (as 'new <name>')", "list-libraries", "install-libraries", "list-profiles", "list-overlays"],
    "cli_actions_with_no_gui_control": ["edit-model (bypassed)", "edit-overlay", "edit-profile", "edit-global-config (bypassed)", "edit-prompt", "test-connect"],
    "global_flags_exposed": 4,
    "global_flags_total": 16,
    "global_flags_missing": ["-s/--scale", "--scale-x/--sx", "--scale-y/--sy", "--scale-z/--sz", "-a/--angle", "-i/--interactive", "-c/--copies", "--colorscheme", "--image-size", "--debug", "-h/--help (via help action only)", "--version (via version action only)"],
    "config_keys_editable_in_gui": 0,
    "config_keys_total": 35,
    "input_file_mode_supported": false,
    "chaining_supported": "only two hardcoded chains, both with invalid syntax",
    "stdin_interaction_supported": false
  },

  "defects_found": [
    {"id": "D1", "severity": "blocker", "text": "7 commands emit syntax that 3dm rejects (build --slice, build --orient --slice, images, new <name>, libraries --list, libraries --install, profiles, overlays). These cannot have worked against current 3dm."},
    {"id": "D2", "severity": "high", "text": "Actions are modeled as ad-hoc subcommand strings, not derived from 3dm's verb/flag model, so drift is guaranteed."},
    {"id": "D3", "severity": "high", "text": "No stdin passthrough: setup, edit-overlay prompts, info -i, self-update confirmations cannot work."},
    {"id": "D4", "severity": "medium", "text": "edit-* actions bypassed with direct file opens, so edit_in_background/editor config and template/creation logic of 3dm are skipped."},
    {"id": "D5", "severity": "medium", "text": "Output parsing for post-run behaviour (open STL/SVG/images) is heuristic ('detected from output'); should use deterministic build/ paths."}
  ]
}
```

## DOCUMENT 3: 3dmakeGUI_remediation.json
```json
{
  "meta": {
    "title": "Remediation plan: 100% 3dm CLI parity in 3dmakeGUI with direct CLI execution",
    "inputs": ["3dmake_functions.json", "3dmake_gui_functions.json"],
    "target": "mrhunsaker/3dmakeGUI (assumed TypeScript VS Code extension in vscode-extension/; adapt paths if other front-ends exist)",
    "non_negotiable_requirement": "Every GUI control executes the real `3dm` binary with a real argv. The GUI never reimplements 3dm behaviour (no direct file opens in place of edit-*, no JS re-implementation of slicing/orient/preview, no output scraping where a deterministic path exists).",
    "definition_of_done": "Every entry in 3dmake_functions.json (actions, global_options, config_keys, input-file mode, interactive prompts) has a reachable GUI control, an automated test asserting the exact argv, and appears in the generated coverage report with zero gaps."
  },

  "design_principles": [
    "Single source of truth: 3dmake_functions.json (checked into the repo as spec/3dm_spec.json) drives argv construction, command-palette registration, menus, and tests. Adding a flag means editing JSON, not code.",
    "No shell: spawn(binary, argvArray, {shell:false}). Never string-concatenate commands. Quote-safe on Windows paths.",
    "Show-what-runs: before and after every run, display the exact command line (copyable) in the Output channel, and expose a 'Copy as CLI command' action. This makes the GUI verifiably non-approximate.",
    "Chains are built as positional verbs in any order (3dm sorts them); the GUI offers a verb multi-select instead of hardcoded pipelines.",
    "Interactive actions run in a real terminal (VS Code Pseudoterminal/Terminal API with node-pty or vscode.window.createTerminal + sendText-free ExecutionTask) so stdin prompts work; non-interactive actions stream to the Output channel for screen-reader aria-live.",
    "Accessibility is preserved: every new control carries accessibilityInformation; completion toasts and aria-live regions remain."
  ],

  "work_items": [
    {
      "id": "WI-00", "title": "Ground truth sync (regenerate spec from the real CLI)", "priority": 0,
      "steps": [
        "Add scripts/sync_spec.ts that runs `3dm help` and parses the action list/docstrings, and runs `3dm <verb> --help`-equivalents where available; diff against spec/3dm_spec.json and fail CI on drift.",
        "Read tdeck/3dmake actions/__init__.py once (git clone, not web) to fill every 'verify'/'likely'/'inferred' field in spec: isolated, last_in_chain, implied_actions, input_file_types, internal vs user verbs, ALL_ACTIONS_IN_ORDER.",
        "Scan all of 3dmakeGUI (not just vscode-extension/) and append any other front-ends or commands to 3dmake_gui_functions.json."
      ],
      "acceptance": ["spec has no 'verify' strings", "CI job `spec-drift` passes against pinned 3dm version and against latest release"]
    },
    {
      "id": "WI-01", "title": "Core: CLI runner and argv builder (the only place 3dm is invoked)", "priority": 1,
      "files": ["src/core/spec.ts", "src/core/argv.ts", "src/core/runner.ts", "src/core/binary.ts"],
      "design": {
        "ThreeDmRequest": {
          "actions": "string[] (verbs, validated against spec; order irrelevant)",
          "globalOptions": "typed map keyed by spec.global_options[].id; repeatable options are arrays",
          "inputFile": "optional absolute path; enforces: <=1, extension in union of accepted types of chosen actions, mutually exclusive with `model`",
          "cwd": "project directory (or directory for `new`)",
          "env": "optional overrides e.g. THREEDMAKE_CONFIG_DIR",
          "mode": "'stream' | 'terminal'"
        },
        "buildArgv(req)": "Emits [ ...flagPairs, ...actions, inputFile? ]. Flags use their canonical long form from spec. Repeatables expand as `-o a -o b`. Validates: scale XOR per-axis, view enum or plane pattern, image-size WxH, copies>=1, colorscheme enum, angle enum, percent syntax. Dashed tokens must come from spec only (guards against D1-type bugs).",
        "validateChain(req)": "Rejects isolated actions combined with others (setup, help, version, self-update, plus whatever WI-00 finds), and actions after last_in_chain per internal order, mirroring 3dm.py messages.",
        "runner": "spawn with shell:false, cwd, env; streams stdout/stderr; returns {argv, exitCode, durationMs, outputs[]}; exit code 2 = user cancelled; supports cancel (SIGINT, then SIGTERM after 3s); captures --debug traces.",
        "binary resolution": "keep 3dmake.binaryPath / THREE_DM_PATH / THREEDM_PATH / PATH; additionally support `python 3dm.py` launcher via setting 3dmake.launcher = ['uv','run','python','/path/3dm.py']",
        "outputs discovery": "After success, compute deterministic expected outputs from spec (build/<model>.stl, -oriented.stl, <project>-<model>.gcode, <stem>-<view>.svg/.stl, <model>-<angle>.png) and stat them; fall back to a before/after directory diff of build/. Do not rely on regex over stdout."
      },
      "acceptance": ["argv unit tests (WI-12) cover every spec entry", "no other file in repo imports child_process"]
    },
    {
      "id": "WI-02", "title": "Fix the 8 broken commands (immediate, ships first)", "priority": 1,
      "mapping": [
        {"gui": "Build + Slice", "old": "3dm build --slice", "new_argv": ["build", "slice"]},
        {"gui": "Full Pipeline", "old": "3dm build --orient --slice", "new_argv": ["build", "orient", "slice"]},
        {"gui": "Export Images", "old": "3dm images", "new_argv": ["image"]},
        {"gui": "New Project", "old": "3dm new <name>", "new_argv": ["new"], "note": "Prompt for a folder name in the GUI, mkdir it, then spawn with cwd = that folder. Folder creation is GUI chrome, project scaffolding is 3dm's."},
        {"gui": "List Libraries", "old": "3dm libraries --list", "new_argv": ["list-libraries"]},
        {"gui": "Install Libraries", "old": "3dm libraries --install", "new_argv": ["install-libraries"]},
        {"gui": "List Profiles", "old": "3dm profiles", "new_argv": ["list-profiles"]},
        {"gui": "List Overlays", "old": "3dm overlays", "new_argv": ["list-overlays"]}
      ],
      "acceptance": ["Each runs against real 3dm without 'Unknown action'/'Unknown option(s)'", "e2e tests WI-12 pass"]
    },
    {
      "id": "WI-03", "title": "Universal options panel covering all 16 global flags", "priority": 2,
      "ui": "Replace the 4-item Command Options tree with a form-like tree/QuickPick flow grouped by: Model & input (-m, input file), Scale (-s | --sx/--sy/--sz with mutual exclusion), Printing (-p picker populated from `3dm list-profiles`, -o multi-select populated from `3dm list-overlays`, -c), Preview (-v: silhouette enum + plane names discovered from build output/build metadata), Images/AI (-a multi-select of 11 angles, --image-size with presets 640x480/1080x720/1920x1080/custom, --colorscheme enum, -i), Diagnostics (--debug).",
      "behaviour": [
        "Each option shows 'unset (config default)' vs explicit; only explicit values become argv flags.",
        "Options not applicable to the selected action are greyed with reason (from spec applies_to) but remain settable.",
        "Pickers for -p/-o call the real list-* actions (cached per session, refresh button).",
        "Session options persist per-project in workspaceState; a 'Reset options' command clears them."
      ],
      "acceptance": ["All 16 flags settable", "argv preview matches settings"]
    },
    {
      "id": "WI-04", "title": "Action runner UI: all 22 actions + chain composer", "priority": 2,
      "ui": [
        "Generate one command `3dmake.run.<action>` per spec action (package.json contributes generated by scripts/gen_contributions.ts at build time).",
        "Quick Actions tree grouped by spec category: Pipeline (build, orient, preview, slice, print), Inspect (info, image), Printer (test-connect), Libraries (list-libraries, install-libraries), Config (list-profiles, list-overlays), Edit (edit-model, edit-overlay, edit-profile, edit-global-config, edit-prompt), Project (new, setup), Maintenance (self-update, version, help).",
        "'Compose chain...' command: multi-select verbs -> shows implied actions and final internal order (computed from spec) -> shows exact argv -> Run.",
        "Keep 'Run Custom Command' as escape hatch, but route it through the same runner/validator with a warning (not error) on unknown tokens."
      ],
      "acceptance": ["tests enumerate spec.actions and assert a registered command for each", "chain composer rejects isolated+other and post-last_in_chain combos with 3dm's wording"]
    },
    {
      "id": "WI-05", "title": "Input-file (non-project) mode", "priority": 2,
      "ui": "Command `Run on file...` and Explorer context menu on .scad/.stl/.gcode: choose actions allowed for that extension (from spec input_file_types), run with cwd = file's folder (3dm copies outputs to cwd and prints 'Result is in ...'), then reveal result files.",
      "rules": ["Disable `-m` when an input file is chosen (mirrors 3dm.py error).", ".gcode accepted only by actions that list it (print)."],
      "acceptance": ["`3dm slice turtle.stl` and `3dm build orient print pyramid.stl` reproducible from GUI with identical argv"]
    },
    {
      "id": "WI-06", "title": "Interactive actions via real terminal / pty", "priority": 2,
      "applies_to": ["setup", "new (if it prompts)", "edit-overlay (printer-specific prompt)", "info -i", "self-update", "any first-run 'set up now?' prompt"],
      "design": [
        "RunMode 'terminal': create a vscode Pseudoterminal backed by node-pty (fallback: Terminal with shellPath=binary and shellArgs=argv) so the user answers prompts directly; argv shown first.",
        "Spec flag interactive_stdin drives mode selection; unknown/'with -i' resolved at request time.",
        "Output of terminal runs is also copied to the Output channel when feasible for screen-reader users; otherwise announce via status message 'Interactive 3dm session started in terminal'.",
        "Detect the 'set them up now?' first-run prompt: if exit/stdout matches, offer to rerun `setup` in terminal mode."
      ],
      "acceptance": ["Setup completes end-to-end from GUI on a clean config dir (test with THREEDMAKE_CONFIG_DIR temp dir)", "info -i accepts a follow-up question"]
    },
    {
      "id": "WI-07", "title": "Edit actions execute the real edit-* verbs", "priority": 2,
      "design": [
        "Replace direct-open of scad/defaults.toml with spawn of `3dm edit-model [-m]`, `edit-global-config`, `edit-profile -p`, `edit-overlay -o [-p]`, `edit-prompt`.",
        "Editor handling: 3dm launches the user's configured `editor`. If `editor` is unset, the GUI offers to set it to `code --wait`-style or `code` (writes via a settings form WI-08, not silently) and sets edit_in_background appropriately (false for terminal editors, true for GUI editors; per README footnote 3).",
        "Edit actions are 'detached': GUI does not block on the editor; it re-scans project on window focus.",
        "edit-overlay prompts (create new? printer-specific?) run in terminal mode (WI-06).",
        "`Open Project Config (3dmake.toml)` remains a GUI file open (no CLI equivalent exists) and is labelled as such."
      ],
      "acceptance": ["Spying on spawn shows argv for each edit verb", "creating a new overlay via GUI produces the .ini under the correct overlays/ path"]
    },
    {
      "id": "WI-08", "title": "Configuration editor for all 35 config keys (defaults.toml and 3dmake.toml)", "priority": 3,
      "design": [
        "Settings webview/tree generated from spec.config_keys with types, defaults, enums, validation, secret masking (octoprint_key, bambu_access_code, gemini_key, openrouter_key, openai_api_key).",
        "Scope switch: Global (defaults.toml, path from `3dm version`) vs Project (3dmake.toml in project or parent dir, mirroring 3dm discovery).",
        "Write with a comment-preserving TOML library (e.g. @iarna/toml cannot preserve comments; use `smol-toml` + targeted text patching or `taplo` WASM) so hand-edited files are not mangled; always back up to .bak before write.",
        "Show effective value and its origin (global/project/CLI) using the same cascade as 3dm.py: defaults.toml < 3dmake.toml < CLI.",
        "List-typed keys (libraries, local_libraries, overlays, image_angles) get add/remove UIs; libraries picker fed by `3dm list-libraries`, with 'Install now' chained to `install-libraries`.",
        "Include min_3dmake_version, print_mode conditional sections (octoprint_* / bambu_*), and a 'Test connection' button that runs `3dm test-connect`."
      ],
      "acceptance": ["Round-trip test: edit every key, re-run `3dm` with --debug and confirm values loaded", "Secrets never logged to Output channel (argv never contains secrets; config values are file-only)"]
    },
    {
      "id": "WI-09", "title": "Per-action UX specifics (everything not covered above)", "priority": 3,
      "items": [
        {"action": "slice", "detail": "Parse and present filament length/weight and extrusion-type breakdown as a structured summary but keep raw output visible. Chain-aware: choose profile/overlays/copies in a single dialog."},
        {"action": "print", "detail": "Confirmation dialog showing print_mode, host (masked), auto_start_prints; offers 'Run test-connect first'."},
        {"action": "test-connect", "detail": "New first-class command plus button in the printer settings group."},
        {"action": "preview", "detail": "View picker = 6 silhouettes + plane names. Plane discovery: run `build` and read preview_plane_names via the build output contract (WI-00 determines the stable source); cache by scad mtime. Open resulting SVG/STL."},
        {"action": "image", "detail": "Multi-select angles, size, colorscheme; open resulting PNGs in an accessible gallery with alt text '<model> viewed from <angle>'."},
        {"action": "info", "detail": "Checkbox 'interactive' -> terminal mode; non-interactive streams to Output."},
        {"action": "orient", "detail": "Open build/<model>-oriented.stl in the STL viewer."},
        {"action": "install-libraries", "detail": "Offer after any change to the libraries list."},
        {"action": "self-update", "detail": "Terminal mode; after exit, re-resolve binary and show new version via `3dm version`."},
        {"action": "version", "detail": "Parse config dir from output to power 'Open config folder'."},
        {"action": "help", "detail": "Show full `3dm help` text in a read-only document for screen readers."},
        {"action": "new", "detail": "Create folder, run `3dm new` with cwd=folder, then refresh Project view and open src/main.scad via `edit-model`."}
      ]
    },
    {
      "id": "WI-10", "title": "Viewers and project tree follow deterministic outputs", "priority": 4,
      "design": ["STL viewer: add ASCII STL parsing (current limitation: binary only) or convert; add -oriented.stl and preview .stl recognition.", "Project view lists build/ outputs by pattern from spec outputs[]; includes .png images and .svg.", "Remove stdout-regex-based 'detect last SVG' logic in favour of runner.outputs."]
    },
    {
      "id": "WI-11", "title": "Version awareness and compatibility", "priority": 4,
      "design": ["On activation run `3dm version`; parse version; compare with spec.min_supported; warn on older 3dm lacking verbs (e.g. test-connect since v0.8, list-profiles since v0.4).", "Disable controls whose action is absent in `3dm help` output of the installed binary (runtime capability detection) instead of failing.", "Surface 3dm's own update notice from stdout as a notification offering `self-update`."]
    },
    {
      "id": "WI-12", "title": "Test suite proving non-approximation", "priority": 1,
      "layers": [
        {"name": "unit", "what": "For each spec action and each global option: buildArgv golden tests; invalid combos (scale+scale_x, model+inputFile, isolated+other, bad enum) rejected with 3dm-equivalent messages.", "tool": "vitest/mocha"},
        {"name": "contract", "what": "Spawn a fake `3dm` shim that records argv/stdin/cwd; trigger EVERY registered GUI command programmatically via vscode.commands.executeCommand in @vscode/test-electron; assert recorded argv equals expected.", "coverage_gate": "100% of spec.actions and spec.global_options exercised"},
        {"name": "e2e-real-cli", "what": "In CI install pinned 3dm release (+ OpenSCAD, PrusaSlicer bundled in release) and run: new, edit-model (EDITOR=true), build, orient, preview (each view), slice, image, info (no LLM), list-*, install-libraries, version, help, test-connect (expect graceful failure), build slice via chain composer, input-file mode with test_fixtures from tdeck/3dmake.", "env": "THREEDMAKE_CONFIG_DIR=<tmp>"},
        {"name": "spec-drift", "what": "WI-00 job fails if `3dm help` actions != spec actions."},
        {"name": "a11y", "what": "Assert every contributed tree item and command has accessibilityInformation/title."}
      ]
    },
    {
      "id": "WI-13", "title": "Generated coverage report and docs", "priority": 5,
      "design": ["scripts/coverage_report.ts emits COVERAGE.md and coverage.json mapping each spec entry -> GUI command id -> test id; CI fails if any row empty.", "Rewrite README command table from spec (fixes mislabels such as 'Describe (Info)' = metadata).", "Add docs/CLI_EQUIVALENTS.md: every GUI control -> exact argv template."]
    }
  ],

  "action_to_gui_matrix": [
    {"action": "setup", "gui": "Settings & Tools > Run Setup", "argv": ["setup"], "mode": "terminal", "wi": "WI-06"},
    {"action": "new", "gui": "Project > New Project", "argv": ["new"], "cwd": "chosen folder", "mode": "terminal-if-prompts", "wi": "WI-02/WI-09"},
    {"action": "edit-model", "gui": "Edit > Edit Model", "argv": ["edit-model", "[-m M]"], "mode": "detached", "wi": "WI-07"},
    {"action": "edit-overlay", "gui": "Edit > Edit Overlay", "argv": ["edit-overlay", "-o NAME", "[-p P]"], "mode": "terminal", "wi": "WI-07"},
    {"action": "edit-profile", "gui": "Edit > Edit Profile", "argv": ["edit-profile", "-p P"], "mode": "detached", "wi": "WI-07"},
    {"action": "edit-global-config", "gui": "Edit > Edit Global Config", "argv": ["edit-global-config"], "mode": "detached", "wi": "WI-07"},
    {"action": "edit-prompt", "gui": "Edit > Edit AI Prompt", "argv": ["edit-prompt"], "mode": "detached", "wi": "WI-07"},
    {"action": "build", "gui": "Pipeline > Build", "argv": ["build", "[opts]"], "mode": "stream", "wi": "WI-04"},
    {"action": "orient", "gui": "Pipeline > Orient", "argv": ["orient", "[opts]"], "mode": "stream", "wi": "WI-04"},
    {"action": "preview", "gui": "Pipeline > Preview", "argv": ["preview", "[-v V]"], "mode": "stream", "wi": "WI-09"},
    {"action": "slice", "gui": "Pipeline > Slice", "argv": ["slice", "[-p -o -c]"], "mode": "stream", "wi": "WI-09"},
    {"action": "print", "gui": "Pipeline > Print", "argv": ["print", "[-p -o -c]"], "mode": "stream", "wi": "WI-09"},
    {"action": "test-connect", "gui": "Printer > Test Connection", "argv": ["test-connect"], "mode": "stream", "wi": "WI-09"},
    {"action": "info", "gui": "Inspect > Describe Model", "argv": ["info", "[-i] [-a ...] [--image-size] [--colorscheme]"], "mode": "stream|terminal(-i)", "wi": "WI-06/WI-09"},
    {"action": "image", "gui": "Inspect > Export Images", "argv": ["image", "[-a ...] [--image-size] [--colorscheme]"], "mode": "stream", "wi": "WI-02/WI-09"},
    {"action": "list-profiles", "gui": "Config > List Profiles", "argv": ["list-profiles"], "mode": "stream+cache", "wi": "WI-02/WI-03"},
    {"action": "list-overlays", "gui": "Config > List Overlays", "argv": ["list-overlays"], "mode": "stream+cache", "wi": "WI-02/WI-03"},
    {"action": "list-libraries", "gui": "Libraries > List", "argv": ["list-libraries"], "mode": "stream+cache", "wi": "WI-02/WI-08"},
    {"action": "install-libraries", "gui": "Libraries > Install", "argv": ["install-libraries"], "mode": "stream", "wi": "WI-02"},
    {"action": "self-update", "gui": "Settings & Tools > Self-Update", "argv": ["self-update"], "mode": "terminal", "wi": "WI-06"},
    {"action": "version", "gui": "Settings & Tools > Version", "argv": ["version"], "mode": "stream", "wi": "WI-09/WI-11"},
    {"action": "help", "gui": "Settings & Tools > Help", "argv": ["help"], "mode": "stream->document", "wi": "WI-09"}
  ],

  "global_option_to_gui_matrix": [
    {"flag": "-s/--scale", "gui": "Options > Scale (uniform)", "validation": "float or N%; excludes per-axis"},
    {"flag": "--scale-x/--sx", "gui": "Options > Scale X"},
    {"flag": "--scale-y/--sy", "gui": "Options > Scale Y"},
    {"flag": "--scale-z/--sz", "gui": "Options > Scale Z"},
    {"flag": "-m/--model", "gui": "Options > Model (picker from src/*.scad)", "validation": "disabled with input file"},
    {"flag": "-v/--view", "gui": "Options > Preview view"},
    {"flag": "-p/--profile", "gui": "Options > Profile (picker from list-profiles)"},
    {"flag": "-o/--overlay", "gui": "Options > Overlays (multi-select from list-overlays)"},
    {"flag": "-a/--angle", "gui": "Options > Image angles (multi-select, 11 values)"},
    {"flag": "-i/--interactive", "gui": "Options > Interactive info"},
    {"flag": "-c/--copies", "gui": "Options > Copies"},
    {"flag": "--colorscheme", "gui": "Options > Color scheme"},
    {"flag": "--image-size", "gui": "Options > Image size"},
    {"flag": "--debug", "gui": "Options > Debug output"},
    {"flag": "-h/--help", "gui": "Help action"},
    {"flag": "--version", "gui": "Version action"}
  ],

  "sequencing": [
    {"phase": 1, "items": ["WI-00", "WI-01", "WI-02", "WI-12 (unit+contract layers)"], "outcome": "Nothing emits invalid syntax; harness proves it"},
    {"phase": 2, "items": ["WI-03", "WI-04", "WI-05", "WI-06", "WI-07"], "outcome": "All actions and flags reachable, interactive and edit verbs real"},
    {"phase": 3, "items": ["WI-08", "WI-09", "WI-10", "WI-11"], "outcome": "Config editor, per-action polish, viewers, compatibility"},
    {"phase": 4, "items": ["WI-12 (e2e-real-cli, a11y)", "WI-13"], "outcome": "CI-enforced parity"}
  ],

  "risks_and_open_questions": [
    "Exact verb/implied/isolated metadata is unconfirmed (see WI-00); do not hardcode it before running the sync.",
    "node-pty is a native module: packaging per platform/Electron ABI may be painful; fallback is a VS Code Terminal with shellPath/shellArgs, which needs no native code but gives less control.",
    "Plane-name discovery relies on build stderr `_3dm_log_scalar` lines (CLAUDE.md); confirm whether plain `3dm build` output exposes them to a caller, otherwise parse build output or run OpenSCAD logging per CLAUDE.md.",
    "Windows quoting and paths with spaces: always argv arrays; test on Windows CI.",
    "Secrets: config editor writes secrets to files only; never pass them in argv or log them.",
    "If 3dmakeGUI has non-VS Code front-ends, WI-01 core must be extracted to a shared package first."
  ]
}
```
