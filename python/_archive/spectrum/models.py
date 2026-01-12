"""
Spectrum Data Models

Core data structures for material management, texture sets, and lookdev workflows.
Designed for USD/MaterialX compatibility with agent-first operations.
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Tuple
from enum import Enum
from pathlib import Path

from core.determinism import deterministic_uuid, round_float, round_vector


class MaterialType(Enum):
    """USD/MaterialX material types"""
    USD_PREVIEW_SURFACE = "UsdPreviewSurface"
    MATERIALX_STANDARD = "MtlxStandardSurface"
    KARMA_PRINCIPLED = "KarmaPrincipled"
    ARNOLD_STANDARD = "ArnoldStandardSurface"
    RENDERMAN_PXR = "PxrSurface"
    CUSTOM = "Custom"


class TextureChannel(Enum):
    """Standard PBR texture channels"""
    ALBEDO = "albedo"
    DIFFUSE = "diffuse"
    BASE_COLOR = "base_color"
    ROUGHNESS = "roughness"
    METALLIC = "metallic"
    SPECULAR = "specular"
    NORMAL = "normal"
    BUMP = "bump"
    DISPLACEMENT = "displacement"
    HEIGHT = "height"
    AMBIENT_OCCLUSION = "ao"
    EMISSIVE = "emissive"
    OPACITY = "opacity"
    TRANSMISSION = "transmission"
    SUBSURFACE = "subsurface"
    SUBSURFACE_COLOR = "subsurface_color"
    COAT = "coat"
    COAT_ROUGHNESS = "coat_roughness"
    SHEEN = "sheen"
    SHEEN_ROUGHNESS = "sheen_roughness"
    IOR = "ior"


class Colorspace(Enum):
    """Texture colorspaces"""
    SRGB = "sRGB"
    LINEAR = "linear"
    RAW = "raw"
    ACES_CG = "ACEScg"
    ACES_2065_1 = "ACES2065-1"
    REC709 = "Rec.709"
    AUTO = "auto"


class TextureFormat(Enum):
    """Supported texture formats"""
    EXR = "exr"
    TX = "tx"  # Renderman/Arnold texture format
    TEX = "tex"  # Karma/Mantra texture format
    PNG = "png"
    TIFF = "tiff"
    JPG = "jpg"
    HDR = "hdr"
    RAT = "rat"  # Houdini RAT format


class PreviewQuality(Enum):
    """Preview render quality levels"""
    DRAFT = "draft"
    MEDIUM = "medium"
    HIGH = "high"
    FINAL = "final"


class EnvironmentType(Enum):
    """Environment lighting types"""
    HDRI = "hdri"
    PROCEDURAL_SKY = "procedural_sky"
    GRADIENT = "gradient"
    SOLID_COLOR = "solid"
    STUDIO = "studio"


@dataclass
class TextureFile:
    """Single texture file reference"""
    path: str
    channel: TextureChannel
    colorspace: Colorspace = Colorspace.AUTO
    format: TextureFormat = TextureFormat.EXR

    # UDIM support
    is_udim: bool = False
    udim_pattern: str = "<UDIM>"  # <UDIM>, %(UDIM)d, etc.

    # Resolution
    resolution: Tuple[int, int] = (2048, 2048)

    # Streaming
    use_mipmaps: bool = True
    max_memory_mb: float = 0  # 0 = unlimited

    # Metadata
    texture_id: str = ""

    def __post_init__(self):
        if not self.texture_id:
            content = f"{self.path}:{self.channel.value}"
            self.texture_id = deterministic_uuid(content, "texture")

        # Auto-detect colorspace if not specified
        if self.colorspace == Colorspace.AUTO:
            self.colorspace = self._detect_colorspace()

    def _detect_colorspace(self) -> Colorspace:
        """Detect colorspace from channel type"""
        linear_channels = {
            TextureChannel.ROUGHNESS,
            TextureChannel.METALLIC,
            TextureChannel.NORMAL,
            TextureChannel.BUMP,
            TextureChannel.DISPLACEMENT,
            TextureChannel.HEIGHT,
            TextureChannel.AMBIENT_OCCLUSION,
            TextureChannel.OPACITY,
        }
        if self.channel in linear_channels:
            return Colorspace.LINEAR
        return Colorspace.SRGB

    def to_dict(self) -> Dict[str, Any]:
        return {
            "path": self.path,
            "channel": self.channel.value,
            "colorspace": self.colorspace.value,
            "format": self.format.value,
            "is_udim": self.is_udim,
            "udim_pattern": self.udim_pattern,
            "resolution": list(self.resolution),
            "use_mipmaps": self.use_mipmaps,
            "max_memory_mb": self.max_memory_mb,
            "texture_id": self.texture_id,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TextureFile':
        return cls(
            path=data["path"],
            channel=TextureChannel(data["channel"]),
            colorspace=Colorspace(data.get("colorspace", "auto")),
            format=TextureFormat(data.get("format", "exr")),
            is_udim=data.get("is_udim", False),
            udim_pattern=data.get("udim_pattern", "<UDIM>"),
            resolution=tuple(data.get("resolution", [2048, 2048])),
            use_mipmaps=data.get("use_mipmaps", True),
            max_memory_mb=data.get("max_memory_mb", 0),
            texture_id=data.get("texture_id", ""),
        )


@dataclass
class TextureSet:
    """
    Collection of texture files for a material.

    Represents a complete set of PBR textures with consistent
    naming, resolution, and UDIM handling.
    """
    name: str
    textures: List[TextureFile] = field(default_factory=list)

    # Resolution variant
    resolution_variant: str = "2k"  # 1k, 2k, 4k, 8k

    # Base path for relative texture paths
    base_path: str = ""

    # UDIM range
    udim_start: int = 1001
    udim_end: int = 1001

    # Metadata
    set_id: str = ""
    description: str = ""
    tags: List[str] = field(default_factory=list)

    def __post_init__(self):
        if not self.set_id:
            content = f"{self.name}:{self.resolution_variant}"
            self.set_id = deterministic_uuid(content, "textureset")

    def get_texture(self, channel: TextureChannel) -> Optional[TextureFile]:
        """Get texture by channel"""
        for tex in self.textures:
            if tex.channel == channel:
                return tex
        return None

    def add_texture(self, texture: TextureFile) -> None:
        """Add texture to set"""
        # Remove existing texture for same channel
        self.textures = [t for t in self.textures if t.channel != texture.channel]
        self.textures.append(texture)

    def get_channels(self) -> List[TextureChannel]:
        """Get list of available channels"""
        return [t.channel for t in self.textures]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "textures": [t.to_dict() for t in self.textures],
            "resolution_variant": self.resolution_variant,
            "base_path": self.base_path,
            "udim_start": self.udim_start,
            "udim_end": self.udim_end,
            "set_id": self.set_id,
            "description": self.description,
            "tags": self.tags,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TextureSet':
        return cls(
            name=data["name"],
            textures=[TextureFile.from_dict(t) for t in data.get("textures", [])],
            resolution_variant=data.get("resolution_variant", "2k"),
            base_path=data.get("base_path", ""),
            udim_start=data.get("udim_start", 1001),
            udim_end=data.get("udim_end", 1001),
            set_id=data.get("set_id", ""),
            description=data.get("description", ""),
            tags=data.get("tags", []),
        )


@dataclass
class ShaderParameter:
    """Single shader parameter definition"""
    name: str
    value: Any
    param_type: str = "float"  # float, float3, color3f, bool, string, int
    min_value: Optional[Any] = None
    max_value: Optional[Any] = None
    default_value: Optional[Any] = None
    ui_label: str = ""
    ui_group: str = ""
    is_connected: bool = False  # True if connected to texture
    connected_to: str = ""  # Texture channel or node path

    def __post_init__(self):
        # Round float values for determinism
        if self.param_type == "float" and isinstance(self.value, float):
            self.value = round_float(self.value)
        elif self.param_type in ("float3", "color3f") and isinstance(self.value, (list, tuple)):
            self.value = round_vector(self.value)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "value": self.value,
            "param_type": self.param_type,
            "min_value": self.min_value,
            "max_value": self.max_value,
            "default_value": self.default_value,
            "ui_label": self.ui_label,
            "ui_group": self.ui_group,
            "is_connected": self.is_connected,
            "connected_to": self.connected_to,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ShaderParameter':
        return cls(
            name=data["name"],
            value=data["value"],
            param_type=data.get("param_type", "float"),
            min_value=data.get("min_value"),
            max_value=data.get("max_value"),
            default_value=data.get("default_value"),
            ui_label=data.get("ui_label", ""),
            ui_group=data.get("ui_group", ""),
            is_connected=data.get("is_connected", False),
            connected_to=data.get("connected_to", ""),
        )


@dataclass
class Material:
    """
    USD Material definition.

    Represents a complete material with shader parameters and texture bindings.
    """
    name: str
    material_type: MaterialType = MaterialType.KARMA_PRINCIPLED
    parameters: List[ShaderParameter] = field(default_factory=list)
    texture_set: Optional[TextureSet] = None

    # USD path
    prim_path: str = ""

    # Variants
    variant_name: str = "default"
    variant_set: str = ""

    # Look/LOD
    purpose: str = "default"  # default, preview, proxy

    # Metadata
    material_id: str = ""
    description: str = ""
    tags: List[str] = field(default_factory=list)
    created_by: str = ""

    # Render settings
    double_sided: bool = False
    use_displacement: bool = False
    displacement_scale: float = 1.0

    def __post_init__(self):
        if not self.material_id:
            content = f"{self.name}:{self.material_type.value}:{self.variant_name}"
            self.material_id = deterministic_uuid(content, "material")

        self.displacement_scale = round_float(self.displacement_scale)

    def get_parameter(self, name: str) -> Optional[ShaderParameter]:
        """Get parameter by name"""
        for param in self.parameters:
            if param.name == name:
                return param
        return None

    def set_parameter(self, name: str, value: Any) -> bool:
        """Set parameter value"""
        for param in self.parameters:
            if param.name == name:
                param.value = value
                return True
        return False

    def add_parameter(self, param: ShaderParameter) -> None:
        """Add or update parameter"""
        # Remove existing
        self.parameters = [p for p in self.parameters if p.name != param.name]
        self.parameters.append(param)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "material_type": self.material_type.value,
            "parameters": [p.to_dict() for p in self.parameters],
            "texture_set": self.texture_set.to_dict() if self.texture_set else None,
            "prim_path": self.prim_path,
            "variant_name": self.variant_name,
            "variant_set": self.variant_set,
            "purpose": self.purpose,
            "material_id": self.material_id,
            "description": self.description,
            "tags": self.tags,
            "created_by": self.created_by,
            "double_sided": self.double_sided,
            "use_displacement": self.use_displacement,
            "displacement_scale": self.displacement_scale,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Material':
        texture_set = None
        if data.get("texture_set"):
            texture_set = TextureSet.from_dict(data["texture_set"])

        return cls(
            name=data["name"],
            material_type=MaterialType(data.get("material_type", "KarmaPrincipled")),
            parameters=[ShaderParameter.from_dict(p) for p in data.get("parameters", [])],
            texture_set=texture_set,
            prim_path=data.get("prim_path", ""),
            variant_name=data.get("variant_name", "default"),
            variant_set=data.get("variant_set", ""),
            purpose=data.get("purpose", "default"),
            material_id=data.get("material_id", ""),
            description=data.get("description", ""),
            tags=data.get("tags", []),
            created_by=data.get("created_by", ""),
            double_sided=data.get("double_sided", False),
            use_displacement=data.get("use_displacement", False),
            displacement_scale=data.get("displacement_scale", 1.0),
        )


@dataclass
class MaterialAssignmentRule:
    """Pattern-based material assignment rule"""
    name: str
    material_name: str
    geometry_pattern: str  # Glob pattern for geometry prims

    # Priority for overlapping rules
    priority: int = 0

    # Scope
    include_children: bool = True

    # Conditions
    attribute_match: Dict[str, Any] = field(default_factory=dict)  # Attribute conditions

    # Metadata
    rule_id: str = ""
    description: str = ""

    def __post_init__(self):
        if not self.rule_id:
            content = f"{self.name}:{self.material_name}:{self.geometry_pattern}"
            self.rule_id = deterministic_uuid(content, "assignment")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "material_name": self.material_name,
            "geometry_pattern": self.geometry_pattern,
            "priority": self.priority,
            "include_children": self.include_children,
            "attribute_match": self.attribute_match,
            "rule_id": self.rule_id,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'MaterialAssignmentRule':
        return cls(
            name=data["name"],
            material_name=data["material_name"],
            geometry_pattern=data["geometry_pattern"],
            priority=data.get("priority", 0),
            include_children=data.get("include_children", True),
            attribute_match=data.get("attribute_match", {}),
            rule_id=data.get("rule_id", ""),
            description=data.get("description", ""),
        )


@dataclass
class EnvironmentPreset:
    """HDRI/Environment lighting preset for lookdev"""
    name: str
    env_type: EnvironmentType = EnvironmentType.HDRI

    # HDRI settings
    hdri_path: str = ""
    rotation: float = 0.0  # Degrees
    intensity: float = 1.0
    exposure: float = 0.0

    # Background
    background_visible: bool = True
    background_color: Tuple[float, float, float] = (0.18, 0.18, 0.18)

    # Ground plane
    use_ground_plane: bool = False
    ground_color: Tuple[float, float, float] = (0.18, 0.18, 0.18)
    ground_roughness: float = 0.5

    # Procedural sky settings (if env_type == PROCEDURAL_SKY)
    sun_direction: Tuple[float, float, float] = (0.5, 1.0, 0.5)
    sky_tint: Tuple[float, float, float] = (0.8, 0.9, 1.0)
    sun_intensity: float = 1.0

    # Metadata
    preset_id: str = ""
    description: str = ""
    tags: List[str] = field(default_factory=list)

    def __post_init__(self):
        if not self.preset_id:
            content = f"{self.name}:{self.env_type.value}"
            self.preset_id = deterministic_uuid(content, "envpreset")

        self.rotation = round_float(self.rotation, 2)
        self.intensity = round_float(self.intensity)
        self.exposure = round_float(self.exposure)
        self.ground_roughness = round_float(self.ground_roughness)
        self.sun_intensity = round_float(self.sun_intensity)
        self.background_color = round_vector(self.background_color)
        self.ground_color = round_vector(self.ground_color)
        self.sun_direction = round_vector(self.sun_direction)
        self.sky_tint = round_vector(self.sky_tint)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "env_type": self.env_type.value,
            "hdri_path": self.hdri_path,
            "rotation": self.rotation,
            "intensity": self.intensity,
            "exposure": self.exposure,
            "background_visible": self.background_visible,
            "background_color": list(self.background_color),
            "use_ground_plane": self.use_ground_plane,
            "ground_color": list(self.ground_color),
            "ground_roughness": self.ground_roughness,
            "sun_direction": list(self.sun_direction),
            "sky_tint": list(self.sky_tint),
            "sun_intensity": self.sun_intensity,
            "preset_id": self.preset_id,
            "description": self.description,
            "tags": self.tags,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'EnvironmentPreset':
        return cls(
            name=data["name"],
            env_type=EnvironmentType(data.get("env_type", "hdri")),
            hdri_path=data.get("hdri_path", ""),
            rotation=data.get("rotation", 0.0),
            intensity=data.get("intensity", 1.0),
            exposure=data.get("exposure", 0.0),
            background_visible=data.get("background_visible", True),
            background_color=tuple(data.get("background_color", [0.18, 0.18, 0.18])),
            use_ground_plane=data.get("use_ground_plane", False),
            ground_color=tuple(data.get("ground_color", [0.18, 0.18, 0.18])),
            ground_roughness=data.get("ground_roughness", 0.5),
            sun_direction=tuple(data.get("sun_direction", [0.5, 1.0, 0.5])),
            sky_tint=tuple(data.get("sky_tint", [0.8, 0.9, 1.0])),
            sun_intensity=data.get("sun_intensity", 1.0),
            preset_id=data.get("preset_id", ""),
            description=data.get("description", ""),
            tags=data.get("tags", []),
        )


@dataclass
class PreviewConfig:
    """Configuration for lookdev preview renders"""
    name: str
    quality: PreviewQuality = PreviewQuality.MEDIUM

    # Resolution
    resolution: Tuple[int, int] = (1920, 1080)

    # Camera
    camera_preset: str = "front"  # front, 3/4, top, custom
    camera_distance: float = 5.0
    camera_fov: float = 50.0

    # Turntable
    enable_turntable: bool = False
    turntable_frames: int = 90
    turntable_start_angle: float = 0.0

    # Render settings
    samples: int = 64
    use_denoiser: bool = True
    motion_blur: bool = False

    # Output
    output_format: TextureFormat = TextureFormat.PNG
    output_path: str = ""

    # Metadata
    config_id: str = ""

    def __post_init__(self):
        if not self.config_id:
            content = f"{self.name}:{self.quality.value}:{self.resolution}"
            self.config_id = deterministic_uuid(content, "preview")

        self.camera_distance = round_float(self.camera_distance)
        self.camera_fov = round_float(self.camera_fov)
        self.turntable_start_angle = round_float(self.turntable_start_angle)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "quality": self.quality.value,
            "resolution": list(self.resolution),
            "camera_preset": self.camera_preset,
            "camera_distance": self.camera_distance,
            "camera_fov": self.camera_fov,
            "enable_turntable": self.enable_turntable,
            "turntable_frames": self.turntable_frames,
            "turntable_start_angle": self.turntable_start_angle,
            "samples": self.samples,
            "use_denoiser": self.use_denoiser,
            "motion_blur": self.motion_blur,
            "output_format": self.output_format.value,
            "output_path": self.output_path,
            "config_id": self.config_id,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PreviewConfig':
        return cls(
            name=data["name"],
            quality=PreviewQuality(data.get("quality", "medium")),
            resolution=tuple(data.get("resolution", [1920, 1080])),
            camera_preset=data.get("camera_preset", "front"),
            camera_distance=data.get("camera_distance", 5.0),
            camera_fov=data.get("camera_fov", 50.0),
            enable_turntable=data.get("enable_turntable", False),
            turntable_frames=data.get("turntable_frames", 90),
            turntable_start_angle=data.get("turntable_start_angle", 0.0),
            samples=data.get("samples", 64),
            use_denoiser=data.get("use_denoiser", True),
            motion_blur=data.get("motion_blur", False),
            output_format=TextureFormat(data.get("output_format", "png")),
            output_path=data.get("output_path", ""),
            config_id=data.get("config_id", ""),
        )


@dataclass
class MaterialPreset:
    """
    Reusable material parameter preset.

    Allows saving and applying parameter configurations across materials.
    """
    name: str
    material_type: MaterialType
    parameters: List[ShaderParameter] = field(default_factory=list)

    # Categorization
    category: str = "general"  # metal, wood, fabric, skin, plastic, glass, etc.
    subcategory: str = ""

    # Metadata
    preset_id: str = ""
    description: str = ""
    tags: List[str] = field(default_factory=list)
    thumbnail_path: str = ""

    def __post_init__(self):
        if not self.preset_id:
            content = f"{self.name}:{self.material_type.value}:{self.category}"
            self.preset_id = deterministic_uuid(content, "matpreset")

    def apply_to_material(self, material: Material) -> List[str]:
        """
        Apply preset parameters to material.

        Returns list of applied parameter names.
        """
        applied = []
        for preset_param in self.parameters:
            if material.set_parameter(preset_param.name, preset_param.value):
                applied.append(preset_param.name)
            else:
                # Parameter doesn't exist, add it
                material.add_parameter(ShaderParameter(
                    name=preset_param.name,
                    value=preset_param.value,
                    param_type=preset_param.param_type,
                ))
                applied.append(preset_param.name)

        return applied

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "material_type": self.material_type.value,
            "parameters": [p.to_dict() for p in self.parameters],
            "category": self.category,
            "subcategory": self.subcategory,
            "preset_id": self.preset_id,
            "description": self.description,
            "tags": self.tags,
            "thumbnail_path": self.thumbnail_path,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'MaterialPreset':
        return cls(
            name=data["name"],
            material_type=MaterialType(data.get("material_type", "KarmaPrincipled")),
            parameters=[ShaderParameter.from_dict(p) for p in data.get("parameters", [])],
            category=data.get("category", "general"),
            subcategory=data.get("subcategory", ""),
            preset_id=data.get("preset_id", ""),
            description=data.get("description", ""),
            tags=data.get("tags", []),
            thumbnail_path=data.get("thumbnail_path", ""),
        )
