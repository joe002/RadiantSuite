"""
Spectrum Material Management

Material library, assignment rules, and preset management for USD/Solaris.
Integrates with human gates for material changes.
"""

import json
import fnmatch
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Tuple, Callable

from .models import (
    Material, MaterialType, MaterialPreset, MaterialAssignmentRule,
    TextureSet, TextureFile, TextureChannel, ShaderParameter,
)

from core.determinism import deterministic_uuid, deterministic_sort
from core.audit import audit_log, AuditCategory, AuditLevel
from core.gates import propose_change, GateLevel, GateProposal


# Standard shader parameter templates for common material types
KARMA_PRINCIPLED_DEFAULTS = [
    ShaderParameter("baseColor", (0.8, 0.8, 0.8), "color3f", ui_label="Base Color", ui_group="Surface"),
    ShaderParameter("roughness", 0.5, "float", 0.0, 1.0, ui_label="Roughness", ui_group="Surface"),
    ShaderParameter("metallic", 0.0, "float", 0.0, 1.0, ui_label="Metallic", ui_group="Surface"),
    ShaderParameter("specular", 0.5, "float", 0.0, 1.0, ui_label="Specular", ui_group="Surface"),
    ShaderParameter("specularTint", 0.0, "float", 0.0, 1.0, ui_label="Specular Tint", ui_group="Surface"),
    ShaderParameter("ior", 1.5, "float", 1.0, 3.0, ui_label="IOR", ui_group="Surface"),
    ShaderParameter("anisotropic", 0.0, "float", 0.0, 1.0, ui_label="Anisotropic", ui_group="Surface"),
    ShaderParameter("anisotropicRotation", 0.0, "float", 0.0, 1.0, ui_label="Anisotropic Rotation", ui_group="Surface"),
    ShaderParameter("sheen", 0.0, "float", 0.0, 1.0, ui_label="Sheen", ui_group="Sheen"),
    ShaderParameter("sheenTint", 0.5, "float", 0.0, 1.0, ui_label="Sheen Tint", ui_group="Sheen"),
    ShaderParameter("clearcoat", 0.0, "float", 0.0, 1.0, ui_label="Clearcoat", ui_group="Coat"),
    ShaderParameter("clearcoatRoughness", 0.03, "float", 0.0, 1.0, ui_label="Clearcoat Roughness", ui_group="Coat"),
    ShaderParameter("opacity", 1.0, "float", 0.0, 1.0, ui_label="Opacity", ui_group="Opacity"),
    ShaderParameter("transmission", 0.0, "float", 0.0, 1.0, ui_label="Transmission", ui_group="Transmission"),
    ShaderParameter("subsurface", 0.0, "float", 0.0, 1.0, ui_label="Subsurface", ui_group="Subsurface"),
    ShaderParameter("subsurfaceColor", (1.0, 1.0, 1.0), "color3f", ui_label="SSS Color", ui_group="Subsurface"),
    ShaderParameter("subsurfaceRadius", (1.0, 0.2, 0.1), "float3", ui_label="SSS Radius", ui_group="Subsurface"),
    ShaderParameter("emissiveColor", (0.0, 0.0, 0.0), "color3f", ui_label="Emissive Color", ui_group="Emission"),
]


USD_PREVIEW_SURFACE_DEFAULTS = [
    ShaderParameter("diffuseColor", (0.8, 0.8, 0.8), "color3f", ui_label="Diffuse Color"),
    ShaderParameter("roughness", 0.5, "float", 0.0, 1.0, ui_label="Roughness"),
    ShaderParameter("metallic", 0.0, "float", 0.0, 1.0, ui_label="Metallic"),
    ShaderParameter("specularColor", (1.0, 1.0, 1.0), "color3f", ui_label="Specular Color"),
    ShaderParameter("ior", 1.5, "float", 1.0, 3.0, ui_label="IOR"),
    ShaderParameter("opacity", 1.0, "float", 0.0, 1.0, ui_label="Opacity"),
    ShaderParameter("clearcoat", 0.0, "float", 0.0, 1.0, ui_label="Clearcoat"),
    ShaderParameter("clearcoatRoughness", 0.01, "float", 0.0, 1.0, ui_label="Clearcoat Roughness"),
    ShaderParameter("emissiveColor", (0.0, 0.0, 0.0), "color3f", ui_label="Emissive Color"),
]


def get_default_parameters(material_type: MaterialType) -> List[ShaderParameter]:
    """Get default parameters for material type"""
    if material_type == MaterialType.KARMA_PRINCIPLED:
        return [ShaderParameter(**{k: v for k, v in p.__dict__.items()}) for p in KARMA_PRINCIPLED_DEFAULTS]
    elif material_type == MaterialType.USD_PREVIEW_SURFACE:
        return [ShaderParameter(**{k: v for k, v in p.__dict__.items()}) for p in USD_PREVIEW_SURFACE_DEFAULTS]
    else:
        # Return minimal set for other types
        return [
            ShaderParameter("baseColor", (0.8, 0.8, 0.8), "color3f"),
            ShaderParameter("roughness", 0.5, "float", 0.0, 1.0),
            ShaderParameter("metallic", 0.0, "float", 0.0, 1.0),
        ]


class MaterialLibrary:
    """
    Material library with search, filtering, and preset management.

    Provides:
    - Material storage and retrieval
    - Tag-based organization
    - Preset management
    - Assignment rule handling
    """

    def __init__(self):
        self._materials: Dict[str, Material] = {}
        self._presets: Dict[str, MaterialPreset] = {}
        self._assignment_rules: Dict[str, MaterialAssignmentRule] = {}

        # Callbacks for UI updates
        self._on_change: List[Callable[[], None]] = []

        # Agent ID for audit
        self._agent_id = "spectrum"

    def on_change(self, callback: Callable[[], None]) -> None:
        """Register change callback"""
        self._on_change.append(callback)

    def _notify_change(self) -> None:
        """Notify listeners of state change"""
        for callback in self._on_change:
            try:
                callback()
            except Exception:
                pass

    # Material Management

    def create_material(
        self,
        name: str,
        material_type: MaterialType = MaterialType.KARMA_PRINCIPLED,
        texture_set: Optional[TextureSet] = None,
        prim_path: str = "",
        gate_level: GateLevel = GateLevel.REVIEW,
        agent_reasoning: str = "",
        confidence: float = 0.8,
    ) -> Tuple[Material, GateProposal]:
        """
        Create a new material with default parameters.

        Returns (Material, GateProposal) for human gate workflow.
        """
        # Get default parameters for this material type
        parameters = get_default_parameters(material_type)

        material = Material(
            name=name,
            material_type=material_type,
            parameters=parameters,
            texture_set=texture_set,
            prim_path=prim_path or f"/materials/{name}",
            created_by=self._agent_id,
        )

        # Connect texture channels to parameters if texture set provided
        if texture_set:
            self._auto_connect_textures(material, texture_set)

        # Store material
        self._materials[name] = material

        # Propose via gate
        proposal = propose_change(
            operation="create_material",
            description=f"Create '{name}' material ({material_type.value})",
            sequence_id="",  # Materials are sequence-independent
            category=AuditCategory.MATERIAL,
            level=gate_level,
            proposed_changes=material.to_dict(),
            reasoning=agent_reasoning,
            confidence=confidence,
            agent_id=self._agent_id,
        )

        self._notify_change()
        return material, proposal

    def _auto_connect_textures(self, material: Material, texture_set: TextureSet) -> None:
        """Auto-connect texture channels to shader parameters"""
        channel_to_param = {
            TextureChannel.ALBEDO: "baseColor",
            TextureChannel.DIFFUSE: "diffuseColor",
            TextureChannel.BASE_COLOR: "baseColor",
            TextureChannel.ROUGHNESS: "roughness",
            TextureChannel.METALLIC: "metallic",
            TextureChannel.NORMAL: "normal",
            TextureChannel.EMISSIVE: "emissiveColor",
            TextureChannel.OPACITY: "opacity",
        }

        for texture in texture_set.textures:
            param_name = channel_to_param.get(texture.channel)
            if param_name:
                param = material.get_parameter(param_name)
                if param:
                    param.is_connected = True
                    param.connected_to = texture.path

    def get_material(self, name: str) -> Optional[Material]:
        """Get material by name"""
        return self._materials.get(name)

    def get_all_materials(self) -> List[Material]:
        """Get all materials sorted by name"""
        return [self._materials[k] for k in deterministic_sort(list(self._materials.keys()))]

    def update_material(
        self,
        name: str,
        updates: Dict[str, Any],
        gate_level: GateLevel = GateLevel.INFORM,
    ) -> Optional[GateProposal]:
        """Update material parameters"""
        material = self._materials.get(name)
        if not material:
            return None

        # Apply updates
        for param_name, value in updates.items():
            material.set_parameter(param_name, value)

        proposal = propose_change(
            operation="update_material",
            description=f"Update material '{name}': {list(updates.keys())}",
            sequence_id="",
            category=AuditCategory.MATERIAL,
            level=gate_level,
            proposed_changes={"material": name, "updates": updates},
            agent_id=self._agent_id,
        )

        self._notify_change()
        return proposal

    def delete_material(self, name: str) -> bool:
        """Delete material"""
        if name in self._materials:
            del self._materials[name]

            audit_log().log(
                operation="delete_material",
                message=f"Deleted material: {name}",
                level=AuditLevel.INFO,
                category=AuditCategory.MATERIAL,
                tool="spectrum",
            )

            self._notify_change()
            return True
        return False

    def duplicate_material(
        self,
        source_name: str,
        new_name: str,
    ) -> Optional[Material]:
        """Duplicate a material with new name"""
        source = self._materials.get(source_name)
        if not source:
            return None

        # Deep copy via serialization
        material_data = source.to_dict()
        material_data["name"] = new_name
        material_data["material_id"] = ""  # Generate new ID
        material_data["prim_path"] = f"/materials/{new_name}"

        new_material = Material.from_dict(material_data)
        self._materials[new_name] = new_material

        audit_log().log(
            operation="duplicate_material",
            message=f"Duplicated '{source_name}' as '{new_name}'",
            level=AuditLevel.INFO,
            category=AuditCategory.MATERIAL,
            tool="spectrum",
        )

        self._notify_change()
        return new_material

    def search_materials(
        self,
        query: str = "",
        tags: Optional[List[str]] = None,
        material_type: Optional[MaterialType] = None,
    ) -> List[Material]:
        """Search materials by name, tags, or type"""
        results = []

        for material in self._materials.values():
            # Name filter
            if query and query.lower() not in material.name.lower():
                continue

            # Tag filter
            if tags and not any(t in material.tags for t in tags):
                continue

            # Type filter
            if material_type and material.material_type != material_type:
                continue

            results.append(material)

        return deterministic_sort(results, key=lambda m: m.name)

    # Preset Management

    def add_preset(self, preset: MaterialPreset) -> None:
        """Add material preset"""
        self._presets[preset.name] = preset

        audit_log().log(
            operation="add_preset",
            message=f"Added material preset: {preset.name}",
            level=AuditLevel.INFO,
            category=AuditCategory.MATERIAL,
            tool="spectrum",
        )

    def get_preset(self, name: str) -> Optional[MaterialPreset]:
        """Get preset by name"""
        return self._presets.get(name)

    def get_presets_by_category(self, category: str) -> List[MaterialPreset]:
        """Get presets by category"""
        return [p for p in self._presets.values() if p.category == category]

    def apply_preset(
        self,
        material_name: str,
        preset_name: str,
        gate_level: GateLevel = GateLevel.REVIEW,
    ) -> Tuple[List[str], Optional[GateProposal]]:
        """
        Apply preset to material.

        Returns (applied_params, proposal).
        """
        material = self._materials.get(material_name)
        preset = self._presets.get(preset_name)

        if not material or not preset:
            return [], None

        applied = preset.apply_to_material(material)

        proposal = propose_change(
            operation="apply_preset",
            description=f"Apply preset '{preset_name}' to '{material_name}'",
            sequence_id="",
            category=AuditCategory.MATERIAL,
            level=gate_level,
            proposed_changes={
                "material": material_name,
                "preset": preset_name,
                "applied_params": applied,
            },
            agent_id=self._agent_id,
        )

        self._notify_change()
        return applied, proposal

    def create_preset_from_material(
        self,
        material_name: str,
        preset_name: str,
        category: str = "general",
    ) -> Optional[MaterialPreset]:
        """Create preset from existing material"""
        material = self._materials.get(material_name)
        if not material:
            return None

        preset = MaterialPreset(
            name=preset_name,
            material_type=material.material_type,
            parameters=list(material.parameters),
            category=category,
            description=f"Created from {material_name}",
        )

        self._presets[preset_name] = preset

        audit_log().log(
            operation="create_preset_from_material",
            message=f"Created preset '{preset_name}' from '{material_name}'",
            level=AuditLevel.INFO,
            category=AuditCategory.MATERIAL,
            tool="spectrum",
        )

        return preset

    # Assignment Rules

    def add_assignment_rule(self, rule: MaterialAssignmentRule) -> None:
        """Add material assignment rule"""
        self._assignment_rules[rule.name] = rule

        audit_log().log(
            operation="add_assignment_rule",
            message=f"Added assignment rule: {rule.name}",
            level=AuditLevel.INFO,
            category=AuditCategory.MATERIAL,
            tool="spectrum",
            input_data=rule.to_dict(),
        )

    def get_assignment_rules(self) -> List[MaterialAssignmentRule]:
        """Get all assignment rules sorted by priority"""
        rules = list(self._assignment_rules.values())
        return sorted(rules, key=lambda r: (-r.priority, r.name))

    def remove_assignment_rule(self, name: str) -> bool:
        """Remove assignment rule"""
        if name in self._assignment_rules:
            del self._assignment_rules[name]
            return True
        return False

    def resolve_material_for_geometry(
        self,
        geometry_path: str,
    ) -> Optional[str]:
        """
        Find material for geometry based on assignment rules.

        Returns material name if matched, None otherwise.
        """
        rules = self.get_assignment_rules()

        for rule in rules:
            if fnmatch.fnmatch(geometry_path, rule.geometry_pattern):
                return rule.material_name

        return None

    def resolve_assignments(
        self,
        geometry_paths: List[str],
    ) -> Dict[str, str]:
        """
        Resolve material assignments for multiple geometry paths.

        Returns dict of geometry_path -> material_name.
        """
        assignments = {}

        for path in geometry_paths:
            material = self.resolve_material_for_geometry(path)
            if material:
                assignments[path] = material

        return assignments

    # Persistence

    def save(self, path: Path) -> None:
        """Save library to file"""
        data = {
            "version": "1.0",
            "materials": {k: v.to_dict() for k, v in self._materials.items()},
            "presets": {k: v.to_dict() for k, v in self._presets.items()},
            "assignment_rules": {k: v.to_dict() for k, v in self._assignment_rules.items()},
        }

        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)

        audit_log().log(
            operation="save_material_library",
            message=f"Saved material library to {path}",
            level=AuditLevel.INFO,
            category=AuditCategory.PIPELINE,
            tool="spectrum",
        )

    def load(self, path: Path) -> bool:
        """Load library from file"""
        if not path.exists():
            return False

        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        self._materials = {
            k: Material.from_dict(v)
            for k, v in data.get("materials", {}).items()
        }

        self._presets = {
            k: MaterialPreset.from_dict(v)
            for k, v in data.get("presets", {}).items()
        }

        self._assignment_rules = {
            k: MaterialAssignmentRule.from_dict(v)
            for k, v in data.get("assignment_rules", {}).items()
        }

        audit_log().log(
            operation="load_material_library",
            message=f"Loaded material library from {path}",
            level=AuditLevel.INFO,
            category=AuditCategory.PIPELINE,
            tool="spectrum",
        )

        self._notify_change()
        return True

    def clear(self) -> None:
        """Clear all materials, presets, and rules"""
        self._materials.clear()
        self._presets.clear()
        self._assignment_rules.clear()
        self._notify_change()


# Module-level instance
_library: Optional[MaterialLibrary] = None


def get_material_library() -> MaterialLibrary:
    """Get singleton material library"""
    global _library
    if _library is None:
        _library = MaterialLibrary()
    return _library
