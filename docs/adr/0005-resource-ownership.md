# ADR 0005: Resource ownership is reservation based

## Decision

Experimental local resource control uses typed reservations, leases, stable
idempotency keys, and explicit settlement/release.  It makes no cross-host or
provider-side enforcement claim.

