from dataclasses import dataclass
from enum import Enum


class EvidenceLevel(str, Enum):
    RUNTIME_VERIFIED = "RUNTIME_VERIFIED"
    SOURCE_ONLY = "SOURCE_ONLY"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class IdentityField:
    value: str | None
    evidence_level: EvidenceLevel
    evidence_source: str | None


def build_identity_field(value, evidence_source, evidence_level):
    if evidence_level is EvidenceLevel.UNKNOWN or value is None or evidence_source is None:
        return IdentityField(None, EvidenceLevel.UNKNOWN, None)
    return IdentityField(str(value), evidence_level, str(evidence_source))


def authority_eligible(provider, identity_field):
    allowed = {"live", "production"}
    return (
        str(provider).casefold() in allowed
        and identity_field.evidence_level is EvidenceLevel.RUNTIME_VERIFIED
        and identity_field.value is not None
    )

