"""
Aurora LPE (Light Path Expression) Generation System

Generates comp-ready AOV expressions for Karma/USD workflows.
Supports per-light-group isolation, standard beauty passes, and custom expressions.

LPE Syntax Reference (Karma/PRMan compatible):
- C = Camera ray
- D = Diffuse scattering
- G = Glossy scattering
- S = Specular scattering (mirror)
- T = Transmission
- SS = Subsurface scattering
- O = Emission
- L = Light
- B = Background
- . = Any event
- * = Zero or more events
- + = One or more events
- <RD> = Reflection + Diffuse
- <TD> = Transmission + Diffuse
- 'group:name' = Light group selector
"""

from dataclasses import dataclass
from typing import List, Dict, Optional, Any
from enum import Enum

from .models import (
    LightGroup, AOVDefinition, AOVBundle, AOVType,
    LPEComponent, LightRole
)
from core.determinism import deterministic_uuid


class LPEPreset(Enum):
    """Standard LPE presets"""
    # Beauty components
    DIFFUSE = "C<RD>L"
    DIFFUSE_DIRECT = "C<RD>L"
    DIFFUSE_INDIRECT = "C<RD>.+L"

    SPECULAR = "C<RS>L"
    SPECULAR_DIRECT = "C<RS>L"
    SPECULAR_INDIRECT = "C<RS>.+L"

    GLOSSY = "CG+L"
    GLOSSY_DIRECT = "CGL"
    GLOSSY_INDIRECT = "CG.+L"

    TRANSMISSION = "C<TD>L"
    TRANSMISSION_DIRECT = "C<TD>L"
    TRANSMISSION_INDIRECT = "C<TD>.+L"

    SUBSURFACE = "C<RSS>L"

    EMISSION = "CO"

    # Shadows
    SHADOW = "unshadowed-C<RD>L"  # Requires unshadowed version subtraction

    # Combined
    BEAUTY = "C.*L"
    ALL_DIRECT = "C[DGS]L"
    ALL_INDIRECT = "C[DGS].+L"


# Standard AOV presets for different workflows
STANDARD_AOVS = {
    "beauty": AOVDefinition(
        name="beauty",
        source="Ci",
        description="Final rendered beauty pass"
    ),
    "diffuse": AOVDefinition(
        name="diffuse",
        lpe="C<RD>L",
        description="Direct diffuse illumination"
    ),
    "diffuse_indirect": AOVDefinition(
        name="diffuse_indirect",
        lpe="C<RD>.+L",
        description="Indirect diffuse (GI bounce)"
    ),
    "specular": AOVDefinition(
        name="specular",
        lpe="C<RS>L",
        description="Direct specular highlights"
    ),
    "specular_indirect": AOVDefinition(
        name="specular_indirect",
        lpe="C<RS>.+L",
        description="Indirect specular reflections"
    ),
    "transmission": AOVDefinition(
        name="transmission",
        lpe="C<TD>L",
        description="Direct transmission (glass, etc.)"
    ),
    "subsurface": AOVDefinition(
        name="sss",
        lpe="C<RSS>L",
        description="Subsurface scattering"
    ),
    "emission": AOVDefinition(
        name="emission",
        lpe="CO",
        description="Self-illumination / emission"
    ),
    # Utility AOVs
    "albedo": AOVDefinition(
        name="albedo",
        source="albedo",
        description="Surface albedo color"
    ),
    "N": AOVDefinition(
        name="N",
        source="N",
        aov_type=AOVType.NORMAL3F,
        description="Shading normals"
    ),
    "P": AOVDefinition(
        name="P",
        source="P",
        aov_type=AOVType.POINT3F,
        description="World position"
    ),
    "Z": AOVDefinition(
        name="Z",
        source="z",
        aov_type=AOVType.FLOAT,
        description="Depth"
    ),
    "crypto_object": AOVDefinition(
        name="crypto_object",
        source="CryptoObject",
        description="Cryptomatte object ID"
    ),
    "crypto_material": AOVDefinition(
        name="crypto_material",
        source="CryptoMaterial",
        description="Cryptomatte material ID"
    ),
}


class LPEGenerator:
    """
    Generates LPE expressions and AOV definitions.

    Supports:
    - Per-light-group isolation
    - Standard beauty decomposition
    - Custom LPE authoring
    - Bundle generation for workflows
    """

    def __init__(self):
        self._custom_presets: Dict[str, str] = {}

    def add_preset(self, name: str, lpe: str) -> None:
        """Add custom LPE preset"""
        self._custom_presets[name] = lpe

    def get_preset(self, name: str) -> Optional[str]:
        """Get LPE by preset name"""
        if name in self._custom_presets:
            return self._custom_presets[name]
        try:
            return LPEPreset[name.upper()].value
        except KeyError:
            return None

    # Light group LPE generation

    def light_group_lpe(self, base_lpe: str, light_group: LightGroup) -> str:
        """
        Generate LPE for specific light group.

        Takes a base LPE and constrains it to a light group.
        Example: "C<RD>L" + group "key_lights" -> "C<RD>'lightgroup:key_lights'"
        """
        selector = light_group.get_lpe_light_selector()
        # Replace L (light) with light group selector
        return base_lpe.replace("L", selector)

    def generate_group_aov(
        self,
        light_group: LightGroup,
        component: str,  # "diffuse", "specular", etc.
    ) -> Optional[AOVDefinition]:
        """
        Generate single AOV for light group + component.

        Example: group="key_lights", component="diffuse"
        -> AOV name: "key_lights_diffuse"
        -> LPE: "C<RD>'lightgroup:key_lights'"
        """
        base_lpe = self.get_preset(component)
        if not base_lpe:
            return None

        lpe = self.light_group_lpe(base_lpe, light_group)
        aov_name = f"{light_group.name}_{component}"

        return AOVDefinition(
            name=aov_name,
            lpe=lpe,
            light_group=light_group.name,
            comp_layer_name=aov_name,
            description=f"{component.title()} from {light_group.name} light group"
        )

    def generate_group_aovs(
        self,
        light_group: LightGroup,
    ) -> List[AOVDefinition]:
        """
        Generate all AOVs for a light group based on its settings.

        Respects generate_beauty, generate_diffuse, etc. flags.
        """
        aovs = []

        if light_group.generate_beauty:
            aov = self.generate_group_aov(light_group, "beauty")
            if aov:
                # Beauty uses different LPE
                aov.lpe = f"C.*{light_group.get_lpe_light_selector()}"
                aovs.append(aov)

        if light_group.generate_diffuse:
            aov = self.generate_group_aov(light_group, "diffuse")
            if aov:
                aovs.append(aov)

            # Include indirect if generating diffuse
            aov_indirect = self.generate_group_aov(light_group, "diffuse_indirect")
            if aov_indirect:
                aovs.append(aov_indirect)

        if light_group.generate_specular:
            aov = self.generate_group_aov(light_group, "specular")
            if aov:
                aovs.append(aov)

            aov_indirect = self.generate_group_aov(light_group, "specular_indirect")
            if aov_indirect:
                aovs.append(aov_indirect)

        if light_group.generate_transmission:
            aov = self.generate_group_aov(light_group, "transmission")
            if aov:
                aovs.append(aov)

        return aovs

    # Bundle generation

    def create_comp_basic_bundle(
        self,
        light_groups: Optional[List[LightGroup]] = None,
    ) -> AOVBundle:
        """
        Create basic comp bundle.

        Includes:
        - Beauty
        - Diffuse (direct + indirect)
        - Specular (direct + indirect)
        - Per light group isolation (if groups provided)
        """
        aovs = [
            STANDARD_AOVS["beauty"],
            STANDARD_AOVS["diffuse"],
            STANDARD_AOVS["diffuse_indirect"],
            STANDARD_AOVS["specular"],
            STANDARD_AOVS["specular_indirect"],
            STANDARD_AOVS["Z"],
            STANDARD_AOVS["crypto_object"],
        ]

        # Add per-group AOVs
        if light_groups:
            for group in light_groups:
                aovs.extend(self.generate_group_aovs(group))

        return AOVBundle(
            name="comp_basic",
            description="Basic compositing passes with light group isolation",
            aovs=aovs,
            workflow="comp",
        )

    def create_comp_full_bundle(
        self,
        light_groups: Optional[List[LightGroup]] = None,
    ) -> AOVBundle:
        """
        Create full comp bundle.

        Includes everything in basic plus:
        - SSS
        - Transmission
        - Emission
        - All utility passes
        """
        aovs = [
            STANDARD_AOVS["beauty"],
            STANDARD_AOVS["diffuse"],
            STANDARD_AOVS["diffuse_indirect"],
            STANDARD_AOVS["specular"],
            STANDARD_AOVS["specular_indirect"],
            STANDARD_AOVS["transmission"],
            STANDARD_AOVS["subsurface"],
            STANDARD_AOVS["emission"],
            STANDARD_AOVS["albedo"],
            STANDARD_AOVS["N"],
            STANDARD_AOVS["P"],
            STANDARD_AOVS["Z"],
            STANDARD_AOVS["crypto_object"],
            STANDARD_AOVS["crypto_material"],
        ]

        if light_groups:
            for group in light_groups:
                aovs.extend(self.generate_group_aovs(group))

        return AOVBundle(
            name="comp_full",
            description="Full compositing passes for maximum flexibility",
            aovs=aovs,
            workflow="comp",
        )

    def create_lookdev_bundle(self) -> AOVBundle:
        """
        Create lookdev/lighting preview bundle.

        Minimal passes for fast iteration.
        """
        return AOVBundle(
            name="lookdev",
            description="Fast iteration passes for lookdev",
            aovs=[
                STANDARD_AOVS["beauty"],
                STANDARD_AOVS["diffuse"],
                STANDARD_AOVS["specular"],
                STANDARD_AOVS["albedo"],
            ],
            workflow="lookdev",
        )

    def create_debug_bundle(self) -> AOVBundle:
        """
        Create debug AOV bundle.

        Technical passes for troubleshooting.
        """
        return AOVBundle(
            name="debug",
            description="Technical debug passes",
            aovs=[
                STANDARD_AOVS["N"],
                STANDARD_AOVS["P"],
                STANDARD_AOVS["Z"],
                STANDARD_AOVS["albedo"],
                STANDARD_AOVS["crypto_object"],
                STANDARD_AOVS["crypto_material"],
            ],
            workflow="debug",
        )

    # Role-based auto-grouping

    def suggest_groups_from_lights(
        self,
        light_paths: List[str],
    ) -> Dict[LightRole, List[str]]:
        """
        Analyze light names and suggest role-based grouping.

        Uses naming conventions to infer roles:
        - *key*, *main* -> KEY
        - *fill* -> FILL
        - *rim*, *edge*, *back* -> RIM
        - *bounce* -> BOUNCE
        - *kick* -> KICK
        - *practical*, *lamp*, *fixture* -> PRACTICAL
        - *env*, *dome*, *hdri*, *sky* -> ENVIRONMENT
        """
        suggestions: Dict[LightRole, List[str]] = {role: [] for role in LightRole}

        patterns = {
            LightRole.KEY: ["key", "main", "hero"],
            LightRole.FILL: ["fill", "soft"],
            LightRole.RIM: ["rim", "edge", "back", "hair", "kicker"],
            LightRole.BOUNCE: ["bounce", "gi", "indirect"],
            LightRole.KICK: ["kick"],
            LightRole.PRACTICAL: ["practical", "lamp", "fixture", "neon", "screen"],
            LightRole.ENVIRONMENT: ["env", "dome", "hdri", "sky", "ambient", "ibl"],
            LightRole.SPECULAR: ["spec", "highlight"],
        }

        for path in light_paths:
            name_lower = path.lower()
            matched = False

            for role, keywords in patterns.items():
                if any(kw in name_lower for kw in keywords):
                    suggestions[role].append(path)
                    matched = True
                    break

            if not matched:
                suggestions[LightRole.CUSTOM].append(path)

        # Remove empty groups
        return {k: v for k, v in suggestions.items() if v}

    def create_groups_from_suggestions(
        self,
        suggestions: Dict[LightRole, List[str]],
        light_type_map: Dict[str, str],  # path -> light type
    ) -> List[LightGroup]:
        """
        Create LightGroup objects from role suggestions.

        Args:
            suggestions: Output from suggest_groups_from_lights
            light_type_map: Mapping of prim path to light type string
        """
        from .models import LightType

        groups = []

        role_colors = {
            LightRole.KEY: "#FFD700",      # Gold
            LightRole.FILL: "#87CEEB",     # Sky blue
            LightRole.RIM: "#FF6B6B",      # Coral
            LightRole.BOUNCE: "#98D8C8",   # Mint
            LightRole.KICK: "#F7DC6F",     # Yellow
            LightRole.PRACTICAL: "#BB8FCE", # Purple
            LightRole.ENVIRONMENT: "#85C1E9", # Light blue
            LightRole.SPECULAR: "#F8F8FF",  # Ghost white
            LightRole.CUSTOM: "#808080",    # Gray
        }

        for role, paths in suggestions.items():
            if not paths:
                continue

            group = LightGroup(
                name=f"{role.value}_lights",
                role=role,
                color_tag=role_colors.get(role, "#808080"),
                description=f"Auto-generated {role.value} light group",
            )

            for path in paths:
                light_type_str = light_type_map.get(path, "RectLight")
                try:
                    light_type = LightType(light_type_str)
                except ValueError:
                    light_type = LightType.RECT

                group.add_light(path, light_type)

            groups.append(group)

        return groups


# Module-level generator instance
_generator: Optional[LPEGenerator] = None


def get_lpe_generator() -> LPEGenerator:
    """Get singleton LPE generator"""
    global _generator
    if _generator is None:
        _generator = LPEGenerator()
    return _generator
