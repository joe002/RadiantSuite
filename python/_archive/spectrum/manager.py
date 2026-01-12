"""
Spectrum Manager

Central manager for material lookdev workflows.
Coordinates materials, textures, environments, and preview system.
"""

import json
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Callable, Tuple

from .models import (
    Material, MaterialType, TextureSet, TextureChannel,
    EnvironmentPreset, EnvironmentType, PreviewConfig, PreviewQuality,
    MaterialAssignmentRule, ShaderParameter,
)
from .materials import MaterialLibrary, get_material_library
from .textures import TextureManager, get_texture_manager
from .environments import EnvironmentManager, get_environment_manager

from core.determinism import deterministic_uuid
from core.audit import audit_log, AuditCategory, AuditLevel
from core.gates import propose_change, GateLevel, GateProposal


@dataclass
class SpectrumSession:
    """
    Spectrum session state.

    Tracks active material, environment, and preview settings.
    """
    session_id: str = ""

    # Active selections
    active_material: str = ""
    active_environment: str = "neutral_grey"
    active_preview_config: str = "default"

    # Comparison mode
    comparison_material_a: str = ""
    comparison_material_b: str = ""
    comparison_enabled: bool = False

    # Preview state
    last_preview_path: str = ""
    turntable_in_progress: bool = False

    # Scene cache
    scene_geometry: List[str] = field(default_factory=list)
    scene_materials: List[str] = field(default_factory=list)

    # Metadata
    created_at: str = ""
    modified_at: str = ""

    def __post_init__(self):
        if not self.session_id:
            self.session_id = deterministic_uuid("spectrum_session", "session")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "active_material": self.active_material,
            "active_environment": self.active_environment,
            "active_preview_config": self.active_preview_config,
            "comparison_material_a": self.comparison_material_a,
            "comparison_material_b": self.comparison_material_b,
            "comparison_enabled": self.comparison_enabled,
            "last_preview_path": self.last_preview_path,
            "turntable_in_progress": self.turntable_in_progress,
            "scene_geometry": self.scene_geometry,
            "scene_materials": self.scene_materials,
            "created_at": self.created_at,
            "modified_at": self.modified_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SpectrumSession':
        return cls(
            session_id=data.get("session_id", ""),
            active_material=data.get("active_material", ""),
            active_environment=data.get("active_environment", "neutral_grey"),
            active_preview_config=data.get("active_preview_config", "default"),
            comparison_material_a=data.get("comparison_material_a", ""),
            comparison_material_b=data.get("comparison_material_b", ""),
            comparison_enabled=data.get("comparison_enabled", False),
            last_preview_path=data.get("last_preview_path", ""),
            turntable_in_progress=data.get("turntable_in_progress", False),
            scene_geometry=data.get("scene_geometry", []),
            scene_materials=data.get("scene_materials", []),
            created_at=data.get("created_at", ""),
            modified_at=data.get("modified_at", ""),
        )


# Default preview configurations
DEFAULT_PREVIEW_CONFIGS = {
    "default": PreviewConfig(
        name="default",
        quality=PreviewQuality.MEDIUM,
        resolution=(1920, 1080),
        camera_preset="3/4",
        samples=64,
        use_denoiser=True,
    ),
    "quick": PreviewConfig(
        name="quick",
        quality=PreviewQuality.DRAFT,
        resolution=(960, 540),
        camera_preset="front",
        samples=16,
        use_denoiser=False,
    ),
    "high_quality": PreviewConfig(
        name="high_quality",
        quality=PreviewQuality.HIGH,
        resolution=(1920, 1080),
        camera_preset="3/4",
        samples=256,
        use_denoiser=True,
    ),
    "turntable": PreviewConfig(
        name="turntable",
        quality=PreviewQuality.MEDIUM,
        resolution=(1920, 1080),
        camera_preset="3/4",
        enable_turntable=True,
        turntable_frames=90,
        samples=64,
        use_denoiser=True,
    ),
    "thumbnail": PreviewConfig(
        name="thumbnail",
        quality=PreviewQuality.DRAFT,
        resolution=(512, 512),
        camera_preset="front",
        samples=32,
        use_denoiser=True,
    ),
}


class SpectrumManager:
    """
    Central Spectrum manager.

    Provides high-level API for:
    - Material workflow management
    - Texture handling
    - Environment control
    - Preview rendering
    - A/B comparison
    """

    _instance: Optional['SpectrumManager'] = None

    def __init__(self):
        self._session = SpectrumSession()

        # Sub-managers
        self._materials = get_material_library()
        self._textures = get_texture_manager()
        self._environments = get_environment_manager()

        # Preview configs
        self._preview_configs: Dict[str, PreviewConfig] = dict(DEFAULT_PREVIEW_CONFIGS)

        # Agent ID
        self._agent_id = "spectrum"

        # Callbacks
        self._on_change: List[Callable[[], None]] = []

    @classmethod
    def get_instance(cls) -> 'SpectrumManager':
        """Get singleton instance"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset singleton (for testing)"""
        cls._instance = None

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

    # Property accessors

    @property
    def session(self) -> SpectrumSession:
        return self._session

    @property
    def materials(self) -> MaterialLibrary:
        return self._materials

    @property
    def textures(self) -> TextureManager:
        return self._textures

    @property
    def environments(self) -> EnvironmentManager:
        return self._environments

    # Material Operations

    def create_material(
        self,
        name: str,
        material_type: MaterialType = MaterialType.KARMA_PRINCIPLED,
        texture_directory: Optional[Path] = None,
        gate_level: GateLevel = GateLevel.REVIEW,
        reasoning: str = "",
        confidence: float = 0.8,
    ) -> Tuple[Material, GateProposal]:
        """
        Create material with optional texture auto-detection.

        If texture_directory provided, scans for textures and auto-connects.
        """
        texture_set = None

        if texture_directory and texture_directory.exists():
            texture_set = self._textures.scan_and_add(name, texture_directory)

        material, proposal = self._materials.create_material(
            name=name,
            material_type=material_type,
            texture_set=texture_set,
            gate_level=gate_level,
            agent_reasoning=reasoning,
            confidence=confidence,
        )

        # Set as active
        self._session.active_material = name
        self._notify_change()

        return material, proposal

    def set_active_material(self, name: str) -> bool:
        """Set active material for editing"""
        if self._materials.get_material(name):
            self._session.active_material = name
            self._notify_change()
            return True
        return False

    def get_active_material(self) -> Optional[Material]:
        """Get active material"""
        if self._session.active_material:
            return self._materials.get_material(self._session.active_material)
        return None

    def update_material_parameter(
        self,
        param_name: str,
        value: Any,
        material_name: Optional[str] = None,
    ) -> bool:
        """Update parameter on active or specified material"""
        name = material_name or self._session.active_material
        if not name:
            return False

        proposal = self._materials.update_material(name, {param_name: value})
        self._notify_change()
        return proposal is not None

    # Environment Operations

    def set_active_environment(self, name: str) -> bool:
        """Set active environment"""
        result = self._environments.set_active(name)
        if result:
            self._session.active_environment = name
            self._notify_change()
        return result

    def get_active_environment(self) -> Optional[EnvironmentPreset]:
        """Get active environment"""
        return self._environments.get_active()

    def rotate_hdri(self, degrees: float) -> bool:
        """Rotate active HDRI environment"""
        preset_name = self._session.active_environment
        result = self._environments.adjust_hdri_rotation(preset_name, degrees)
        if result:
            self._notify_change()
        return result

    def adjust_environment_intensity(self, intensity: float) -> bool:
        """Adjust active environment intensity"""
        preset_name = self._session.active_environment
        result = self._environments.adjust_hdri_intensity(preset_name, intensity)
        if result:
            self._notify_change()
        return result

    # Comparison Mode

    def enable_comparison(
        self,
        material_a: str,
        material_b: str,
    ) -> bool:
        """Enable A/B material comparison"""
        if not self._materials.get_material(material_a):
            return False
        if not self._materials.get_material(material_b):
            return False

        self._session.comparison_material_a = material_a
        self._session.comparison_material_b = material_b
        self._session.comparison_enabled = True

        audit_log().log(
            operation="enable_comparison",
            message=f"Enabled comparison: {material_a} vs {material_b}",
            level=AuditLevel.INFO,
            category=AuditCategory.MATERIAL,
            tool="spectrum",
        )

        self._notify_change()
        return True

    def disable_comparison(self) -> None:
        """Disable comparison mode"""
        self._session.comparison_enabled = False
        self._notify_change()

    def swap_comparison(self) -> None:
        """Swap A and B materials in comparison"""
        if self._session.comparison_enabled:
            self._session.comparison_material_a, self._session.comparison_material_b = (
                self._session.comparison_material_b, self._session.comparison_material_a
            )
            self._notify_change()

    # Preview Configuration

    def get_preview_config(self, name: str = "default") -> Optional[PreviewConfig]:
        """Get preview configuration"""
        return self._preview_configs.get(name)

    def set_active_preview_config(self, name: str) -> bool:
        """Set active preview configuration"""
        if name in self._preview_configs:
            self._session.active_preview_config = name
            self._notify_change()
            return True
        return False

    def add_preview_config(self, config: PreviewConfig) -> None:
        """Add custom preview configuration"""
        self._preview_configs[config.name] = config

    def get_preview_settings(self) -> Dict[str, Any]:
        """
        Get current preview settings for render.

        Combines active config, material, and environment.
        """
        config = self._preview_configs.get(
            self._session.active_preview_config, DEFAULT_PREVIEW_CONFIGS["default"]
        )

        env = self._environments.get_active()
        material = self.get_active_material()

        return {
            "config": config.to_dict() if config else None,
            "environment": env.to_dict() if env else None,
            "material": material.to_dict() if material else None,
            "comparison": {
                "enabled": self._session.comparison_enabled,
                "material_a": self._session.comparison_material_a,
                "material_b": self._session.comparison_material_b,
            } if self._session.comparison_enabled else None,
        }

    # Scene Integration

    def update_scene_cache(
        self,
        geometry: List[str],
        materials: List[str],
    ) -> None:
        """Update cached scene information"""
        from core.determinism import deterministic_sort
        self._session.scene_geometry = deterministic_sort(geometry)
        self._session.scene_materials = deterministic_sort(materials)

    def get_unassigned_geometry(self) -> List[str]:
        """Get geometry without material assignments"""
        assigned = set()

        for rule in self._materials.get_assignment_rules():
            for geo in self._session.scene_geometry:
                import fnmatch
                if fnmatch.fnmatch(geo, rule.geometry_pattern):
                    assigned.add(geo)

        return [g for g in self._session.scene_geometry if g not in assigned]

    # Persistence

    def save_session(self, path: Path) -> None:
        """Save session to file"""
        data = {
            "version": "1.0",
            "session": self._session.to_dict(),
            "preview_configs": {k: v.to_dict() for k, v in self._preview_configs.items()},
        }

        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)

        # Also save materials library
        materials_path = path.parent / f"{path.stem}_materials.json"
        self._materials.save(materials_path)

        audit_log().log(
            operation="save_spectrum_session",
            message=f"Saved Spectrum session to {path}",
            level=AuditLevel.INFO,
            category=AuditCategory.PIPELINE,
            tool="spectrum",
        )

    def load_session(self, path: Path) -> bool:
        """Load session from file"""
        if not path.exists():
            return False

        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        self._session = SpectrumSession.from_dict(data.get("session", {}))

        for name, config_data in data.get("preview_configs", {}).items():
            self._preview_configs[name] = PreviewConfig.from_dict(config_data)

        # Load materials library
        materials_path = path.parent / f"{path.stem}_materials.json"
        if materials_path.exists():
            self._materials.load(materials_path)

        audit_log().log(
            operation="load_spectrum_session",
            message=f"Loaded Spectrum session from {path}",
            level=AuditLevel.INFO,
            category=AuditCategory.PIPELINE,
            tool="spectrum",
        )

        self._notify_change()
        return True

    def clear(self) -> None:
        """Clear session state"""
        self._session = SpectrumSession()
        self._materials.clear()
        self._notify_change()


# Convenience function
def spectrum() -> SpectrumManager:
    """Get Spectrum manager instance"""
    return SpectrumManager.get_instance()
