"""
Aurora Data Models

Core data structures for light groups, AOV definitions, and LPE generation.
Designed for comp-ready AOV delivery with deterministic operations.
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Set
from enum import Enum
import json

from core.determinism import deterministic_uuid, round_float, round_vector


class LightType(Enum):
    """USD/Karma light types"""
    RECT = "RectLight"
    DISK = "DiskLight"
    SPHERE = "SphereLight"
    CYLINDER = "CylinderLight"
    DISTANT = "DistantLight"
    DOME = "DomeLight"
    PORTAL = "PortalLight"
    GEOMETRY = "GeometryLight"
    MESH = "MeshLight"


class LightRole(Enum):
    """Semantic lighting roles for automatic grouping"""
    KEY = "key"
    FILL = "fill"
    RIM = "rim"
    BOUNCE = "bounce"
    KICK = "kick"
    PRACTICAL = "practical"
    AMBIENT = "ambient"
    ENVIRONMENT = "environment"
    SPECULAR = "specular"
    CUSTOM = "custom"


class AOVType(Enum):
    """AOV data types"""
    COLOR3F = "color3f"
    COLOR4F = "color4f"
    FLOAT = "float"
    FLOAT3 = "float3"
    INT = "int"
    VECTOR3F = "vector3f"
    NORMAL3F = "normal3f"
    POINT3F = "point3f"


class LPEComponent(Enum):
    """Light Path Expression components"""
    # Camera events
    CAMERA = "C"

    # Scattering events
    DIFFUSE = "D"
    GLOSSY = "G"
    SPECULAR = "S"
    SUBSURFACE = "SS"
    TRANSMISSION = "T"
    VOLUME = "V"

    # Special events
    EMISSION = "O"
    LIGHT = "L"
    BACKGROUND = "B"

    # Modifiers
    REFLECTION = "R"
    ANY = "."
    ONE_OR_MORE = "+"
    ZERO_OR_MORE = "*"


@dataclass
class LightGroupMember:
    """A light belonging to a group"""
    prim_path: str
    light_type: LightType
    enabled: bool = True
    solo: bool = False
    contribution: float = 1.0  # Multiplier for group contribution

    def __post_init__(self):
        self.contribution = round_float(self.contribution, 4)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "prim_path": self.prim_path,
            "light_type": self.light_type.value,
            "enabled": self.enabled,
            "solo": self.solo,
            "contribution": self.contribution,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'LightGroupMember':
        return cls(
            prim_path=data["prim_path"],
            light_type=LightType(data["light_type"]),
            enabled=data.get("enabled", True),
            solo=data.get("solo", False),
            contribution=data.get("contribution", 1.0),
        )


@dataclass
class LightGroup:
    """
    A named collection of lights for isolation/control.

    Light groups serve two purposes:
    1. Organizational: Group related lights (key lights, practicals, etc.)
    2. AOV Generation: Each group can generate per-light-group AOVs
    """

    name: str
    role: LightRole = LightRole.CUSTOM
    members: List[LightGroupMember] = field(default_factory=list)
    color_tag: str = "#FFFFFF"  # UI color for identification
    description: str = ""

    # Group-level controls
    enabled: bool = True
    intensity_mult: float = 1.0

    # AOV generation settings
    generate_beauty: bool = True
    generate_diffuse: bool = True
    generate_specular: bool = True
    generate_shadow: bool = False
    generate_transmission: bool = False

    # Metadata
    group_id: str = ""
    created_by: str = ""  # Agent or user who created

    def __post_init__(self):
        if not self.group_id:
            content = f"{self.name}:{self.role.value}:{len(self.members)}"
            self.group_id = deterministic_uuid(content, "lightgroup")
        self.intensity_mult = round_float(self.intensity_mult, 4)

    def add_light(self, prim_path: str, light_type: LightType) -> LightGroupMember:
        """Add light to group"""
        member = LightGroupMember(prim_path=prim_path, light_type=light_type)
        self.members.append(member)
        return member

    def remove_light(self, prim_path: str) -> bool:
        """Remove light from group"""
        for i, member in enumerate(self.members):
            if member.prim_path == prim_path:
                self.members.pop(i)
                return True
        return False

    def get_prim_paths(self) -> List[str]:
        """Get all light prim paths in group"""
        return [m.prim_path for m in self.members if m.enabled]

    def get_lpe_light_selector(self) -> str:
        """
        Generate LPE light group selector.

        For Karma: Uses 'lightgroup:groupname' syntax
        Returns the selector string for use in LPE expressions.
        """
        return f"'lightgroup:{self.name}'"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "role": self.role.value,
            "members": [m.to_dict() for m in self.members],
            "color_tag": self.color_tag,
            "description": self.description,
            "enabled": self.enabled,
            "intensity_mult": self.intensity_mult,
            "generate_beauty": self.generate_beauty,
            "generate_diffuse": self.generate_diffuse,
            "generate_specular": self.generate_specular,
            "generate_shadow": self.generate_shadow,
            "generate_transmission": self.generate_transmission,
            "group_id": self.group_id,
            "created_by": self.created_by,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'LightGroup':
        return cls(
            name=data["name"],
            role=LightRole(data.get("role", "custom")),
            members=[LightGroupMember.from_dict(m) for m in data.get("members", [])],
            color_tag=data.get("color_tag", "#FFFFFF"),
            description=data.get("description", ""),
            enabled=data.get("enabled", True),
            intensity_mult=data.get("intensity_mult", 1.0),
            generate_beauty=data.get("generate_beauty", True),
            generate_diffuse=data.get("generate_diffuse", True),
            generate_specular=data.get("generate_specular", True),
            generate_shadow=data.get("generate_shadow", False),
            generate_transmission=data.get("generate_transmission", False),
            group_id=data.get("group_id", ""),
            created_by=data.get("created_by", ""),
        )


@dataclass
class AOVDefinition:
    """
    AOV/render variable definition.

    Supports standard beauty AOVs, custom LPEs, and light group isolation.
    """

    name: str
    aov_type: AOVType = AOVType.COLOR3F
    lpe: str = ""  # Light Path Expression
    source: str = ""  # Built-in source (e.g., "Ci", "N", "P")

    # Compositing metadata
    comp_layer_name: str = ""  # Name in comp (may differ from render name)
    comp_merge_mode: str = "plus"  # plus, over, multiply, screen

    # Light group association
    light_group: str = ""  # If set, this AOV is for a specific light group

    # Settings
    enabled: bool = True
    denoise: bool = False
    filter_type: str = "box"  # box, gaussian, blackman-harris

    # Metadata
    aov_id: str = ""
    description: str = ""

    def __post_init__(self):
        if not self.aov_id:
            content = f"{self.name}:{self.lpe or self.source}"
            self.aov_id = deterministic_uuid(content, "aov")
        if not self.comp_layer_name:
            self.comp_layer_name = self.name

    def get_karma_driver_settings(self) -> Dict[str, Any]:
        """Get settings for Karma render product configuration"""
        settings = {
            "name": self.name,
            "type": self.aov_type.value,
        }

        if self.lpe:
            settings["lpe"] = self.lpe
        elif self.source:
            settings["source"] = self.source

        if self.filter_type != "box":
            settings["filter"] = self.filter_type

        return settings

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "aov_type": self.aov_type.value,
            "lpe": self.lpe,
            "source": self.source,
            "comp_layer_name": self.comp_layer_name,
            "comp_merge_mode": self.comp_merge_mode,
            "light_group": self.light_group,
            "enabled": self.enabled,
            "denoise": self.denoise,
            "filter_type": self.filter_type,
            "aov_id": self.aov_id,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AOVDefinition':
        return cls(
            name=data["name"],
            aov_type=AOVType(data.get("aov_type", "color3f")),
            lpe=data.get("lpe", ""),
            source=data.get("source", ""),
            comp_layer_name=data.get("comp_layer_name", ""),
            comp_merge_mode=data.get("comp_merge_mode", "plus"),
            light_group=data.get("light_group", ""),
            enabled=data.get("enabled", True),
            denoise=data.get("denoise", False),
            filter_type=data.get("filter_type", "box"),
            aov_id=data.get("aov_id", ""),
            description=data.get("description", ""),
        )


@dataclass
class AOVBundle:
    """
    A preset collection of AOVs for common workflows.

    Examples: "comp_basic", "comp_full", "debug", "lookdev"
    """

    name: str
    description: str = ""
    aovs: List[AOVDefinition] = field(default_factory=list)

    # What this bundle is for
    workflow: str = "comp"  # comp, lookdev, debug, lighting

    # Auto-generation from light groups
    per_light_group: bool = False  # If True, duplicate AOVs per light group

    # Metadata
    bundle_id: str = ""

    def __post_init__(self):
        if not self.bundle_id:
            content = f"{self.name}:{self.workflow}:{len(self.aovs)}"
            self.bundle_id = deterministic_uuid(content, "bundle")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "aovs": [a.to_dict() for a in self.aovs],
            "workflow": self.workflow,
            "per_light_group": self.per_light_group,
            "bundle_id": self.bundle_id,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AOVBundle':
        return cls(
            name=data["name"],
            description=data.get("description", ""),
            aovs=[AOVDefinition.from_dict(a) for a in data.get("aovs", [])],
            workflow=data.get("workflow", "comp"),
            per_light_group=data.get("per_light_group", False),
            bundle_id=data.get("bundle_id", ""),
        )


@dataclass
class LightLinkRule:
    """
    Light linking/shadow linking rule.

    Controls which lights affect which geometry.
    """

    name: str
    light_pattern: str  # Glob pattern for lights (e.g., "/World/Lights/key_*")
    geometry_pattern: str  # Glob pattern for geometry (e.g., "/World/Geo/character/*")

    # Linking type
    illumination: bool = True  # Light illuminates geometry
    shadow: bool = True  # Geometry casts shadow from this light

    # Rule behavior
    include: bool = True  # True = include, False = exclude
    priority: int = 0  # Higher priority rules override lower

    # Metadata
    rule_id: str = ""
    description: str = ""

    def __post_init__(self):
        if not self.rule_id:
            content = f"{self.name}:{self.light_pattern}:{self.geometry_pattern}"
            self.rule_id = deterministic_uuid(content, "linkrule")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "light_pattern": self.light_pattern,
            "geometry_pattern": self.geometry_pattern,
            "illumination": self.illumination,
            "shadow": self.shadow,
            "include": self.include,
            "priority": self.priority,
            "rule_id": self.rule_id,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'LightLinkRule':
        return cls(
            name=data["name"],
            light_pattern=data["light_pattern"],
            geometry_pattern=data["geometry_pattern"],
            illumination=data.get("illumination", True),
            shadow=data.get("shadow", True),
            include=data.get("include", True),
            priority=data.get("priority", 0),
            rule_id=data.get("rule_id", ""),
            description=data.get("description", ""),
        )
