"""
Spectrum Environment System

HDRI and lighting presets for lookdev workflows.
Includes built-in studio lighting configurations and HDRI management.
"""

from pathlib import Path
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field

from .models import EnvironmentPreset, EnvironmentType

from core.determinism import deterministic_uuid, deterministic_sort, round_float, round_vector
from core.audit import audit_log, AuditCategory, AuditLevel


# Built-in studio lighting presets
STUDIO_PRESETS = {
    "neutral_grey": EnvironmentPreset(
        name="Neutral Grey",
        env_type=EnvironmentType.SOLID_COLOR,
        background_color=(0.18, 0.18, 0.18),
        background_visible=True,
        use_ground_plane=True,
        ground_color=(0.18, 0.18, 0.18),
        ground_roughness=0.5,
        description="Neutral grey background for material review",
        tags=["studio", "neutral", "grey"],
    ),

    "pure_black": EnvironmentPreset(
        name="Pure Black",
        env_type=EnvironmentType.SOLID_COLOR,
        background_color=(0.0, 0.0, 0.0),
        background_visible=True,
        use_ground_plane=False,
        description="Black void for isolated material review",
        tags=["studio", "black", "isolated"],
    ),

    "pure_white": EnvironmentPreset(
        name="Pure White",
        env_type=EnvironmentType.SOLID_COLOR,
        background_color=(1.0, 1.0, 1.0),
        background_visible=True,
        use_ground_plane=True,
        ground_color=(0.95, 0.95, 0.95),
        ground_roughness=0.3,
        description="White cyclorama for product shots",
        tags=["studio", "white", "product"],
    ),

    "gradient_studio": EnvironmentPreset(
        name="Gradient Studio",
        env_type=EnvironmentType.GRADIENT,
        background_color=(0.3, 0.3, 0.35),
        background_visible=True,
        use_ground_plane=True,
        ground_color=(0.15, 0.15, 0.18),
        ground_roughness=0.6,
        description="Subtle gradient background",
        tags=["studio", "gradient"],
    ),

    "outdoor_daylight": EnvironmentPreset(
        name="Outdoor Daylight",
        env_type=EnvironmentType.PROCEDURAL_SKY,
        sun_direction=(0.3, 1.0, 0.5),
        sun_intensity=1.0,
        sky_tint=(0.8, 0.9, 1.0),
        background_visible=True,
        use_ground_plane=True,
        ground_color=(0.2, 0.2, 0.18),
        ground_roughness=0.8,
        description="Bright outdoor daylight",
        tags=["outdoor", "daylight", "sun"],
    ),

    "outdoor_overcast": EnvironmentPreset(
        name="Outdoor Overcast",
        env_type=EnvironmentType.PROCEDURAL_SKY,
        sun_direction=(0.0, 1.0, 0.0),
        sun_intensity=0.3,
        sky_tint=(0.7, 0.75, 0.8),
        background_visible=True,
        use_ground_plane=True,
        ground_color=(0.15, 0.15, 0.15),
        ground_roughness=0.7,
        description="Soft overcast lighting",
        tags=["outdoor", "overcast", "soft"],
    ),

    "golden_hour": EnvironmentPreset(
        name="Golden Hour",
        env_type=EnvironmentType.PROCEDURAL_SKY,
        sun_direction=(0.8, 0.3, 0.5),
        sun_intensity=0.8,
        sky_tint=(1.0, 0.85, 0.7),
        background_visible=True,
        use_ground_plane=True,
        ground_color=(0.25, 0.2, 0.15),
        ground_roughness=0.6,
        description="Warm golden hour lighting",
        tags=["outdoor", "golden", "warm"],
    ),

    "blue_hour": EnvironmentPreset(
        name="Blue Hour",
        env_type=EnvironmentType.PROCEDURAL_SKY,
        sun_direction=(-0.5, -0.2, 0.8),
        sun_intensity=0.2,
        sky_tint=(0.6, 0.7, 0.9),
        background_visible=True,
        use_ground_plane=True,
        ground_color=(0.1, 0.12, 0.15),
        ground_roughness=0.5,
        description="Cool blue hour lighting",
        tags=["outdoor", "blue", "cool"],
    ),
}


class EnvironmentManager:
    """
    Environment preset manager.

    Provides:
    - Built-in studio presets
    - HDRI library management
    - Custom preset creation
    - Quick switching between environments
    """

    def __init__(self):
        self._presets: Dict[str, EnvironmentPreset] = {}
        self._hdri_library: Dict[str, str] = {}  # name -> path
        self._active_preset: Optional[str] = None

        # Load built-in presets
        self._load_builtin_presets()

    def _load_builtin_presets(self) -> None:
        """Load built-in studio presets"""
        for name, preset in STUDIO_PRESETS.items():
            self._presets[name] = preset

    # Preset Management

    def add_preset(self, preset: EnvironmentPreset) -> None:
        """Add environment preset"""
        self._presets[preset.name] = preset

        audit_log().log(
            operation="add_env_preset",
            message=f"Added environment preset: {preset.name}",
            level=AuditLevel.INFO,
            category=AuditCategory.ENVIRONMENT,
            tool="spectrum",
        )

    def get_preset(self, name: str) -> Optional[EnvironmentPreset]:
        """Get preset by name"""
        return self._presets.get(name)

    def get_all_presets(self) -> List[EnvironmentPreset]:
        """Get all presets sorted by name"""
        return [self._presets[k] for k in deterministic_sort(list(self._presets.keys()))]

    def get_presets_by_type(self, env_type: EnvironmentType) -> List[EnvironmentPreset]:
        """Get presets by environment type"""
        return [p for p in self._presets.values() if p.env_type == env_type]

    def get_presets_by_tag(self, tag: str) -> List[EnvironmentPreset]:
        """Get presets by tag"""
        return [p for p in self._presets.values() if tag in p.tags]

    def remove_preset(self, name: str) -> bool:
        """Remove preset (cannot remove built-in)"""
        if name in STUDIO_PRESETS:
            return False  # Can't remove built-in

        if name in self._presets:
            del self._presets[name]
            return True

        return False

    def duplicate_preset(self, source_name: str, new_name: str) -> Optional[EnvironmentPreset]:
        """Duplicate preset with new name"""
        source = self._presets.get(source_name)
        if not source:
            return None

        # Deep copy via serialization
        preset_data = source.to_dict()
        preset_data["name"] = new_name
        preset_data["preset_id"] = ""  # Generate new ID

        new_preset = EnvironmentPreset.from_dict(preset_data)
        self._presets[new_name] = new_preset

        return new_preset

    # Active Preset

    def set_active(self, name: str) -> bool:
        """Set active environment preset"""
        if name not in self._presets:
            return False

        self._active_preset = name

        audit_log().log(
            operation="set_active_env",
            message=f"Set active environment: {name}",
            level=AuditLevel.INFO,
            category=AuditCategory.ENVIRONMENT,
            tool="spectrum",
        )

        return True

    def get_active(self) -> Optional[EnvironmentPreset]:
        """Get active environment preset"""
        if self._active_preset:
            return self._presets.get(self._active_preset)
        return None

    @property
    def active_name(self) -> Optional[str]:
        return self._active_preset

    # HDRI Library

    def add_hdri(self, name: str, path: str) -> None:
        """Add HDRI to library"""
        self._hdri_library[name] = path

        # Create preset for this HDRI
        preset = EnvironmentPreset(
            name=f"HDRI: {name}",
            env_type=EnvironmentType.HDRI,
            hdri_path=path,
            rotation=0.0,
            intensity=1.0,
            exposure=0.0,
            background_visible=True,
            description=f"HDRI environment: {name}",
            tags=["hdri", name.lower()],
        )

        self._presets[f"hdri_{name}"] = preset

        audit_log().log(
            operation="add_hdri",
            message=f"Added HDRI to library: {name}",
            level=AuditLevel.INFO,
            category=AuditCategory.ENVIRONMENT,
            tool="spectrum",
            input_data={"name": name, "path": path},
        )

    def get_hdri_path(self, name: str) -> Optional[str]:
        """Get HDRI path by name"""
        return self._hdri_library.get(name)

    def get_all_hdris(self) -> List[Tuple[str, str]]:
        """Get all HDRIs as (name, path) tuples"""
        return [(k, v) for k, v in sorted(self._hdri_library.items())]

    def scan_hdri_directory(self, directory: Path) -> int:
        """
        Scan directory for HDRI files and add to library.

        Returns number of HDRIs added.
        """
        if not directory.exists():
            return 0

        hdri_extensions = [".exr", ".hdr", ".hdri"]
        count = 0

        for file_path in directory.iterdir():
            if not file_path.is_file():
                continue

            if file_path.suffix.lower() not in hdri_extensions:
                continue

            name = file_path.stem
            self.add_hdri(name, str(file_path))
            count += 1

        return count

    # Preset Creation Helpers

    def create_hdri_preset(
        self,
        name: str,
        hdri_path: str,
        rotation: float = 0.0,
        intensity: float = 1.0,
        exposure: float = 0.0,
    ) -> EnvironmentPreset:
        """Create HDRI environment preset"""
        preset = EnvironmentPreset(
            name=name,
            env_type=EnvironmentType.HDRI,
            hdri_path=hdri_path,
            rotation=rotation,
            intensity=intensity,
            exposure=exposure,
        )

        self._presets[name] = preset
        return preset

    def create_studio_preset(
        self,
        name: str,
        background_color: Tuple[float, float, float] = (0.18, 0.18, 0.18),
        use_ground: bool = True,
        ground_color: Optional[Tuple[float, float, float]] = None,
        ground_roughness: float = 0.5,
    ) -> EnvironmentPreset:
        """Create studio environment preset"""
        preset = EnvironmentPreset(
            name=name,
            env_type=EnvironmentType.SOLID_COLOR,
            background_color=background_color,
            background_visible=True,
            use_ground_plane=use_ground,
            ground_color=ground_color or background_color,
            ground_roughness=ground_roughness,
        )

        self._presets[name] = preset
        return preset

    def create_procedural_sky_preset(
        self,
        name: str,
        sun_direction: Tuple[float, float, float] = (0.5, 1.0, 0.5),
        sun_intensity: float = 1.0,
        sky_tint: Tuple[float, float, float] = (0.8, 0.9, 1.0),
    ) -> EnvironmentPreset:
        """Create procedural sky preset"""
        preset = EnvironmentPreset(
            name=name,
            env_type=EnvironmentType.PROCEDURAL_SKY,
            sun_direction=sun_direction,
            sun_intensity=sun_intensity,
            sky_tint=sky_tint,
            background_visible=True,
            use_ground_plane=True,
        )

        self._presets[name] = preset
        return preset

    # Preset Adjustment

    def adjust_hdri_rotation(self, preset_name: str, rotation: float) -> bool:
        """Adjust HDRI rotation for a preset"""
        preset = self._presets.get(preset_name)
        if not preset or preset.env_type != EnvironmentType.HDRI:
            return False

        preset.rotation = round_float(rotation % 360.0, 2)
        return True

    def adjust_hdri_intensity(self, preset_name: str, intensity: float) -> bool:
        """Adjust HDRI intensity for a preset"""
        preset = self._presets.get(preset_name)
        if not preset:
            return False

        preset.intensity = round_float(max(0.0, intensity))
        return True

    def adjust_exposure(self, preset_name: str, exposure: float) -> bool:
        """Adjust exposure for a preset"""
        preset = self._presets.get(preset_name)
        if not preset:
            return False

        preset.exposure = round_float(exposure)
        return True


# Module-level instance
_manager: Optional[EnvironmentManager] = None


def get_environment_manager() -> EnvironmentManager:
    """Get singleton environment manager"""
    global _manager
    if _manager is None:
        _manager = EnvironmentManager()
    return _manager


# Quick access to built-in presets
def get_neutral_grey() -> EnvironmentPreset:
    return get_environment_manager().get_preset("neutral_grey")


def get_pure_black() -> EnvironmentPreset:
    return get_environment_manager().get_preset("pure_black")


def get_pure_white() -> EnvironmentPreset:
    return get_environment_manager().get_preset("pure_white")


def get_outdoor_daylight() -> EnvironmentPreset:
    return get_environment_manager().get_preset("outdoor_daylight")


def get_golden_hour() -> EnvironmentPreset:
    return get_environment_manager().get_preset("golden_hour")
