"""
Spectrum Texture System

Texture set management, channel detection, and UDIM handling.
Supports automatic channel detection from naming conventions.
"""

import re
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Set
from dataclasses import dataclass

from .models import (
    TextureSet, TextureFile, TextureChannel, TextureFormat, Colorspace,
)

from core.determinism import deterministic_uuid, deterministic_sort
from core.audit import audit_log, AuditCategory, AuditLevel


# Channel detection patterns (regex)
CHANNEL_PATTERNS = {
    TextureChannel.ALBEDO: [
        r"_(?:albedo|alb|color|col|diffuse|diff|base_?color|basecolor)(?:_|\.)",
        r"(?:albedo|alb|color|col|diffuse|diff|base_?color|basecolor)\.",
    ],
    TextureChannel.ROUGHNESS: [
        r"_(?:roughness|rough|rgh|gloss)(?:_|\.)",
        r"(?:roughness|rough|rgh|gloss)\.",
    ],
    TextureChannel.METALLIC: [
        r"_(?:metallic|metal|mtl|metalness)(?:_|\.)",
        r"(?:metallic|metal|mtl|metalness)\.",
    ],
    TextureChannel.NORMAL: [
        r"_(?:normal|nrm|nor|norm)(?:_|\.)",
        r"(?:normal|nrm|nor|norm)\.",
    ],
    TextureChannel.BUMP: [
        r"_(?:bump|bmp)(?:_|\.)",
        r"(?:bump|bmp)\.",
    ],
    TextureChannel.DISPLACEMENT: [
        r"_(?:displacement|disp|height|hgt)(?:_|\.)",
        r"(?:displacement|disp)\.",
    ],
    TextureChannel.HEIGHT: [
        r"_(?:height|hgt)(?:_|\.)",
        r"(?:height|hgt)\.",
    ],
    TextureChannel.AMBIENT_OCCLUSION: [
        r"_(?:ao|ambient_?occlusion|occlusion|occ)(?:_|\.)",
        r"(?:ao|ambient_?occlusion|occlusion|occ)\.",
    ],
    TextureChannel.EMISSIVE: [
        r"_(?:emissive|emit|emission|glow)(?:_|\.)",
        r"(?:emissive|emit|emission|glow)\.",
    ],
    TextureChannel.OPACITY: [
        r"_(?:opacity|alpha|transparency|mask)(?:_|\.)",
        r"(?:opacity|alpha|transparency|mask)\.",
    ],
    TextureChannel.SPECULAR: [
        r"_(?:specular|spec|reflection|refl)(?:_|\.)",
        r"(?:specular|spec|reflection|refl)\.",
    ],
    TextureChannel.TRANSMISSION: [
        r"_(?:transmission|trans|refraction)(?:_|\.)",
        r"(?:transmission|trans|refraction)\.",
    ],
    TextureChannel.SUBSURFACE: [
        r"_(?:subsurface|sss|scatter)(?:_|\.)",
        r"(?:subsurface|sss|scatter)\.",
    ],
    TextureChannel.COAT: [
        r"_(?:coat|clearcoat|clear_?coat)(?:_|\.)",
        r"(?:coat|clearcoat|clear_?coat)\.",
    ],
}

# UDIM patterns
UDIM_PATTERNS = [
    r"(\d{4})",  # 1001, 1002, etc.
    r"<UDIM>",
    r"\$\(UDIM\)",
    r"%\(UDIM\)d",
    r"_u(\d+)_v(\d+)_",  # Mari style
]

# Resolution detection patterns
RESOLUTION_PATTERNS = {
    "512": (512, 512),
    "1k": (1024, 1024),
    "2k": (2048, 2048),
    "4k": (4096, 4096),
    "8k": (8192, 8192),
    "16k": (16384, 16384),
}


def detect_texture_channel(filename: str) -> Optional[TextureChannel]:
    """
    Detect texture channel from filename.

    Uses naming conventions to identify the channel type.
    """
    filename_lower = filename.lower()

    for channel, patterns in CHANNEL_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, filename_lower, re.IGNORECASE):
                return channel

    return None


def detect_texture_format(path: str) -> TextureFormat:
    """Detect texture format from file extension"""
    ext = Path(path).suffix.lower().lstrip(".")

    format_map = {
        "exr": TextureFormat.EXR,
        "tx": TextureFormat.TX,
        "tex": TextureFormat.TEX,
        "png": TextureFormat.PNG,
        "tif": TextureFormat.TIFF,
        "tiff": TextureFormat.TIFF,
        "jpg": TextureFormat.JPG,
        "jpeg": TextureFormat.JPG,
        "hdr": TextureFormat.HDR,
        "rat": TextureFormat.RAT,
    }

    return format_map.get(ext, TextureFormat.EXR)


def detect_udim(filename: str) -> Tuple[bool, str]:
    """
    Detect if texture uses UDIM.

    Returns (is_udim, pattern_used).
    """
    # Check for explicit UDIM tokens
    if "<UDIM>" in filename or "$(UDIM)" in filename:
        return True, filename

    # Check for 4-digit UDIM number
    match = re.search(r"[._](\d{4})[._]", filename)
    if match:
        udim_num = match.group(1)
        if 1001 <= int(udim_num) <= 9999:
            # Create pattern
            pattern = filename.replace(udim_num, "<UDIM>")
            return True, pattern

    return False, filename


def detect_resolution(filename: str) -> Optional[Tuple[int, int]]:
    """Detect resolution from filename"""
    filename_lower = filename.lower()

    for res_name, resolution in RESOLUTION_PATTERNS.items():
        if res_name in filename_lower:
            return resolution

    return None


def scan_texture_directory(
    directory: Path,
    extensions: Optional[List[str]] = None,
) -> List[TextureFile]:
    """
    Scan directory for texture files.

    Returns list of TextureFile objects with auto-detected properties.
    """
    if extensions is None:
        extensions = [".exr", ".tx", ".tex", ".png", ".tif", ".tiff", ".jpg", ".jpeg", ".hdr"]

    textures = []
    seen_patterns = set()

    if not directory.exists():
        return textures

    for file_path in directory.iterdir():
        if not file_path.is_file():
            continue

        if file_path.suffix.lower() not in extensions:
            continue

        filename = file_path.name

        # Detect channel
        channel = detect_texture_channel(filename)
        if not channel:
            continue  # Skip unrecognized textures

        # Detect format
        tex_format = detect_texture_format(str(file_path))

        # Detect UDIM
        is_udim, udim_pattern = detect_udim(filename)

        # Skip duplicate UDIM patterns
        if is_udim:
            pattern_key = f"{channel.value}:{udim_pattern}"
            if pattern_key in seen_patterns:
                continue
            seen_patterns.add(pattern_key)

        # Detect resolution
        resolution = detect_resolution(filename) or (2048, 2048)

        texture = TextureFile(
            path=str(file_path),
            channel=channel,
            format=tex_format,
            is_udim=is_udim,
            udim_pattern=udim_pattern if is_udim else "",
            resolution=resolution,
        )

        textures.append(texture)

    return deterministic_sort(textures, key=lambda t: (t.channel.value, t.path))


def create_texture_set_from_directory(
    name: str,
    directory: Path,
    extensions: Optional[List[str]] = None,
) -> TextureSet:
    """
    Create TextureSet from directory scan.

    Auto-detects all texture channels and properties.
    """
    textures = scan_texture_directory(directory, extensions)

    # Detect resolution variant from first texture
    resolution_variant = "2k"
    if textures:
        res = textures[0].resolution
        if res[0] <= 512:
            resolution_variant = "512"
        elif res[0] <= 1024:
            resolution_variant = "1k"
        elif res[0] <= 2048:
            resolution_variant = "2k"
        elif res[0] <= 4096:
            resolution_variant = "4k"
        else:
            resolution_variant = "8k"

    # Detect UDIM range
    udim_start = 1001
    udim_end = 1001

    for tex in textures:
        if tex.is_udim:
            # Scan for actual UDIM tiles
            base_path = Path(tex.path).parent
            pattern = tex.udim_pattern.replace("<UDIM>", r"(\d{4})")

            for file_path in base_path.iterdir():
                match = re.search(pattern, file_path.name)
                if match:
                    udim_num = int(match.group(1))
                    udim_start = min(udim_start, udim_num)
                    udim_end = max(udim_end, udim_num)
            break

    texture_set = TextureSet(
        name=name,
        textures=textures,
        resolution_variant=resolution_variant,
        base_path=str(directory),
        udim_start=udim_start,
        udim_end=udim_end,
    )

    audit_log().log(
        operation="create_texture_set",
        message=f"Created texture set '{name}' with {len(textures)} textures from {directory}",
        level=AuditLevel.INFO,
        category=AuditCategory.MATERIAL,
        tool="spectrum",
        input_data={
            "name": name,
            "directory": str(directory),
            "channels": [t.channel.value for t in textures],
        },
    )

    return texture_set


class TextureManager:
    """
    Texture set manager with caching and resolution switching.

    Provides:
    - Texture set storage
    - Resolution variant management
    - Texture path resolution
    - Format conversion helpers
    """

    def __init__(self):
        self._texture_sets: Dict[str, TextureSet] = {}
        self._resolution_variants: Dict[str, Dict[str, TextureSet]] = {}  # name -> {variant -> set}

    def add_texture_set(self, texture_set: TextureSet) -> None:
        """Add texture set to manager"""
        self._texture_sets[texture_set.name] = texture_set

        # Track resolution variant
        if texture_set.name not in self._resolution_variants:
            self._resolution_variants[texture_set.name] = {}

        self._resolution_variants[texture_set.name][texture_set.resolution_variant] = texture_set

    def get_texture_set(
        self,
        name: str,
        resolution_variant: Optional[str] = None,
    ) -> Optional[TextureSet]:
        """
        Get texture set, optionally at specific resolution.

        If resolution_variant specified, looks for that variant.
        Falls back to default if not found.
        """
        if resolution_variant and name in self._resolution_variants:
            variants = self._resolution_variants[name]
            if resolution_variant in variants:
                return variants[resolution_variant]

        return self._texture_sets.get(name)

    def get_available_resolutions(self, name: str) -> List[str]:
        """Get available resolution variants for a texture set"""
        if name in self._resolution_variants:
            return deterministic_sort(list(self._resolution_variants[name].keys()))
        return []

    def remove_texture_set(self, name: str) -> bool:
        """Remove texture set"""
        if name in self._texture_sets:
            del self._texture_sets[name]
            if name in self._resolution_variants:
                del self._resolution_variants[name]
            return True
        return False

    def get_all_texture_sets(self) -> List[TextureSet]:
        """Get all texture sets"""
        return list(self._texture_sets.values())

    def scan_and_add(
        self,
        name: str,
        directory: Path,
    ) -> Optional[TextureSet]:
        """Scan directory and add resulting texture set"""
        texture_set = create_texture_set_from_directory(name, directory)

        if texture_set.textures:
            self.add_texture_set(texture_set)
            return texture_set

        return None

    def get_texture_path(
        self,
        set_name: str,
        channel: TextureChannel,
        resolution_variant: Optional[str] = None,
    ) -> Optional[str]:
        """Get texture path for channel from set"""
        texture_set = self.get_texture_set(set_name, resolution_variant)
        if not texture_set:
            return None

        texture = texture_set.get_texture(channel)
        if texture:
            return texture.path

        return None


# Module-level instance
_manager: Optional[TextureManager] = None


def get_texture_manager() -> TextureManager:
    """Get singleton texture manager"""
    global _manager
    if _manager is None:
        _manager = TextureManager()
    return _manager


# Texture channel to shader parameter mapping
CHANNEL_TO_PARAM = {
    TextureChannel.ALBEDO: ["baseColor", "diffuseColor"],
    TextureChannel.DIFFUSE: ["diffuseColor", "baseColor"],
    TextureChannel.BASE_COLOR: ["baseColor", "diffuseColor"],
    TextureChannel.ROUGHNESS: ["roughness"],
    TextureChannel.METALLIC: ["metallic"],
    TextureChannel.SPECULAR: ["specular", "specularColor"],
    TextureChannel.NORMAL: ["normal"],
    TextureChannel.BUMP: ["bump"],
    TextureChannel.DISPLACEMENT: ["displacement"],
    TextureChannel.AMBIENT_OCCLUSION: ["occlusion"],
    TextureChannel.EMISSIVE: ["emissiveColor", "emission"],
    TextureChannel.OPACITY: ["opacity", "alpha"],
    TextureChannel.TRANSMISSION: ["transmission"],
    TextureChannel.SUBSURFACE: ["subsurface"],
    TextureChannel.COAT: ["clearcoat", "coat"],
}


def get_param_for_channel(channel: TextureChannel) -> List[str]:
    """Get shader parameter names for a texture channel"""
    return CHANNEL_TO_PARAM.get(channel, [])
