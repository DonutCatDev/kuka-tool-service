# Validation evidence

This directory owns reviewed evidence for the KUKA Tool Service repository.

Commit concise reports, fixture manifests, and acceptance records when they are
needed to support a decision. Put transient test output under ignored
`validation/results/` or `validation/tmp/` directories.

Validation stages must be reported separately:

1. source and unit validation;
2. container and local HTTP validation;
3. Fleetlord deployment validation;
4. operator review of generated KUKA programs;
5. separately authorized robot-side acceptance.

Passing an earlier stage does not imply that a later stage has passed.
