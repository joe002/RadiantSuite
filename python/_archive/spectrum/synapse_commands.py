"""
Spectrum Synapse Commands

Registers Spectrum commands with Synapse for AI agent control.
Enables agents to manage materials, textures, environments through WebSocket.

Command Types:
- spectrum_create_material: Create a material
- spectrum_update_material: Update material parameters
- spectrum_delete_material: Delete material
- spectrum_get_materials: List all materials
- spectrum_set_active_material: Set active material
- spectrum_add_texture_set: Add texture set from directory
- spectrum_get_environments: List environment presets
- spectrum_set_environment: Set active environment
- spectrum_rotate_hdri: Rotate HDRI environment
- spectrum_enable_comparison: Enable A/B comparison
- spectrum_get_preview_settings: Get current preview settings
"""

from typing import Dict, Any, Optional, List
from enum import Enum
from pathlib import Path

from .manager import spectrum, SpectrumManager
from .models import MaterialType, TextureChannel, EnvironmentType, PreviewQuality
from .materials import get_material_library
from .textures import get_texture_manager
from .environments import get_environment_manager

from core.gates import GateLevel, GateDecision
from core.audit import audit_log, AuditCategory, AuditLevel


class SpectrumCommandType(Enum):
    """Spectrum command types for Synapse protocol"""
    # Material Management
    CREATE_MATERIAL = "spectrum_create_material"
    UPDATE_MATERIAL = "spectrum_update_material"
    DELETE_MATERIAL = "spectrum_delete_material"
    GET_MATERIALS = "spectrum_get_materials"
    GET_MATERIAL = "spectrum_get_material"
    SET_ACTIVE_MATERIAL = "spectrum_set_active_material"
    DUPLICATE_MATERIAL = "spectrum_duplicate_material"
    APPLY_PRESET = "spectrum_apply_preset"

    # Texture Management
    ADD_TEXTURE_SET = "spectrum_add_texture_set"
    GET_TEXTURE_SETS = "spectrum_get_texture_sets"
    SCAN_TEXTURES = "spectrum_scan_textures"

    # Environment Management
    GET_ENVIRONMENTS = "spectrum_get_environments"
    SET_ENVIRONMENT = "spectrum_set_environment"
    ROTATE_HDRI = "spectrum_rotate_hdri"
    ADJUST_INTENSITY = "spectrum_adjust_intensity"
    ADD_HDRI = "spectrum_add_hdri"

    # Comparison
    ENABLE_COMPARISON = "spectrum_enable_comparison"
    DISABLE_COMPARISON = "spectrum_disable_comparison"
    SWAP_COMPARISON = "spectrum_swap_comparison"

    # Preview
    GET_PREVIEW_SETTINGS = "spectrum_get_preview_settings"
    SET_PREVIEW_CONFIG = "spectrum_set_preview_config"

    # Session
    GET_SESSION = "spectrum_get_session"
    SAVE_SESSION = "spectrum_save_session"
    LOAD_SESSION = "spectrum_load_session"


class SpectrumCommandHandler:
    """
    Handles Spectrum commands from Synapse.

    Usage:
        handler = SpectrumCommandHandler()
        handler.register_with_synapse(synapse_handler.registry)
    """

    def __init__(self):
        self._mgr = spectrum()

    def register_with_synapse(self, registry) -> None:
        """Register all Spectrum commands with Synapse registry"""

        # Material Management
        registry.register(
            SpectrumCommandType.CREATE_MATERIAL.value,
            self._handle_create_material,
            self._validate_create_material
        )
        registry.register(
            SpectrumCommandType.UPDATE_MATERIAL.value,
            self._handle_update_material
        )
        registry.register(
            SpectrumCommandType.DELETE_MATERIAL.value,
            self._handle_delete_material
        )
        registry.register(
            SpectrumCommandType.GET_MATERIALS.value,
            self._handle_get_materials
        )
        registry.register(
            SpectrumCommandType.GET_MATERIAL.value,
            self._handle_get_material
        )
        registry.register(
            SpectrumCommandType.SET_ACTIVE_MATERIAL.value,
            self._handle_set_active_material
        )
        registry.register(
            SpectrumCommandType.DUPLICATE_MATERIAL.value,
            self._handle_duplicate_material
        )
        registry.register(
            SpectrumCommandType.APPLY_PRESET.value,
            self._handle_apply_preset
        )

        # Texture Management
        registry.register(
            SpectrumCommandType.ADD_TEXTURE_SET.value,
            self._handle_add_texture_set
        )
        registry.register(
            SpectrumCommandType.GET_TEXTURE_SETS.value,
            self._handle_get_texture_sets
        )
        registry.register(
            SpectrumCommandType.SCAN_TEXTURES.value,
            self._handle_scan_textures
        )

        # Environment Management
        registry.register(
            SpectrumCommandType.GET_ENVIRONMENTS.value,
            self._handle_get_environments
        )
        registry.register(
            SpectrumCommandType.SET_ENVIRONMENT.value,
            self._handle_set_environment
        )
        registry.register(
            SpectrumCommandType.ROTATE_HDRI.value,
            self._handle_rotate_hdri
        )
        registry.register(
            SpectrumCommandType.ADJUST_INTENSITY.value,
            self._handle_adjust_intensity
        )
        registry.register(
            SpectrumCommandType.ADD_HDRI.value,
            self._handle_add_hdri
        )

        # Comparison
        registry.register(
            SpectrumCommandType.ENABLE_COMPARISON.value,
            self._handle_enable_comparison
        )
        registry.register(
            SpectrumCommandType.DISABLE_COMPARISON.value,
            self._handle_disable_comparison
        )
        registry.register(
            SpectrumCommandType.SWAP_COMPARISON.value,
            self._handle_swap_comparison
        )

        # Preview
        registry.register(
            SpectrumCommandType.GET_PREVIEW_SETTINGS.value,
            self._handle_get_preview_settings
        )
        registry.register(
            SpectrumCommandType.SET_PREVIEW_CONFIG.value,
            self._handle_set_preview_config
        )

        # Session
        registry.register(
            SpectrumCommandType.GET_SESSION.value,
            self._handle_get_session
        )
        registry.register(
            SpectrumCommandType.SAVE_SESSION.value,
            self._handle_save_session
        )
        registry.register(
            SpectrumCommandType.LOAD_SESSION.value,
            self._handle_load_session
        )

        audit_log().log(
            operation="spectrum_synapse_register",
            message="Spectrum commands registered with Synapse",
            level=AuditLevel.INFO,
            category=AuditCategory.SYSTEM,
            tool="spectrum",
        )

    # Validators

    def _validate_create_material(self, payload: Dict) -> Optional[str]:
        if "name" not in payload:
            return "Missing required field: name"
        return None

    # Material Handlers

    def _handle_create_material(self, payload: Dict) -> Dict:
        """Create a material"""
        name = payload["name"]
        material_type_str = payload.get("material_type", "KarmaPrincipled")
        texture_dir = payload.get("texture_directory")
        gate_level_str = payload.get("gate_level", "review")
        reasoning = payload.get("reasoning", "")
        confidence = payload.get("confidence", 0.8)

        try:
            material_type = MaterialType(material_type_str)
        except ValueError:
            material_type = MaterialType.KARMA_PRINCIPLED

        try:
            gate_level = GateLevel(gate_level_str)
        except ValueError:
            gate_level = GateLevel.REVIEW

        texture_path = Path(texture_dir) if texture_dir else None

        material, proposal = self._mgr.create_material(
            name=name,
            material_type=material_type,
            texture_directory=texture_path,
            gate_level=gate_level,
            reasoning=reasoning,
            confidence=confidence,
        )

        return {
            "material": material.to_dict(),
            "proposal_id": proposal.proposal_id,
            "decision": proposal.decision.value,
        }

    def _handle_update_material(self, payload: Dict) -> Dict:
        """Update material parameters"""
        name = payload.get("name") or self._mgr.session.active_material
        parameters = payload.get("parameters", {})

        if not name:
            raise ValueError("No material specified and no active material")

        for param_name, value in parameters.items():
            self._mgr.update_material_parameter(param_name, value, name)

        return {
            "updated": name,
            "parameters": list(parameters.keys()),
        }

    def _handle_delete_material(self, payload: Dict) -> Dict:
        """Delete material"""
        name = payload["name"]
        result = self._mgr.materials.delete_material(name)

        return {
            "deleted": result,
            "name": name,
        }

    def _handle_get_materials(self, payload: Dict) -> Dict:
        """Get all materials"""
        materials = self._mgr.materials.get_all_materials()

        return {
            "materials": [m.to_dict() for m in materials],
            "count": len(materials),
            "active": self._mgr.session.active_material,
        }

    def _handle_get_material(self, payload: Dict) -> Dict:
        """Get specific material"""
        name = payload["name"]
        material = self._mgr.materials.get_material(name)

        if not material:
            raise ValueError(f"Material not found: {name}")

        return {
            "material": material.to_dict(),
        }

    def _handle_set_active_material(self, payload: Dict) -> Dict:
        """Set active material"""
        name = payload["name"]
        result = self._mgr.set_active_material(name)

        return {
            "success": result,
            "active": name if result else None,
        }

    def _handle_duplicate_material(self, payload: Dict) -> Dict:
        """Duplicate material"""
        source = payload["source"]
        new_name = payload["new_name"]

        material = self._mgr.materials.duplicate_material(source, new_name)

        if not material:
            raise ValueError(f"Source material not found: {source}")

        return {
            "material": material.to_dict(),
        }

    def _handle_apply_preset(self, payload: Dict) -> Dict:
        """Apply preset to material"""
        material_name = payload["material"]
        preset_name = payload["preset"]
        gate_level_str = payload.get("gate_level", "review")

        try:
            gate_level = GateLevel(gate_level_str)
        except ValueError:
            gate_level = GateLevel.REVIEW

        applied, proposal = self._mgr.materials.apply_preset(
            material_name, preset_name, gate_level
        )

        return {
            "applied": applied,
            "proposal_id": proposal.proposal_id if proposal else None,
        }

    # Texture Handlers

    def _handle_add_texture_set(self, payload: Dict) -> Dict:
        """Add texture set from directory"""
        name = payload["name"]
        directory = Path(payload["directory"])

        texture_set = self._mgr.textures.scan_and_add(name, directory)

        if not texture_set:
            raise ValueError(f"No textures found in: {directory}")

        return {
            "texture_set": texture_set.to_dict(),
            "channels": [t.channel.value for t in texture_set.textures],
        }

    def _handle_get_texture_sets(self, payload: Dict) -> Dict:
        """Get all texture sets"""
        sets = self._mgr.textures.get_all_texture_sets()

        return {
            "texture_sets": [s.to_dict() for s in sets],
            "count": len(sets),
        }

    def _handle_scan_textures(self, payload: Dict) -> Dict:
        """Scan directory for textures"""
        from .textures import scan_texture_directory

        directory = Path(payload["directory"])
        textures = scan_texture_directory(directory)

        return {
            "textures": [t.to_dict() for t in textures],
            "count": len(textures),
        }

    # Environment Handlers

    def _handle_get_environments(self, payload: Dict) -> Dict:
        """Get all environment presets"""
        presets = self._mgr.environments.get_all_presets()

        return {
            "environments": [p.to_dict() for p in presets],
            "count": len(presets),
            "active": self._mgr.session.active_environment,
        }

    def _handle_set_environment(self, payload: Dict) -> Dict:
        """Set active environment"""
        name = payload["name"]
        result = self._mgr.set_active_environment(name)

        return {
            "success": result,
            "active": name if result else None,
        }

    def _handle_rotate_hdri(self, payload: Dict) -> Dict:
        """Rotate HDRI environment"""
        degrees = payload["degrees"]
        result = self._mgr.rotate_hdri(degrees)

        return {
            "success": result,
            "rotation": degrees,
        }

    def _handle_adjust_intensity(self, payload: Dict) -> Dict:
        """Adjust environment intensity"""
        intensity = payload["intensity"]
        result = self._mgr.adjust_environment_intensity(intensity)

        return {
            "success": result,
            "intensity": intensity,
        }

    def _handle_add_hdri(self, payload: Dict) -> Dict:
        """Add HDRI to library"""
        name = payload["name"]
        path = payload["path"]

        self._mgr.environments.add_hdri(name, path)

        return {
            "added": name,
            "path": path,
        }

    # Comparison Handlers

    def _handle_enable_comparison(self, payload: Dict) -> Dict:
        """Enable A/B comparison"""
        material_a = payload["material_a"]
        material_b = payload["material_b"]

        result = self._mgr.enable_comparison(material_a, material_b)

        return {
            "success": result,
            "material_a": material_a,
            "material_b": material_b,
        }

    def _handle_disable_comparison(self, payload: Dict) -> Dict:
        """Disable comparison"""
        self._mgr.disable_comparison()

        return {
            "disabled": True,
        }

    def _handle_swap_comparison(self, payload: Dict) -> Dict:
        """Swap comparison materials"""
        self._mgr.swap_comparison()

        return {
            "swapped": True,
            "material_a": self._mgr.session.comparison_material_a,
            "material_b": self._mgr.session.comparison_material_b,
        }

    # Preview Handlers

    def _handle_get_preview_settings(self, payload: Dict) -> Dict:
        """Get current preview settings"""
        return self._mgr.get_preview_settings()

    def _handle_set_preview_config(self, payload: Dict) -> Dict:
        """Set preview configuration"""
        name = payload["name"]
        result = self._mgr.set_active_preview_config(name)

        return {
            "success": result,
            "active": name if result else None,
        }

    # Session Handlers

    def _handle_get_session(self, payload: Dict) -> Dict:
        """Get session state"""
        return {
            "session": self._mgr.session.to_dict(),
        }

    def _handle_save_session(self, payload: Dict) -> Dict:
        """Save session"""
        path = Path(payload["path"])
        self._mgr.save_session(path)

        return {
            "saved": str(path),
        }

    def _handle_load_session(self, payload: Dict) -> Dict:
        """Load session"""
        path = Path(payload["path"])
        result = self._mgr.load_session(path)

        return {
            "loaded": result,
            "path": str(path),
        }


# Singleton handler
_handler: Optional[SpectrumCommandHandler] = None


def get_spectrum_command_handler() -> SpectrumCommandHandler:
    """Get singleton Spectrum command handler"""
    global _handler
    if _handler is None:
        _handler = SpectrumCommandHandler()
    return _handler


def register_spectrum_commands(synapse_registry) -> None:
    """Register Spectrum commands with Synapse"""
    handler = get_spectrum_command_handler()
    handler.register_with_synapse(synapse_registry)
