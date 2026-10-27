# Fleetlord pilot deployment validation

Date: 2026-10-27

## Release

- Revision: `d84bde1b572859e3d030f82cd74c131300fd16dc`
- Public URL: `https://fleetlord.local:4743`
- Semaphore project: 1
- Reusable preflight template: 313

## Preflight

Semaphore task 556 checked out the exact release revision and completed with
`ok=11`, `changed=0`, `failed=0`. It confirmed:

- the Fleetlord-only host guard;
- the protected Production Desk users secret;
- Docker, Docker Compose, and the external `fleet-services` network;
- no existing KUKA Tool Service stack;
- ports 4700 and 4743 available;
- static address `172.30.0.23` available;
- no controller access or deployment action.

## Deployment

After explicit authorization, a one-use template fixed approval, revision,
inventory 4, environment 1, repository 3, and `ansible/deploy.yml`; task and
branch overrides were disabled. Semaphore task 557 completed successfully with
`ok=20`, `changed=5`, `failed=0`.

The task built and started the service, then passed its authenticated health,
direct-HTTP rejection, and HTTPS login checks. It reported the exact release
revision, `controller_access: false`, and `robot_acceptance_complete: false`.
The one-use deployment template 314 was deleted after success to prevent replay;
read-only preflight template 313 remains.

## Independent live checks

- `GET http://fleetlord.local:4700/healthz` returned 200, `status: ok`,
  `authentication_configured: true`, and `controller_access: false`.
- Direct HTTP login returned 426.
- HTTPS login returned 200 with an HTML response.
- The login form contained CSRF and password fields.
- CSP, `X-Content-Type-Options`, `X-Frame-Options`, and Referrer Policy headers
  were present with the configured values.

The HTTPS probe accepted Caddy's internal CA without independently validating
its certificate chain. Client trust and expected certificate identity remain an
operator acceptance item.

## Remaining acceptance

- Authenticate with approved test users and verify viewer/operator/admin roles.
- Exercise representative inspection and transformation/download workflows with
  non-production fixtures and confirm audit writes.
- Confirm backup/recovery coverage for service data.
- Complete operator review and separately controlled robot-side acceptance.

No controller credential, controller connection, program upload, or robot motion
was introduced or tested.
