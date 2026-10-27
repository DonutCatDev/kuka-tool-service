# Browser service contract

## Safety boundary

KUKA Tool Service reads operator-uploaded `.src` files and returns analysis or a
downloadable transformed artifact. It has no controller credentials, robot
network client, production share, or automatic propagation route.

Inspection is syntactic. A successful result does not establish that a program
is valid KRL for every controller version or physically safe to run.

## Supported parsing conventions

The first release recognizes the conventions used by the prior LFAM utilities:

- `DEF NAME()` program declarations, including legacy filename-derived names;
- `PTP { ... }` and `LIN { ... }` motion counts;
- numeric X, Y, and Z fields when calculating Cartesian bounds and runtime;
- `$VEL.CP = value` velocity assignments in metres per second;
- `;travel end` as entry into an extrusion region;
- `;travel start` as entry into return travel;
- the first same-Z `LIN` shortly after `;travel start` as a wipe candidate;
- extrusion layers bounded by travel markers and Z layers grouped at 0.1 mm.

Coordinate fields may appear in any order and numeric fields may use signs,
leading decimals, or scientific notation. Joint-space PTP motions may omit XYZ.
LIN commands lacking a complete XYZ triplet are reported and excluded from
Cartesian bounds and runtime while remaining visible in the raw LIN count.

## Runtime estimate

The estimate sums straight-line distance between consecutive complete `LIN`
motions and divides each segment by the active `$VEL.CP` value. It does not model
acceleration, approximation/blending, PTP duration, controller overhead, process
delays, extrusion state, or physical constraints. The browser labels it an
idealized estimate.

## Byte handling

Inputs are hashed before processing. The decoder recognizes UTF-8 with or
without a BOM, then Windows-1252, then Latin-1. Inspection never rewrites input.

Metadata annotation preserves the detected encoding, dominant newline style,
terminal-newline state, and all unmanaged lines. Managed metadata immediately
following `DEF` is replaced rather than duplicated. Downloads include input and
output SHA-256 values in response headers.

## Velocity modification

Velocity modification follows the historical LFAM marker convention while
using a stricter state machine than the desktop utility:

- `;travel end` opens an extrusion region;
- `;travel start` opens a return-travel region;
- the two marker types must begin with `;travel end` and alternate;
- `$VEL.CP` assignments before the first marker are setup commands and remain
  unchanged;
- assignments inside extrusion and travel regions are replaced independently;
- numeric values may use signs, leading decimals, or scientific notation;
- whitespace, comments, commands, coordinates, and unrelated lines remain
  unchanged.

Both target speeds must be greater than zero and no more than 2 m/s. Files with
missing, duplicate, reversed, or same-line ambiguous travel markers are rejected
rather than classified heuristically. The output is an offline review artifact;
the service does not determine whether a requested speed is physically safe.
The browser requires an explicit acknowledgement of independent operator review
before generating the download.

## Mesh rectangle editing

Mesh rectangle editing accepts one strictly parsed mesh CSV and selects cells by
inclusive X and Y coordinate bounds. At least one coordinate on each axis must
fall inside the requested bounds. The selected measured cells may be set to a
value, or have a value added, subtracted, or multiplied. Bounds and edit values
must be finite; reversed bounds, unsupported operations, and no-op edits are
rejected.

An edit fails as a whole if its rectangle contains an unmeasured cell or would
produce a height outside -10000 through 10000 mm. Output uses a deterministic
CSV representation, retains UTF-8 BOM and CRLF/LF style when present, preserves
untouched values numerically, and rounds edited results to six decimal places.
Output is reparsed by the validation suite. The browser returns the result only as an
attachment with input/output hashes and changed-cell count headers. It requires
operator authorization, CSRF protection, and explicit acknowledgement that the
mesh needs independent review.

## Mesh generation from SRC

Mesh generation extracts complete Cartesian `LIN` coordinates only from strict
marker-classified extrusion regions. Ambiguous, reversed, or incomplete travel
markers and incomplete extrusion motions reject the operation. The extrusion XY
bounds are expanded by a non-negative margin and snapped outward to independent
X and Y spacing intervals. A zero-width source axis is expanded by one interval
so the result remains a valid interpolatable mesh.

Every generated cell receives the requested baseline height. Spacing is limited
to 0.1 through 1000 mm, and the shared mesh parser's axis, cell-count, byte, and
numeric limits apply. The generated UTF-8/LF CSV is reparsed before download and
is compatible with mesh inspection, rectangular editing, and mesh-speed
compensation. Browser generation requires operator authorization, CSRF
protection, and explicit independent-review acknowledgement; input/output hashes
and grid dimensions are audited.

## XYZ adjustment

XYZ adjustment applies a uniform millimetre offset to complete Cartesian `LIN`
commands in marker-classified extrusion regions. It uses the same strict marker
state machine as velocity modification: extrusion begins at `;travel end`,
return travel begins at `;travel start`, and marker types must begin with travel
end and alternate.

The operator may target all extrusion layers or an inclusive layer range.
Layer indices are zero-based and are assigned only when a valid `;travel end`
marker begins an extrusion region. Both range endpoints are required; reversed,
negative, or out-of-range selections reject the entire operation. Range output
names include both selected indices so the narrower scope remains visible.

Coordinate fields may appear in any order and may use signs, leading decimals,
or scientific notation. Every targeted `LIN` must contain exactly one X, one Y,
and one Z value. Duplicate or incomplete fields reject the whole operation. The
three results are formatted to the historical utility's 0.001 mm precision;
orientation, approximation, external-axis, comments, and other fields remain
unchanged. Commented examples containing `LIN` text are not motion commands and
remain unchanged.

Setup motions, PTP commands, return-travel LIN commands, and wipe moves after a
travel-start marker are intentionally not adjusted. Consequently, an offset can
change the relationship between the extrusion path and those preserved motions;
the browser requires explicit acknowledgement that the result needs independent
operator review. Offsets are finite, bounded to -1000 through 1000 mm per axis,
and cannot all be zero.

## Alternating path merge

Path merge accepts a primary and secondary SRC program and interleaves complete
path blocks in primary/secondary order. A block begins with its entry velocity
and travel, contains one `;travel end` delimited extrusion region, and ends at
`;travel start`; an immediately following same-Z wipe is retained with that
block. Original block text and velocity assignments are preserved.

The generated program uses the primary file's header, `DEF` declaration, final
return path, shutdown sequence, encoding, newline style, and terminal-newline
state. Before merging, the service requires:

- different primary and secondary byte streams;
- the same encoding and non-mixed newline style;
- structurally equivalent headers and tails after normalizing program names,
  motion coordinates, and velocity values;
- strict travel-marker ordering and complete Cartesian extrusion LIN commands;
- equal path-block counts;
- paired block Z heights within 0.05 mm.

The merged output is parsed again and rejected if it exceeds normal source
limits, contains an incomplete Cartesian LIN, or does not retain the expected
combined extrusion-block count. Both input hashes and the output hash are
returned and audited. This check establishes structural compatibility only; it
does not validate transition safety, reachability, collision clearance, process
timing, or controller execution.

## Probe-grid generation

Probe generation derives XY bounds only from complete Cartesian `LIN` commands
inside strictly marker-classified extrusion regions. It rounds each half-extent
outward to the requested spacing, optionally adds a non-negative margin, and
orders the grid by row or column using one-way or zigzag traversal.

At each point the generated sequence moves to safe Z at travel speed, descends
to probe Z at probe speed, issues `HALT`, and returns to safe Z. Safe Z must be
greater than probe Z. Spacing is limited to 0.1–1000 mm, margin to 0–1000 mm,
speeds to greater than zero through 2 m/s, and a generated grid to 10,000 points.

The first extrusion LIN supplies only the non-XYZ motion fields, such as
orientation, external axes, and approximation mode. The generated artifact is a
new review-only program and intentionally does not copy source initialization,
tool/base selection, safety logic, process outputs, PTP entry, or shutdown
logic. Its header states these omissions. It must not be treated as a
controller-ready probing routine without independent engineering integration
and physical validation.

## Mesh CSV inspection

Mesh files use the historical matrix convention: the top-left field is empty,
the remaining first-row fields are Y coordinates, each later row begins with an
X coordinate, and the remaining cells are measured Z heights. The parser uses
the standard CSV grammar and requires rectangular rows, finite numeric values,
and strictly increasing unique X and Y axes.

Uploads are limited to 8 MiB, 2,000 values per axis, and 1,000,000 cells. Blank
height cells remain explicitly missing and are reported; a fully empty probing
template is rejected as not yet being a measurement mesh. Bilinear lookup uses
four measured corners and otherwise returns a caller-supplied baseline,
including outside the grid. It never silently rewrites missing cells.

The reusable speed calculation follows the historical zone convention while
requiring explicit bounded parameters. This release exposes mesh inspection in
the browser and supports the endpoint compensation mode below.

## Endpoint mesh-speed compensation

The first mesh-speed transformation inserts `$VEL.CP` assignments before
complete extrusion-region `LIN` commands when the bilinearly interpolated mesh
height at that command's target XY changes the active speed zone. It follows the
reference formula: round the height deviation into zones, scale the base speed
by the configured fraction per zone, apply a tolerance, and clamp the result to
0.001–0.1 m/s. Program speeds above 0.1 m/s are left unchanged.

This mode does not split a LIN move where it crosses a mesh-zone boundary. It
uses only the target endpoint, preserves every motion coordinate and travel
region, and reparses the output to verify its LIN count. Missing interpolation
corners and coordinates outside the mesh use the explicit baseline height and
are counted in the audit record. A request producing no speed changes is
rejected rather than returning an indistinguishable artifact.
The compensation pass has a 15-second processing deadline in addition to the
existing input and output parsing limits.

The source, mesh, and output SHA-256 hashes are returned and audited. The result
requires independent review because endpoint compensation is not equivalent to
the historical boundary-splitting mode and neither method establishes a
physically safe process.

## Authorization

- `viewer`, `operator`, and `admin` may inspect files.
- `viewer`, `operator`, and `admin` may inspect mesh CSV files.
- `operator` and `admin` may generate annotated artifacts.
- `operator` and `admin` may generate velocity-modified artifacts.
- `operator` and `admin` may generate XYZ-adjusted artifacts.
- `operator` and `admin` may generate merged artifacts.
- `operator` and `admin` may generate probe-grid artifacts.
- `operator` and `admin` may generate mesh-speed artifacts.
- all mutation requests require a session-bound CSRF token.
- the service uses the unique `kuka_tools_session` cookie name.
- generated programs are attachment-only downloads.

The service consumes the existing Production Desk users secret format but does
not contain or generate credential values.

The initial Compose definition exposes the application health endpoint on port
4700 and authenticated browser traffic through a Caddy internal-TLS endpoint on
port 4743. Its Caddy data directory is service-specific, so its public root
certificate must be reviewed and trusted on approved clients before pilot use.
Consolidating this route behind a shared Fleetlord TLS gateway remains a
deployment-phase option.
