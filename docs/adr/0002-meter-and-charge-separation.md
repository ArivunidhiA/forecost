# ADR 0002: Meter facts and charges are separate

## Decision

Immutable meter facts record quantities and aggregation semantics.  Immutable
charges record a valuation, currency, authority, tariff components, and any
supersession.  A charge references facts; it never changes them.

## Consequences

Several sources can value one event without double-counting it, and a pricing
correction is evidence rather than a destructive update.

