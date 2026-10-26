# KUKA Tool Service repository instructions

## Scope

This repository owns the headless processing library, web application,
container definition, tests, documentation, and deployment automation for the
KUKA/LFAM SRC tool service hosted on Fleetlord.

When this repository is nested under `fleet_control/`, the parent workspace and
Fleet Control repository instructions also apply. Explicit task instructions
take precedence.

## Safety boundary

- Treat uploaded KUKA `.src` programs as untrusted, production-sensitive input.
- Generated files are offline review artifacts. Do not upload to a controller,
  activate a robot program, or add controller credentials without a separately
  reviewed and explicitly authorized scope.
- Preserve the original input bytes and SHA-256 digest. Record the selected
  operation, parameters, output digest, validation result, and operator identity.
- Fail closed when parsing is incomplete, markers are ambiguous, validation
  fails, or configured resource limits are exceeded.
- Never describe a syntactically valid transformation as physically safe. Robot
  review and physical acceptance are separate stages.
- Keep secrets in Fleetlord's root-owned secret tree. Never commit secret values,
  uploaded production programs, generated programs, or runtime databases.

## Repository organization

- `src/` owns importable application and processing code.
- `tests/` owns unit, contract, and golden-file regression tests.
- `progression/` owns current plans, decisions, status, and remaining work.
- `validation/` owns reviewed validation evidence; transient output belongs in
  ignored `validation/results/` or `validation/tmp/` directories.
- `docs/` owns durable operator and administrator documentation once the service
  is implemented.

## Change workflow

1. Inspect the reference implementation and representative fixtures before
   changing parser or transformation behavior.
2. Keep parsing, validation, transformation, storage, and web concerns separate.
3. Preserve encoding, newline style, unchanged source text, and deterministic
   output wherever the operation permits.
4. Add or update golden fixtures for every behavior-changing transformation.
5. Run focused tests and the repository-wide check command before committing.
6. Treat source changes, local validation, Fleetlord deployment, and robot-side
   acceptance as distinct stages.
7. Do not deploy merely because local validation succeeds.

## Web-service requirements

- Require authentication for all source-file access and transformations.
- Use a unique, explicit session cookie name; never use a framework default.
- Enforce CSRF protection on mutations and strict upload, parameter, line-count,
  runtime, and artifact-retention limits.
- Use server-generated identifiers and sanitized download names. Never use a
  client path as a storage path.
- Serve generated programs as attachments, not executable or inline content.
- Do not add network writes, robot access, or automatic file propagation as an
  incidental extension of this service.
