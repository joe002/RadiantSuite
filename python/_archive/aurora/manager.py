"""
Aurora Manager

Central manager for light groups, AOVs, and linking.
Handles scene state, persistence, and agent integration.
"""

import json
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Callable, Tuple

from .models import (
    LightGroup, LightGroupMember, LightType, LightRole,
    AOVDefinition, AOVBundle, AOVType,
    LightLinkRule,
)
from .lpe import LPEGenerator, get_lpe_generator, STANDARD_AOVS
from .linking import LightLinker, get_light_linker, LinkMode

from core.determinism import deterministic_uuid, deterministic_sort
from core.audit import audit_log, AuditCategory, AuditLevel
from core.gates import (
    human_gate, propose_change, GateLevel, GateDecision, GateProposal
)


@dataclass
class AuroraSession:
    """
    Aurora session state.

    Tracks all light groups, AOVs, and settings for a scene/sequence.
    """
    session_id: str = ""
    sequence_id: str = ""  # Shot/sequence this session is for

    # Light Groups
    light_groups: Dict[str, LightGroup] = field(default_factory=dict)

    # AOV Configuration
    active_bundle: str = "comp_basic"
    custom_aovs: List[AOVDefinition] = field(default_factory=list)
    bundle_overrides: Dict[str, bool] = field(default_factory=dict)  # AOV name -> enabled

    # Scene state cache
    scene_lights: List[str] = field(default_factory=list)
    scene_geometry: List[str] = field(default_factory=list)

    # Metadata
    created_at: str = ""
    modified_at: str = ""

    def __post_init__(self):
        if not self.session_id:
            content = f"{self.sequence_id}:{len(self.light_groups)}"
            self.session_id = deterministic_uuid(content, "aurora_session")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "sequence_id": self.sequence_id,
            "light_groups": {k: v.to_dict() for k, v in self.light_groups.items()},
            "active_bundle": self.active_bundle,
            "custom_aovs": [a.to_dict() for a in self.custom_aovs],
            "bundle_overrides": self.bundle_overrides,
            "scene_lights": self.scene_lights,
            "scene_geometry": self.scene_geometry,
            "created_at": self.created_at,
            "modified_at": self.modified_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AuroraSession':
        session = cls(
            session_id=data.get("session_id", ""),
            sequence_id=data.get("sequence_id", ""),
            active_bundle=data.get("active_bundle", "comp_basic"),
            bundle_overrides=data.get("bundle_overrides", {}),
            scene_lights=data.get("scene_lights", []),
            scene_geometry=data.get("scene_geometry", []),
            created_at=data.get("created_at", ""),
            modified_at=data.get("modified_at", ""),
        )

        for name, group_data in data.get("light_groups", {}).items():
            session.light_groups[name] = LightGroup.from_dict(group_data)

        for aov_data in data.get("custom_aovs", []):
            session.custom_aovs.append(AOVDefinition.from_dict(aov_data))

        return session


class AuroraManager:
    """
    Central Aurora manager.

    Provides high-level API for:
    - Light group management
    - AOV bundle configuration
    - Light linking
    - Human gate integration
    - USD scene integration

    Usage:
        manager = AuroraManager.get_instance()
        manager.set_sequence("shot_010")

        # Create light group (proposes via gate)
        manager.create_light_group("key_lights", LightRole.KEY, lights=[...])

        # After human approval, get AOVs
        aovs = manager.get_all_aovs()
    """

    _instance: Optional['AuroraManager'] = None

    def __init__(self):
        self._session = AuroraSession()
        self._lpe_gen = get_lpe_generator()
        self._linker = get_light_linker()

        # Pre-built bundles
        self._bundles: Dict[str, AOVBundle] = {}
        self._init_default_bundles()

        # Agent ID for audit trail
        self._agent_id = "aurora"

        # Callbacks for UI updates
        self._on_change: List[Callable[[], None]] = []

    @classmethod
    def get_instance(cls) -> 'AuroraManager':
        """Get singleton instance"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset singleton (for testing)"""
        cls._instance = None

    def on_change(self, callback: Callable[[], None]) -> None:
        """Register change callback for UI updates"""
        self._on_change.append(callback)

    def _notify_change(self) -> None:
        """Notify listeners of state change"""
        for callback in self._on_change:
            try:
                callback()
            except Exception:
                pass

    def _init_default_bundles(self) -> None:
        """Initialize default AOV bundles"""
        self._bundles["comp_basic"] = self._lpe_gen.create_comp_basic_bundle()
        self._bundles["comp_full"] = self._lpe_gen.create_comp_full_bundle()
        self._bundles["lookdev"] = self._lpe_gen.create_lookdev_bundle()
        self._bundles["debug"] = self._lpe_gen.create_debug_bundle()

    # Session Management

    def set_sequence(self, sequence_id: str) -> None:
        """Set current sequence/shot"""
        self._session.sequence_id = sequence_id

        audit_log().log(
            operation="set_sequence",
            message=f"Aurora session set to sequence: {sequence_id}",
            level=AuditLevel.INFO,
            category=AuditCategory.LIGHTING,
            sequence_id=sequence_id,
            tool="aurora",
        )

    @property
    def sequence_id(self) -> str:
        return self._session.sequence_id

    @property
    def session(self) -> AuroraSession:
        return self._session

    # Light Group Management

    def create_light_group(
        self,
        name: str,
        role: LightRole = LightRole.CUSTOM,
        lights: Optional[List[Tuple[str, LightType]]] = None,
        color_tag: str = "#FFFFFF",
        description: str = "",
        gate_level: GateLevel = GateLevel.REVIEW,
        agent_reasoning: str = "",
        confidence: float = 0.8,
    ) -> Tuple[LightGroup, GateProposal]:
        """
        Create a light group (proposes via human gate).

        Args:
            name: Group name
            role: Semantic role (key, fill, rim, etc.)
            lights: List of (prim_path, light_type) tuples
            color_tag: UI color
            description: Human-readable description
            gate_level: Approval level required
            agent_reasoning: Why agent is proposing this
            confidence: Agent confidence (0-1)

        Returns:
            (LightGroup, GateProposal) - Group is created but pending approval
        """
        group = LightGroup(
            name=name,
            role=role,
            color_tag=color_tag,
            description=description,
            created_by=self._agent_id,
        )

        if lights:
            for prim_path, light_type in lights:
                group.add_light(prim_path, light_type)

        # Propose via gate
        proposal = propose_change(
            operation="create_light_group",
            description=f"Create '{name}' light group with {len(group.members)} lights",
            sequence_id=self._session.sequence_id,
            category=AuditCategory.LIGHTING,
            level=gate_level,
            proposed_changes=group.to_dict(),
            reasoning=agent_reasoning,
            confidence=confidence,
            agent_id=self._agent_id,
        )

        # Store pending (will be activated on approval)
        self._session.light_groups[name] = group

        self._notify_change()
        return group, proposal

    def add_light_to_group(
        self,
        group_name: str,
        prim_path: str,
        light_type: LightType,
        gate_level: GateLevel = GateLevel.INFORM,
    ) -> Optional[GateProposal]:
        """Add light to existing group"""
        group = self._session.light_groups.get(group_name)
        if not group:
            return None

        member = group.add_light(prim_path, light_type)

        proposal = propose_change(
            operation="add_light_to_group",
            description=f"Add {prim_path} to '{group_name}'",
            sequence_id=self._session.sequence_id,
            category=AuditCategory.LIGHTING,
            level=gate_level,
            proposed_changes={
                "group": group_name,
                "light": member.to_dict(),
            },
            agent_id=self._agent_id,
        )

        self._notify_change()
        return proposal

    def remove_light_from_group(
        self,
        group_name: str,
        prim_path: str,
    ) -> bool:
        """Remove light from group"""
        group = self._session.light_groups.get(group_name)
        if not group:
            return False

        result = group.remove_light(prim_path)

        if result:
            audit_log().log(
                operation="remove_light_from_group",
                message=f"Removed {prim_path} from '{group_name}'",
                level=AuditLevel.INFO,
                category=AuditCategory.LIGHTING,
                tool="aurora",
            )
            self._notify_change()

        return result

    def delete_light_group(self, name: str) -> bool:
        """Delete light group"""
        if name in self._session.light_groups:
            del self._session.light_groups[name]

            audit_log().log(
                operation="delete_light_group",
                message=f"Deleted light group: {name}",
                level=AuditLevel.INFO,
                category=AuditCategory.LIGHTING,
                tool="aurora",
            )

            self._notify_change()
            return True
        return False

    def get_light_groups(self) -> List[LightGroup]:
        """Get all light groups"""
        return list(self._session.light_groups.values())

    def get_light_group(self, name: str) -> Optional[LightGroup]:
        """Get specific light group"""
        return self._session.light_groups.get(name)

    # Auto-grouping

    def auto_group_lights(
        self,
        light_paths: List[str],
        light_type_map: Dict[str, str],
        gate_level: GateLevel = GateLevel.REVIEW,
    ) -> Tuple[List[LightGroup], GateProposal]:
        """
        Automatically create light groups from naming conventions.

        Returns (groups, proposal) for human review.
        """
        suggestions = self._lpe_gen.suggest_groups_from_lights(light_paths)
        groups = self._lpe_gen.create_groups_from_suggestions(
            suggestions, light_type_map
        )

        for group in groups:
            group.created_by = self._agent_id
            self._session.light_groups[group.name] = group

        proposal = propose_change(
            operation="auto_group_lights",
            description=f"Auto-created {len(groups)} light groups from {len(light_paths)} lights",
            sequence_id=self._session.sequence_id,
            category=AuditCategory.LIGHTING,
            level=gate_level,
            proposed_changes={
                "groups": [g.to_dict() for g in groups],
                "source_lights": light_paths,
            },
            reasoning="Analyzed light names to infer semantic roles (key, fill, rim, etc.)",
            confidence=0.7,
            agent_id=self._agent_id,
        )

        self._notify_change()
        return groups, proposal

    # AOV Management

    def set_active_bundle(self, bundle_name: str) -> bool:
        """Set active AOV bundle"""
        if bundle_name not in self._bundles:
            return False

        self._session.active_bundle = bundle_name

        audit_log().log(
            operation="set_aov_bundle",
            message=f"Set active AOV bundle: {bundle_name}",
            level=AuditLevel.INFO,
            category=AuditCategory.AOV,
            tool="aurora",
        )

        self._notify_change()
        return True

    def get_available_bundles(self) -> List[str]:
        """Get available bundle names"""
        return list(self._bundles.keys())

    def get_bundle(self, name: str) -> Optional[AOVBundle]:
        """Get bundle by name"""
        return self._bundles.get(name)

    def add_custom_aov(
        self,
        name: str,
        lpe: str = "",
        source: str = "",
        aov_type: AOVType = AOVType.COLOR3F,
    ) -> AOVDefinition:
        """Add custom AOV definition"""
        aov = AOVDefinition(
            name=name,
            lpe=lpe,
            source=source,
            aov_type=aov_type,
        )
        self._session.custom_aovs.append(aov)

        audit_log().log(
            operation="add_custom_aov",
            message=f"Added custom AOV: {name}",
            level=AuditLevel.INFO,
            category=AuditCategory.AOV,
            tool="aurora",
            input_data=aov.to_dict(),
        )

        self._notify_change()
        return aov

    def get_all_aovs(self) -> List[AOVDefinition]:
        """
        Get all AOVs for current configuration.

        Combines:
        - Active bundle AOVs
        - Per-light-group AOVs
        - Custom AOVs
        """
        aovs: List[AOVDefinition] = []

        # Bundle AOVs
        bundle = self._bundles.get(self._session.active_bundle)
        if bundle:
            for aov in bundle.aovs:
                # Check overrides
                if self._session.bundle_overrides.get(aov.name, True):
                    aovs.append(aov)

        # Light group AOVs
        for group in self._session.light_groups.values():
            if group.enabled:
                group_aovs = self._lpe_gen.generate_group_aovs(group)
                aovs.extend(group_aovs)

        # Custom AOVs
        aovs.extend(self._session.custom_aovs)

        return aovs

    def toggle_aov(self, aov_name: str, enabled: bool) -> None:
        """Toggle AOV enabled state"""
        self._session.bundle_overrides[aov_name] = enabled
        self._notify_change()

    # Light Linking

    @property
    def linker(self) -> LightLinker:
        """Access light linker"""
        return self._linker

    def set_link_mode(self, mode: LinkMode) -> None:
        """Set light linking mode"""
        self._linker.mode = mode

        audit_log().log(
            operation="set_link_mode",
            message=f"Set light linking mode: {mode.value}",
            level=AuditLevel.INFO,
            category=AuditCategory.LIGHTING,
            tool="aurora",
        )

    # Scene Integration

    def update_scene_cache(
        self,
        lights: List[str],
        geometry: List[str],
    ) -> None:
        """Update cached scene paths"""
        self._session.scene_lights = deterministic_sort(lights)
        self._session.scene_geometry = deterministic_sort(geometry)

    def get_unassigned_lights(self) -> List[str]:
        """Get lights not in any group"""
        assigned = set()
        for group in self._session.light_groups.values():
            for member in group.members:
                assigned.add(member.prim_path)

        return [p for p in self._session.scene_lights if p not in assigned]

    # Persistence

    def save_session(self, path: Path) -> None:
        """Save session to file"""
        data = {
            "version": "1.0",
            "session": self._session.to_dict(),
            "linker": self._linker.to_dict(),
        }

        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)

        audit_log().log(
            operation="save_aurora_session",
            message=f"Saved Aurora session to {path}",
            level=AuditLevel.INFO,
            category=AuditCategory.PIPELINE,
            tool="aurora",
        )

    def load_session(self, path: Path) -> bool:
        """Load session from file"""
        if not path.exists():
            return False

        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        self._session = AuroraSession.from_dict(data.get("session", {}))
        self._linker.from_dict(data.get("linker", {}))

        # Regenerate bundles with loaded groups
        self._regenerate_bundles()

        audit_log().log(
            operation="load_aurora_session",
            message=f"Loaded Aurora session from {path}",
            level=AuditLevel.INFO,
            category=AuditCategory.PIPELINE,
            tool="aurora",
        )

        self._notify_change()
        return True

    def _regenerate_bundles(self) -> None:
        """Regenerate bundles with current light groups"""
        groups = list(self._session.light_groups.values())
        self._bundles["comp_basic"] = self._lpe_gen.create_comp_basic_bundle(groups)
        self._bundles["comp_full"] = self._lpe_gen.create_comp_full_bundle(groups)

    def clear(self) -> None:
        """Clear session state"""
        self._session = AuroraSession()
        self._linker.clear()
        self._init_default_bundles()
        self._notify_change()


# Convenience function
def aurora() -> AuroraManager:
    """Get Aurora manager instance"""
    return AuroraManager.get_instance()
