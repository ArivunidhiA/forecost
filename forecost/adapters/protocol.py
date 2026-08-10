"""Versioned capability declarations and offline adapter conformance checks."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal

ADAPTER_PROTOCOL_VERSION = 1

Readiness = Literal["NOT OBSERVED", "OBSERVED", "CONTAINED"]


@dataclass(frozen=True)
class AdapterCapabilities:
    """Machine-readable promises made by one ingestion/control boundary.

    Capabilities are declarations, not marketing claims.  The conformance CLI
    validates internal consistency and reports the exact authority/control
    boundary so an adapter cannot silently imply stronger containment.
    """

    name: str
    protocol_version: int
    transport: Literal["pull", "push", "callback", "file"]
    event_identity: Literal["source", "derived", "caller"]
    lifecycle: bool
    finality: bool
    graph_identity: bool
    meter_dimensions: bool
    economic_authority: tuple[str, ...]
    watermarks: bool
    enforcement_point: Literal["none", "advisory", "pre-call"]
    privacy: Literal["content-free-by-selection"]
    readiness_ceiling: Readiness

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


ADAPTER_CAPABILITIES: tuple[AdapterCapabilities, ...] = (
    AdapterCapabilities(
        "claude_jsonl",
        1,
        "pull",
        "source",
        True,
        True,
        True,
        True,
        ("list_rate",),
        True,
        "advisory",
        "content-free-by-selection",
        "OBSERVED",
    ),
    AdapterCapabilities(
        "litellm",
        1,
        "callback",
        "source",
        False,
        True,
        False,
        True,
        ("gateway_estimate", "list_rate"),
        True,
        "pre-call",
        "content-free-by-selection",
        "CONTAINED",
    ),
    AdapterCapabilities(
        "otel_genai",
        1,
        "file",
        "source",
        True,
        True,
        True,
        True,
        ("provider_estimate", "unknown"),
        True,
        "none",
        "content-free-by-selection",
        "OBSERVED",
    ),
    AdapterCapabilities(
        "openai_agents",
        1,
        "push",
        "source",
        True,
        True,
        True,
        True,
        ("provider_estimate", "unknown"),
        True,
        "none",
        "content-free-by-selection",
        "OBSERVED",
    ),
    AdapterCapabilities(
        "langgraph",
        1,
        "push",
        "derived",
        True,
        True,
        True,
        True,
        ("unknown",),
        True,
        "none",
        "content-free-by-selection",
        "OBSERVED",
    ),
)


def check_capability(capability: AdapterCapabilities) -> list[str]:
    """Return deterministic protocol violations for one declaration."""
    errors: list[str] = []
    if capability.protocol_version != ADAPTER_PROTOCOL_VERSION:
        errors.append("unsupported protocol version")
    if not capability.name or any(character.isspace() for character in capability.name):
        errors.append("name must be a non-empty atom")
    if not capability.economic_authority:
        errors.append("economic authority must be explicit")
    if capability.readiness_ceiling == "CONTAINED" and capability.enforcement_point != "pre-call":
        errors.append("CONTAINED requires a tested pre-call boundary")
    if capability.enforcement_point == "pre-call" and capability.readiness_ceiling != "CONTAINED":
        errors.append("pre-call adapters must declare their containment ceiling")
    if capability.event_identity == "derived" and not capability.watermarks:
        errors.append("derived identity requires a replay watermark")
    return errors


def conformance_report() -> dict[str, Any]:
    adapters = []
    passed = True
    for capability in ADAPTER_CAPABILITIES:
        errors = check_capability(capability)
        passed = passed and not errors
        adapters.append({**capability.to_dict(), "conformant": not errors, "errors": errors})
    return {
        "protocol_version": ADAPTER_PROTOCOL_VERSION,
        "conformant": passed,
        "adapters": adapters,
        "claim_boundary": (
            "offline structural conformance; runtime/provider availability is not implied"
        ),
    }
