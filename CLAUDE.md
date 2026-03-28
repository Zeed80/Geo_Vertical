# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

GeoVertical Analyzer — PyQt6 desktop application for geodetic control of antenna-mast structures (verticality and straightness analysis) per Russian engineering standards (SP 70.13330.2012, GOST R 71949-2025). Supports CSV/TXT/DXF/GeoJSON/Shapefile/Trimble JXL/JobXML/JOB input, 3D editing, and PDF/Excel/DOCX report generation.

## Commands

```bash
# Run application
python main.py

# Install dependencies
pip install -r requirements.txt

# Run all tests
python -m pytest tests

# Run a single test file
python -m pytest tests/test_calculations.py

# Run a single test by name
python -m pytest tests/test_calculations.py::test_group_points_by_height

# Run tests with coverage
python -m pytest tests --cov=core --cov=utils

# Lint (ruff covers core/, utils/, tests/)
ruff check core/ utils/ tests/

# Type check
mypy core/ utils/
```

## Architecture

### Layer Overview

```
main.py
  └── gui/main_window.py          # Top-level application shell (tabs, menus, autosave)
        ├── core/services/         # Orchestration: CalculationService, ProjectManager
        ├── core/                  # Pure business logic (no Qt)
        └── utils/                 # Cross-cutting: reports, logging, settings
```

### Core (business logic, no Qt)

- **`core/data_loader.py`** — Multi-format entry point; detects format, delegates to parsers, returns `LoadedSurveyData` with diagnostics.
- **`core/trimble_loader.py`** — Trimble JOB/JXL/JobXML parser with quality diagnostics and fallback chains.
- **`core/calculations.py`** — Core math: `group_points_by_height()`, `calculate_belt_center()`, `approximate_tower_axis()`, `calculate_vertical_deviation()`, `calculate_straightness_deviation()`. Results are LRU-cached.
- **`core/normatives.py`** — `NormativeChecker` validates deviations against SP 70.13330.2012 and GOST R 71949-2025 tolerances.
- **`core/belt_operations.py`** / **`core/section_operations.py`** — Belt/section assignment, grouping, completion logic.
- **`core/belt_completion.py`** — Advanced belt completion (large file, ~122 KB).
- **`core/tower_generator.py`** — `TowerBlueprint` for programmatic/parametric tower creation; blueprint stored in `.gvproj` for reproducibility.
- **`core/undo_manager.py`** — Full DataFrame + metadata snapshots (max 50), branching undo/redo.
- **`core/exceptions.py`** — 15+ custom exception types rooted in `GeoVerticalError`.
- **`core/import_models.py`** / **`core/full_report_models.py`** — Typed dataclasses for import diagnostics and DO_TSS_2 report schema.
- **`core/services/`** — `CalculationService` (main computation orchestrator), `ProjectManager` (save/load `.gvproj`), report template manager.
- **`core/exporters/`** — DXF, GeoJSON, KML, SCAD schema exporters.
- **`core/data_loader_async.py`** / **`core/calculation_thread.py`** — Non-blocking import and background computation.

### GUI (PyQt6)

- **`gui/main_window.py`** — Application shell: tab interface (data / calculations / plots / 3D editor / full report), project lifecycle, dark theme, 3-minute autosave.
- **`gui/data_table.py`** — Editable table (x, y, z, belt columns); real-time validation; syncs with 3D editor.
- **`gui/point_editor_3d.py`** / **`gui/editor_3d.py`** — PyOpenGL-based 3D point/tower viewer and editor.
- **`gui/data_import_wizard.py`** / **`gui/second_station_import_wizard.py`** — File selection, format detection, coordinate system, multi-station workflows.
- **`gui/lattice_editor.py`** / **`gui/enhanced_tower_preview.py`** — Tower constructor: section definition UI + PyQtGraph GLView live preview.
- **`gui/calculation_tab.py`** / **`gui/full_report_tab.py`** — Calculation workflow and DO_TSS_2 report builder.
- **`gui/plots_widget.py`** — Matplotlib-based graphs for verticality and straightness results.

### Utils

- **`utils/coordinate_systems.py`** — EPSG code management, auto-detection, coordinate transformations.
- **`utils/report_generator.py`** / **`utils/report_generator_enhanced.py`** — PDF/Excel report generation.
- **`utils/full_report_builder.py`** — DO_TSS_2 DOCX generation.
- **`utils/logging_config.py`** — Centralized logging with file rotation.
- **`utils/settings_manager.py`** — Application settings persistence.

### Data Flow

```
File import → DataLoader → LoadedSurveyData (DataFrame + diagnostics)
    → DataTable (GUI) ↔ UndoManager snapshots
    → CalculationService → belt grouping → axis fit → deviations
    → NormativeChecker → compliance flags
    → Plots / Tables / Report exporters
```

### Project File (.gvproj)

JSON-serialized bundle: survey DataFrame, belt assignments, TowerBlueprint, calculation results, report metadata. Managed by `core/services/ProjectManager`.

## Key Conventions

- All UI strings and docstrings are in **Russian**.
- Belt (пояс) = horizontal group of points at the same nominal height; section (секция) = vertical segment between belts.
- Tolerance formulas: verticality `Δ = 0.001 × h`; straightness `δ = L / 750`.
- `core/` must not import from `gui/` — keep business logic Qt-free.
- Heavy computations run in `core/calculation_thread.py` (QThread) to keep the UI responsive.
