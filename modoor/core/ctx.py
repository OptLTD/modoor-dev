from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Ctx:
    """Request context injected by the capability layer."""

    tenant: int
    user_id: int
    team_id: int
    # HTTP MCP: when True, mutate tools are rejected (default for agent_key).
    agent_readonly: bool = False
    # Bulk sync / import: skip writing base.oplog audit rows.
    skip_oplog: bool = False

    def audit_dict(self) -> dict[str, int]:
        return {
            "tenant": self.tenant,
            "user_id": self.user_id,
            "team_id": self.team_id,
        }
