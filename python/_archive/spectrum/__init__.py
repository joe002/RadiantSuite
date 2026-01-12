"""
Spectrum - LookDev Tool

Material management and lookdev workflow tool for USD/Solaris.

Features:
- Material library with presets
- Texture set management with auto-detection
- Environment presets (HDRI, studio, procedural)
- Preview configurations
- A/B material comparison
- Human gate integration

Usage:
    from spectrum import spectrum, MaterialType

    # Get manager
    mgr = spectrum()

    # Create material
    material, proposal = mgr.create_material(
        "chrome_metal",
        MaterialType.KARMA_PRINCIPLED,
    )

    # Set environment
    mgr.set_active_environment("neutral_grey")

    # Get preview settings
    settings = mgr.get_preview_settings()
"""

from .models import (
    Material,
    MaterialType,
    MaterialPreset,
    MaterialAssignmentRule,
    TextureSet,
    TextureFile,
    TextureChannel,
    TextureFormat,
    Colorspace,
    ShaderParameter,
    EnvironmentPreset,
    EnvironmentType,
    PreviewConfig,
    PreviewQuality,
)

from .materials import (
    MaterialLibrary,
    get_material_library,
    get_default_parameters,
)

from .textures import (
    TextureManager,
    get_texture_manager,
    detect_texture_channel,
    create_texture_set_from_directory,
    scan_texture_directory,
)

from .environments import (
    EnvironmentManager,
    get_environment_manager,
    get_neutral_grey,
    get_pure_black,
    get_pure_white,
    get_outdoor_daylight,
    get_golden_hour,
)

from .manager import (
    SpectrumManager,
    SpectrumSession,
    spectrum,
)

from .synapse_commands import (
    SpectrumCommandHandler,
    SpectrumCommandType,
    get_spectrum_command_handler,
    register_spectrum_commands,
)

__all__ = [
    # Models
    'Material',
    'MaterialType',
    'MaterialPreset',
    'MaterialAssignmentRule',
    'TextureSet',
    'TextureFile',
    'TextureChannel',
    'TextureFormat',
    'Colorspace',
    'ShaderParameter',
    'EnvironmentPreset',
    'EnvironmentType',
    'PreviewConfig',
    'PreviewQuality',
    # Materials
    'MaterialLibrary',
    'get_material_library',
    'get_default_parameters',
    # Textures
    'TextureManager',
    'get_texture_manager',
    'detect_texture_channel',
    'create_texture_set_from_directory',
    'scan_texture_directory',
    # Environments
    'EnvironmentManager',
    'get_environment_manager',
    'get_neutral_grey',
    'get_pure_black',
    'get_pure_white',
    'get_outdoor_daylight',
    'get_golden_hour',
    # Manager
    'SpectrumManager',
    'SpectrumSession',
    'spectrum',
    # Synapse Integration
    'SpectrumCommandHandler',
    'SpectrumCommandType',
    'get_spectrum_command_handler',
    'register_spectrum_commands',
]
