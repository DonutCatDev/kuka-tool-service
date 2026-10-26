# Initial browser slice local validation

Date: 2026-10-26

Scope: SRC inspection, idealized runtime estimation, metadata annotation, and
authenticated browser routes

## Result

The initial source implementation passed its local Python checks. It has not
been deployed to Fleetlord and has not received operator or robot-side
acceptance.

## Automated checks

Command:

```bash
PYTHON=.venv/bin/python scripts/check.sh
```

Environment and result:

- Linux Python 3.13.5
- Flask 3.1.3
- pytest 9.0.2
- 18 tests passed
- package dependency check reported no broken requirements
- Python compilation passed
- deployment wheel built successfully and contained the required HTML templates
  and CSS package data
- Git whitespace validation passed
- Docker was unavailable, so Docker image and Compose semantic validation were
  skipped

The tests cover:

- LFAM travel-start/travel-end layer conventions;
- velocity phase classification;
- same-Z wipe detection;
- coordinate reordering and scientific notation;
- incomplete LIN reporting;
- UTF-8, UTF-8 BOM, Windows-1252, CRLF, LF, and mixed newline detection;
- parsing time-limit failure;
- metadata validation and repeat annotation;
- preservation of unmanaged content, encoding, and newline style;
- authentication, authorization, CSRF, HTTPS enforcement, health reporting,
  audit records, and attachment downloads.

## Reference-source inspection

Only aggregate results were emitted; reference source contents were not copied
into this repository.

| Reference | SHA-256 | Bytes | Lines | LIN | PTP | Extrusion layers | Z layers | Wipes | Warnings |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| Layer editor sample | `4d08e5ade2a7565a75ccc5908fff0d821a0ea5b831e95d567db689ca076188b4` | 2,524 | 77 | 48 | 0 | 0 | 0 | 0 | No PTP motion |
| General example | `c00c6b829bd41eef48e34552bc9cc56554e2c463fa7ea0fc100a26dd03a61e39` | 16,137 | 348 | 199 | 8 | 0 | 0 | 0 | Contains a non-positive `$VEL.CP` example |
| Large recreated output | `9ae8fe2faf8fb02e42498c43f626ec3446e05b0d79c31b698b89fe59cd863d79` | 20,345,352 | 157,873 | 151,176 | 1 | 205 | 203 | 203 | None |

The large reference parsed in approximately five seconds, below the configured
15-second processing limit.

## Reference transformation smoke check

An in-memory metadata annotation was performed against the reference input with
SHA-256
`1afcb06ab7bfbc783638c5bdbcde9d85659a16cea42ff0d1ff7e4ee7be150786`.
The source was not modified and the generated artifact was not written to the
reference tree.

Observed result:

- input size: 29,222 bytes;
- output size: 29,430 bytes;
- output filename: `CELL09-01201_BACK_51%.src`;
- output encoding/newline: UTF-8/LF;
- generated DEF name: `CELL09_01201_BACK_51P`;
- 199 LIN commands remained parseable;
- no parser warnings were produced after transformation;
- input and output hashes differed as expected.

## Remaining acceptance

- Build and validate the Docker image.
- Run `docker compose config` against the checked-in Compose project.
- Review the service-specific Caddy certificate enrollment approach.
- Add reviewed, sanitized golden fixtures representing accepted production
  conventions.
- Perform browser acceptance with approved operator identities.
- Deploy only through a separately authorized Fleetlord workflow.
- Keep robot-side review and acceptance separate from service deployment.
