"""
Aurora - Light Groups & AOV Manager

Agent-first lighting workflow tool for USD/Solaris.

Features:
- Light group management with semantic roles
- Per-light-group AOV generation with LPE
- Light linking with pattern rules
- Human gate integration for approval workflows
- Deterministic operations for reproducibility

Usage:
    from aurora import aurora, LightRole, LightType

    # Get manager
    mgr = aurora()
    mgr.set_sequence("shot_010")

    # Create light group
    group, proposal = mgr.create_light_group(
        "key_lights",
        LightRole.KEY,
        lights=[
            ("/World/Lights/key_main", LightType.RECT),
            ("/World/Lights/key_fill", LightType.DISK),
        ]
    )

    # Get all AOVs for render
    aovs = mgr.get_all_aovs()
"""

from .models import (
    LightGroup,
    LightGroupMember,
    LightType,
    LightRole,
    AOVDefinition,
    AOVBundle,
    AOVType,
    LightLinkRule,
    LPEComponent,
)

from .lpe import (
    LPEGenerator,
    LPEPreset,
    get_lpe_generator,
    STANDARD_AOVS,
)

from .linking import (
    LightLinker,
    LinkMode,
    LinkCollection,
    LinkRelationship,
    get_light_linker,
)

from .manager import (
    AuroraManager,
    AuroraSession,
    aurora,
)

from .synapse_commands import (
    AuroraCommandHandler,
    AuroraCommandType,
    get_aurora_command_handler,
    register_aurora_commands,
)

__all__ = [
    # Models
    'LightGroup',
    'LightGroupMember',
    'LightType',
    'LightRole',
    'AOVDefinition',
    'AOVBundle',
    'AOVType',
    'LightLinkRule',
    'LPEComponent',
    # LPE
    'LPEGenerator',
    'LPEPreset',
    'get_lpe_generator',
    'STANDARD_AOVS',
    # Linking
    'LightLinker',
    'LinkMode',
    'LinkCollection',
    'LinkRelationship',
    'get_light_linker',
    # Manager
    'AuroraManager',
    'AuroraSession',
    'aurora',
    # Synapse Integration
    'AuroraCommandHandler',
    'AuroraCommandType',
    'get_aurora_command_handler',
    'register_aurora_commands',
]
