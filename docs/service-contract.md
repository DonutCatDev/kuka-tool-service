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

## Authorization

- `viewer`, `operator`, and `admin` may inspect files.
- `operator` and `admin` may generate annotated artifacts.
- `operator` and `admin` may generate velocity-modified artifacts.
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
