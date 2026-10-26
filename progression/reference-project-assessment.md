# Reference project assessment

Status: initial assessment

Last reviewed: 2026-10-26

## Source reviewed

Workspace reference:

```text
refs/large_mesh_project/
```

The source is a Windows-oriented desktop tool suite for KUKA/LFAM `.src`
programs, CSV height meshes, and related generated artifacts. Some historical
documentation describes it as a 3D-printer bed-mesh project, but the active file
format and workflows are KUKA robot motion tooling.

The reference tree is approximately 2 GB and includes more than source code:

- a Windows virtual environment;
- `node_modules` and packaged VS Code extension output;
- Python bytecode and test caches;
- generated plots and HTML visualizations;
- large input and output `.src` programs;
- current, testing, and legacy application variants.

It must remain a reference source. Only reviewed, headless logic and sanitized
fixtures should be brought into this repository.

## Reusable candidates

### Strong initial candidates

- `mesh_project_core/time_estimator.py`
  - geometric LIN-path time estimation;
  - initial and final layer speed extraction.
- `mesh_project_core/src_file_handler.py`
  - motion extraction and coordinate replacement concepts;
  - DEF identification and renaming concepts.
- `apps/metadata_renamer/src_renamer_with_metadata.py`
  - output naming and metadata-header workflow.
- `apps/src_path_merger/current/velocity_analyzer.py`
  - velocity distribution and contextual classification concepts.

### Candidates requiring additional extraction or validation

- `apps/src_path_merger/current/`
  - useful merge and wipe handling;
  - strongly dependent on marker and block conventions.
- `apps/xyz_adjustor/layer_operations.py`
  - useful layer/segment model;
  - file reconstruction requires review against production-sized fixtures.
- `apps/probing_path_generator/`
  - generation logic is embedded in GUI classes.
- `apps/mesh_speed_compensator/`
  - processing is mixed with project layout, visualization, and GUI behavior.
- CSV and SRC layer editors
  - desktop interaction models require a purpose-built browser UI.

## Technical risks to resolve

1. The shared reader/writer assumes UTF-8 and normalizes line endings.
2. Motion regexes recognize a limited numeric and field-order subset.
3. Time estimation ignores acceleration, blending, PTP duration, and process
   delays.
4. Parser and application variants have diverged.
5. Some tests import historical module paths and do not prove the current layout.
6. Dependency bounds are broad and include desktop-only PySide6 packages.
7. Existing project directories and generated outputs are not appropriate test
   fixtures until reviewed and sanitized.

## Migration decision

Build a new headless package and web service around explicit contracts. Do not
run PySide applications on Fleetlord, import the old project as a package, or
copy the reference repository wholesale.

The first implementation should favor inspection and narrowly controlled
metadata generation. Advanced robot-program transformations remain gated until
the golden regression corpus proves the intended behavior.
