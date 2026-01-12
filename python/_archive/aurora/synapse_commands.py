"""
Aurora Synapse Commands

Registers Aurora commands with Synapse for AI agent control.
Enables agents to manage light groups, AOVs, and linking through WebSocket.

Command Types:
- aurora_create_group: Create a light group
- aurora_add_light: Add light to group
- aurora_remove_light: Remove light from group
- aurora_delete_group: Delete light group
- aurora_auto_group: Auto-generate groups from scene lights
- aurora_get_groups: Get all light groups
- aurora_set_bundle: Set active AOV bundle
- aurora_get_aovs: Get all AOVs for current config
- aurora_add_link_rule: Add light linking rule
- aurora_get_pending: Get pending gate proposals
- aurora_approve: Approve gate proposal
- aurora_reject: Reject gate proposal
"""

from typing import Dict, Any, Optional, List
from enum import Enum

from .manager import aurora, AuroraManager
from .models import LightType, LightRole, AOVType
from .linking import LinkMode

from core.gates import human_gate, GateDecision, GateLevel
from core.audit import audit_log, AuditCategory, AuditLevel


class AuroraCommandType(Enum):
    """Aurora command types for Synapse protocol"""
    # Light Group Management
    CREATE_GROUP = "aurora_create_group"
    ADD_LIGHT = "aurora_add_light"
    REMOVE_LIGHT = "aurora_remove_light"
    DELETE_GROUP = "aurora_delete_group"
    AUTO_GROUP = "aurora_auto_group"
    GET_GROUPS = "aurora_get_groups"
    GET_GROUP = "aurora_get_group"

    # AOV Management
    SET_BUNDLE = "aurora_set_bundle"
    GET_BUNDLES = "aurora_get_bundles"
    GET_AOVS = "aurora_get_aovs"
    ADD_CUSTOM_AOV = "aurora_add_custom_aov"
    TOGGLE_AOV = "aurora_toggle_aov"

    # Light Linking
    ADD_LINK_RULE = "aurora_add_link_rule"
    REMOVE_LINK_RULE = "aurora_remove_link_rule"
    GET_LINK_RULES = "aurora_get_link_rules"
    SET_LINK_MODE = "aurora_set_link_mode"

    # Gate/Approval System
    GET_PENDING = "aurora_get_pending"
    APPROVE = "aurora_approve"
    REJECT = "aurora_reject"
    APPROVE_ALL = "aurora_approve_all"

    # Session
    SET_SEQUENCE = "aurora_set_sequence"
    GET_SESSION = "aurora_get_session"
    SAVE_SESSION = "aurora_save_session"
    LOAD_SESSION = "aurora_load_session"


class AuroraCommandHandler:
    """
    Handles Aurora commands from Synapse.

    Usage:
        # Register with Synapse handler
        aurora_handler = AuroraCommandHandler()
        aurora_handler.register_with_synapse(synapse_handler.registry)

        # Commands are then available via WebSocket
    """

    def __init__(self):
        self._mgr = aurora()

    def register_with_synapse(self, registry) -> None:
        """Register all Aurora commands with Synapse registry"""

        # Light Group Management
        registry.register(
            AuroraCommandType.CREATE_GROUP.value,
            self._handle_create_group,
            self._validate_create_group
        )
        registry.register(
            AuroraCommandType.ADD_LIGHT.value,
            self._handle_add_light,
            self._validate_add_light
        )
        registry.register(
            AuroraCommandType.REMOVE_LIGHT.value,
            self._handle_remove_light
        )
        registry.register(
            AuroraCommandType.DELETE_GROUP.value,
            self._handle_delete_group
        )
        registry.register(
            AuroraCommandType.AUTO_GROUP.value,
            self._handle_auto_group
        )
        registry.register(
            AuroraCommandType.GET_GROUPS.value,
            self._handle_get_groups
        )
        registry.register(
            AuroraCommandType.GET_GROUP.value,
            self._handle_get_group
        )

        # AOV Management
        registry.register(
            AuroraCommandType.SET_BUNDLE.value,
            self._handle_set_bundle
        )
        registry.register(
            AuroraCommandType.GET_BUNDLES.value,
            self._handle_get_bundles
        )
        registry.register(
            AuroraCommandType.GET_AOVS.value,
            self._handle_get_aovs
        )
        registry.register(
            AuroraCommandType.ADD_CUSTOM_AOV.value,
            self._handle_add_custom_aov
        )
        registry.register(
            AuroraCommandType.TOGGLE_AOV.value,
            self._handle_toggle_aov
        )

        # Light Linking
        registry.register(
            AuroraCommandType.ADD_LINK_RULE.value,
            self._handle_add_link_rule
        )
        registry.register(
            AuroraCommandType.REMOVE_LINK_RULE.value,
            self._handle_remove_link_rule
        )
        registry.register(
            AuroraCommandType.GET_LINK_RULES.value,
            self._handle_get_link_rules
        )
        registry.register(
            AuroraCommandType.SET_LINK_MODE.value,
            self._handle_set_link_mode
        )

        # Gate/Approval
        registry.register(
            AuroraCommandType.GET_PENDING.value,
            self._handle_get_pending
        )
        registry.register(
            AuroraCommandType.APPROVE.value,
            self._handle_approve
        )
        registry.register(
            AuroraCommandType.REJECT.value,
            self._handle_reject
        )
        registry.register(
            AuroraCommandType.APPROVE_ALL.value,
            self._handle_approve_all
        )

        # Session
        registry.register(
            AuroraCommandType.SET_SEQUENCE.value,
            self._handle_set_sequence
        )
        registry.register(
            AuroraCommandType.GET_SESSION.value,
            self._handle_get_session
        )
        registry.register(
            AuroraCommandType.SAVE_SESSION.value,
            self._handle_save_session
        )
        registry.register(
            AuroraCommandType.LOAD_SESSION.value,
            self._handle_load_session
        )

        audit_log().log(
            operation="aurora_synapse_register",
            message="Aurora commands registered with Synapse",
            level=AuditLevel.INFO,
            category=AuditCategory.SYSTEM,
            tool="aurora",
        )

    # Validators

    def _validate_create_group(self, payload: Dict) -> Optional[str]:
        if "name" not in payload:
            return "Missing required field: name"
        return None

    def _validate_add_light(self, payload: Dict) -> Optional[str]:
        if "group" not in payload:
            return "Missing required field: group"
        if "prim_path" not in payload:
            return "Missing required field: prim_path"
        return None

    # Light Group Handlers

    def _handle_create_group(self, payload: Dict) -> Dict:
        """Create a light group"""
        name = payload["name"]
        role_str = payload.get("role", "custom")
        lights_data = payload.get("lights", [])
        color_tag = payload.get("color_tag", "#FFFFFF")
        description = payload.get("description", "")
        gate_level_str = payload.get("gate_level", "review")
        reasoning = payload.get("reasoning", "")
        confidence = payload.get("confidence", 0.8)

        # Parse role
        try:
            role = LightRole(role_str)
        except ValueError:
            role = LightRole.CUSTOM

        # Parse gate level
        try:
            gate_level = GateLevel(gate_level_str)
        except ValueError:
            gate_level = GateLevel.REVIEW

        # Parse lights
        lights = []
        for light_data in lights_data:
            prim_path = light_data.get("prim_path", light_data.get("path", ""))
            light_type_str = light_data.get("light_type", light_data.get("type", "RectLight"))
            try:
                light_type = LightType(light_type_str)
            except ValueError:
                light_type = LightType.RECT
            lights.append((prim_path, light_type))

        group, proposal = self._mgr.create_light_group(
            name=name,
            role=role,
            lights=lights,
            color_tag=color_tag,
            description=description,
            gate_level=gate_level,
            agent_reasoning=reasoning,
            confidence=confidence,
        )

        return {
            "group": group.to_dict(),
            "proposal_id": proposal.proposal_id,
            "decision": proposal.decision.value,
        }

    def _handle_add_light(self, payload: Dict) -> Dict:
        """Add light to group"""
        group_name = payload["group"]
        prim_path = payload["prim_path"]
        light_type_str = payload.get("light_type", "RectLight")

        try:
            light_type = LightType(light_type_str)
        except ValueError:
            light_type = LightType.RECT

        proposal = self._mgr.add_light_to_group(group_name, prim_path, light_type)

        return {
            "added": True,
            "group": group_name,
            "prim_path": prim_path,
            "proposal_id": proposal.proposal_id if proposal else None,
        }

    def _handle_remove_light(self, payload: Dict) -> Dict:
        """Remove light from group"""
        group_name = payload["group"]
        prim_path = payload["prim_path"]

        result = self._mgr.remove_light_from_group(group_name, prim_path)

        return {
            "removed": result,
            "group": group_name,
            "prim_path": prim_path,
        }

    def _handle_delete_group(self, payload: Dict) -> Dict:
        """Delete light group"""
        name = payload["name"]
        result = self._mgr.delete_light_group(name)

        return {
            "deleted": result,
            "name": name,
        }

    def _handle_auto_group(self, payload: Dict) -> Dict:
        """Auto-generate groups from scene lights"""
        light_paths = payload.get("light_paths", [])
        light_type_map = payload.get("light_type_map", {})
        gate_level_str = payload.get("gate_level", "review")

        try:
            gate_level = GateLevel(gate_level_str)
        except ValueError:
            gate_level = GateLevel.REVIEW

        groups, proposal = self._mgr.auto_group_lights(
            light_paths, light_type_map, gate_level
        )

        return {
            "groups": [g.to_dict() for g in groups],
            "count": len(groups),
            "proposal_id": proposal.proposal_id,
        }

    def _handle_get_groups(self, payload: Dict) -> Dict:
        """Get all light groups"""
        groups = self._mgr.get_light_groups()

        return {
            "groups": [g.to_dict() for g in groups],
            "count": len(groups),
        }

    def _handle_get_group(self, payload: Dict) -> Dict:
        """Get specific light group"""
        name = payload["name"]
        group = self._mgr.get_light_group(name)

        if not group:
            raise ValueError(f"Light group not found: {name}")

        return {
            "group": group.to_dict(),
        }

    # AOV Handlers

    def _handle_set_bundle(self, payload: Dict) -> Dict:
        """Set active AOV bundle"""
        bundle_name = payload["bundle"]
        result = self._mgr.set_active_bundle(bundle_name)

        if not result:
            raise ValueError(f"Unknown bundle: {bundle_name}")

        return {
            "active_bundle": bundle_name,
        }

    def _handle_get_bundles(self, payload: Dict) -> Dict:
        """Get available AOV bundles"""
        bundles = self._mgr.get_available_bundles()

        return {
            "bundles": bundles,
            "active": self._mgr.session.active_bundle,
        }

    def _handle_get_aovs(self, payload: Dict) -> Dict:
        """Get all AOVs for current config"""
        aovs = self._mgr.get_all_aovs()

        return {
            "aovs": [a.to_dict() for a in aovs],
            "count": len(aovs),
            "active_bundle": self._mgr.session.active_bundle,
        }

    def _handle_add_custom_aov(self, payload: Dict) -> Dict:
        """Add custom AOV"""
        name = payload["name"]
        lpe = payload.get("lpe", "")
        source = payload.get("source", "")
        aov_type_str = payload.get("aov_type", "color3f")

        try:
            aov_type = AOVType(aov_type_str)
        except ValueError:
            aov_type = AOVType.COLOR3F

        aov = self._mgr.add_custom_aov(name, lpe, source, aov_type)

        return {
            "aov": aov.to_dict(),
        }

    def _handle_toggle_aov(self, payload: Dict) -> Dict:
        """Toggle AOV enabled state"""
        name = payload["name"]
        enabled = payload.get("enabled", True)

        self._mgr.toggle_aov(name, enabled)

        return {
            "name": name,
            "enabled": enabled,
        }

    # Light Linking Handlers

    def _handle_add_link_rule(self, payload: Dict) -> Dict:
        """Add light linking rule"""
        name = payload["name"]
        light_pattern = payload["light_pattern"]
        geometry_pattern = payload["geometry_pattern"]
        illumination = payload.get("illumination", True)
        shadow = payload.get("shadow", True)
        include = payload.get("include", True)
        priority = payload.get("priority", 0)
        description = payload.get("description", "")

        rule = self._mgr.linker.create_rule(
            name=name,
            light_pattern=light_pattern,
            geometry_pattern=geometry_pattern,
            illumination=illumination,
            shadow=shadow,
            include=include,
            priority=priority,
            description=description,
        )

        return {
            "rule": rule.to_dict(),
        }

    def _handle_remove_link_rule(self, payload: Dict) -> Dict:
        """Remove light linking rule"""
        rule_id = payload["rule_id"]
        result = self._mgr.linker.remove_rule(rule_id)

        return {
            "removed": result,
            "rule_id": rule_id,
        }

    def _handle_get_link_rules(self, payload: Dict) -> Dict:
        """Get all linking rules"""
        rules = self._mgr.linker.get_rules()

        return {
            "rules": [r.to_dict() for r in rules],
            "mode": self._mgr.linker.mode.value,
        }

    def _handle_set_link_mode(self, payload: Dict) -> Dict:
        """Set light linking mode"""
        mode_str = payload["mode"]

        try:
            mode = LinkMode(mode_str)
        except ValueError:
            raise ValueError(f"Unknown link mode: {mode_str}")

        self._mgr.set_link_mode(mode)

        return {
            "mode": mode.value,
        }

    # Gate/Approval Handlers

    def _handle_get_pending(self, payload: Dict) -> Dict:
        """Get pending gate proposals"""
        sequence_id = payload.get("sequence_id")
        proposals = human_gate().get_pending(sequence_id)

        return {
            "proposals": [p.to_dict() for p in proposals],
            "count": len(proposals),
        }

    def _handle_approve(self, payload: Dict) -> Dict:
        """Approve gate proposal"""
        proposal_id = payload["proposal_id"]
        user_id = payload.get("user_id", "synapse_user")
        notes = payload.get("notes", "")

        proposal = human_gate().decide(
            proposal_id, GateDecision.APPROVED, user_id, notes
        )

        if not proposal:
            raise ValueError(f"Proposal not found: {proposal_id}")

        return {
            "proposal_id": proposal_id,
            "decision": proposal.decision.value,
        }

    def _handle_reject(self, payload: Dict) -> Dict:
        """Reject gate proposal"""
        proposal_id = payload["proposal_id"]
        user_id = payload.get("user_id", "synapse_user")
        notes = payload.get("notes", "")

        proposal = human_gate().decide(
            proposal_id, GateDecision.REJECTED, user_id, notes
        )

        if not proposal:
            raise ValueError(f"Proposal not found: {proposal_id}")

        return {
            "proposal_id": proposal_id,
            "decision": proposal.decision.value,
        }

    def _handle_approve_all(self, payload: Dict) -> Dict:
        """Approve all pending proposals for sequence"""
        sequence_id = payload["sequence_id"]
        user_id = payload.get("user_id", "synapse_user")
        notes = payload.get("notes", "Batch approved")

        batch = human_gate().approve_all(sequence_id, user_id, notes)

        return {
            "sequence_id": sequence_id,
            "approved_count": len([p for p in batch.proposals if p.decision == GateDecision.APPROVED]),
            "summary": batch.summary(),
        }

    # Session Handlers

    def _handle_set_sequence(self, payload: Dict) -> Dict:
        """Set current sequence"""
        sequence_id = payload["sequence_id"]
        self._mgr.set_sequence(sequence_id)

        return {
            "sequence_id": sequence_id,
        }

    def _handle_get_session(self, payload: Dict) -> Dict:
        """Get current session state"""
        return {
            "session": self._mgr.session.to_dict(),
        }

    def _handle_save_session(self, payload: Dict) -> Dict:
        """Save session to file"""
        from pathlib import Path
        path = Path(payload["path"])
        self._mgr.save_session(path)

        return {
            "saved": str(path),
        }

    def _handle_load_session(self, payload: Dict) -> Dict:
        """Load session from file"""
        from pathlib import Path
        path = Path(payload["path"])
        result = self._mgr.load_session(path)

        return {
            "loaded": result,
            "path": str(path),
        }


# Singleton handler
_handler: Optional[AuroraCommandHandler] = None


def get_aurora_command_handler() -> AuroraCommandHandler:
    """Get singleton Aurora command handler"""
    global _handler
    if _handler is None:
        _handler = AuroraCommandHandler()
    return _handler


def register_aurora_commands(synapse_registry) -> None:
    """Register Aurora commands with Synapse"""
    handler = get_aurora_command_handler()
    handler.register_with_synapse(synapse_registry)
