from dataclasses import dataclass
from enum import Enum


class LeaseState(str, Enum):
    NORMAL = "NORMAL"
    MAINTENANCE_ACTIVE = "MAINTENANCE_ACTIVE"
    MAINTENANCE_EXPIRED = "MAINTENANCE_EXPIRED"
    INVALID = "INVALID"


@dataclass(frozen=True)
class Lease:
    lease_id: str
    target_service: str
    created_at: float
    expires_at: float
    request_source: str


def evaluate_lease(lease, now, expected_service="sim-service"):
    if (
        not lease.lease_id
        or lease.target_service != expected_service
        or lease.expires_at <= lease.created_at
        or not lease.request_source
    ):
        return LeaseState.INVALID
    if now >= lease.expires_at:
        return LeaseState.MAINTENANCE_EXPIRED
    return LeaseState.MAINTENANCE_ACTIVE

