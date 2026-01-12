"""
Aurora Light Linking System

Manages light-to-geometry relationships for USD/Solaris workflows.
Handles both illumination linking and shadow linking with pattern-based rules.

USD Light Linking Concepts:
- Collection-based: Lights have collections defining what they illuminate
- includeRoot/excludeRoot: Base include/exclude behavior
- Expansion rules: How patterns are resolved
"""

from dataclasses import dataclass, field
from typing import List, Dict, Set, Optional, Any, Tuple
from enum import Enum
import fnmatch
import re

from .models import LightLinkRule, LightGroup, LightGroupMember
from core.determinism import deterministic_uuid, deterministic_sort
from core.audit import audit_log, AuditCategory, AuditLevel


class LinkMode(Enum):
    """How linking is applied"""
    INCLUDE_ALL_EXCLUDE_LISTED = "include_all"  # Default lit, rules exclude
    EXCLUDE_ALL_INCLUDE_LISTED = "exclude_all"  # Default dark, rules include


@dataclass
class LinkRelationship:
    """A resolved light-geometry linking relationship"""
    light_path: str
    geometry_path: str
    illumination: bool = True
    shadow: bool = True
    rule_source: str = ""  # Which rule created this

    def to_dict(self) -> Dict[str, Any]:
        return {
            "light_path": self.light_path,
            "geometry_path": self.geometry_path,
            "illumination": self.illumination,
            "shadow": self.shadow,
            "rule_source": self.rule_source,
        }


@dataclass
class LinkCollection:
    """
    USD-style collection for light linking.

    Mirrors USD collection semantics:
    - includes: Paths/patterns to include
    - excludes: Paths/patterns to exclude
    - expansionRule: How to expand patterns
    """
    name: str
    light_path: str  # Light this collection belongs to

    includes: List[str] = field(default_factory=list)
    excludes: List[str] = field(default_factory=list)

    expansion_rule: str = "expandPrims"  # expandPrims, explicitOnly

    collection_id: str = ""

    def __post_init__(self):
        if not self.collection_id:
            content = f"{self.light_path}:{self.name}"
            self.collection_id = deterministic_uuid(content, "collection")

    def matches(self, prim_path: str) -> bool:
        """Check if prim matches this collection"""
        # Check excludes first (higher priority)
        for pattern in self.excludes:
            if self._path_matches(prim_path, pattern):
                return False

        # Then check includes
        for pattern in self.includes:
            if self._path_matches(prim_path, pattern):
                return True

        return False

    def _path_matches(self, path: str, pattern: str) -> bool:
        """Match path against pattern (supports glob and descendants)"""
        # Exact match
        if path == pattern:
            return True

        # Descendant match (pattern ends with /*)
        if pattern.endswith("/*"):
            base = pattern[:-2]
            if path.startswith(base + "/"):
                return True

        # Glob pattern match
        if "*" in pattern or "?" in pattern:
            if fnmatch.fnmatch(path, pattern):
                return True

        return False

    def to_usd_dict(self) -> Dict[str, Any]:
        """Convert to USD-compatible dictionary"""
        return {
            "includes": self.includes,
            "excludes": self.excludes,
            "expansionRule": self.expansion_rule,
        }


class LightLinker:
    """
    Manages light linking rules and resolves relationships.

    Workflow:
    1. Define rules (patterns matching lights to geometry)
    2. Resolve rules against actual scene paths
    3. Generate USD collections for rendering
    """

    def __init__(self):
        self._rules: Dict[str, LightLinkRule] = {}  # rule_id -> rule
        self._mode = LinkMode.INCLUDE_ALL_EXCLUDE_LISTED
        self._resolved_cache: Dict[str, List[LinkRelationship]] = {}
        self._dirty = True

    @property
    def mode(self) -> LinkMode:
        return self._mode

    @mode.setter
    def mode(self, value: LinkMode) -> None:
        self._mode = value
        self._dirty = True

    def add_rule(self, rule: LightLinkRule) -> None:
        """Add linking rule"""
        self._rules[rule.rule_id] = rule
        self._dirty = True

        audit_log().log(
            operation="add_link_rule",
            message=f"Added light link rule: {rule.name}",
            level=AuditLevel.INFO,
            category=AuditCategory.LIGHTING,
            input_data=rule.to_dict(),
        )

    def remove_rule(self, rule_id: str) -> bool:
        """Remove linking rule"""
        if rule_id in self._rules:
            rule = self._rules.pop(rule_id)
            self._dirty = True

            audit_log().log(
                operation="remove_link_rule",
                message=f"Removed light link rule: {rule.name}",
                level=AuditLevel.INFO,
                category=AuditCategory.LIGHTING,
            )
            return True
        return False

    def get_rules(self) -> List[LightLinkRule]:
        """Get all rules sorted by priority"""
        rules = list(self._rules.values())
        return sorted(rules, key=lambda r: (-r.priority, r.name))

    def create_rule(
        self,
        name: str,
        light_pattern: str,
        geometry_pattern: str,
        illumination: bool = True,
        shadow: bool = True,
        include: bool = True,
        priority: int = 0,
        description: str = "",
    ) -> LightLinkRule:
        """Create and add a new rule"""
        rule = LightLinkRule(
            name=name,
            light_pattern=light_pattern,
            geometry_pattern=geometry_pattern,
            illumination=illumination,
            shadow=shadow,
            include=include,
            priority=priority,
            description=description,
        )
        self.add_rule(rule)
        return rule

    # Common rule presets

    def exclude_from_light(
        self,
        light_path: str,
        geometry_pattern: str,
        name: Optional[str] = None,
    ) -> LightLinkRule:
        """Quick rule to exclude geometry from a light"""
        rule_name = name or f"exclude_{light_path.split('/')[-1]}"
        return self.create_rule(
            name=rule_name,
            light_pattern=light_path,
            geometry_pattern=geometry_pattern,
            include=False,
            description=f"Exclude {geometry_pattern} from {light_path}",
        )

    def light_only_affects(
        self,
        light_path: str,
        geometry_pattern: str,
        name: Optional[str] = None,
    ) -> LightLinkRule:
        """Quick rule for light to only affect specific geometry"""
        rule_name = name or f"only_{light_path.split('/')[-1]}"
        return self.create_rule(
            name=rule_name,
            light_pattern=light_path,
            geometry_pattern=geometry_pattern,
            include=True,
            priority=100,  # High priority to override defaults
            description=f"{light_path} only affects {geometry_pattern}",
        )

    def shadow_catcher(
        self,
        geometry_pattern: str,
        light_pattern: str = "*",
        name: Optional[str] = None,
    ) -> LightLinkRule:
        """Create shadow catcher rule (receives shadows but not illumination)"""
        rule_name = name or "shadow_catcher"
        return self.create_rule(
            name=rule_name,
            light_pattern=light_pattern,
            geometry_pattern=geometry_pattern,
            illumination=False,
            shadow=True,
            include=True,
            description=f"Shadow catcher for {geometry_pattern}",
        )

    # Resolution

    def resolve(
        self,
        light_paths: List[str],
        geometry_paths: List[str],
    ) -> List[LinkRelationship]:
        """
        Resolve all rules against actual scene paths.

        Returns list of LinkRelationship objects defining all light-geo pairs.
        """
        relationships = []

        # Sort for determinism
        light_paths = deterministic_sort(light_paths)
        geometry_paths = deterministic_sort(geometry_paths)

        # Get rules sorted by priority
        rules = self.get_rules()

        for light_path in light_paths:
            for geo_path in geometry_paths:
                relationship = self._resolve_pair(
                    light_path, geo_path, rules
                )
                if relationship:
                    relationships.append(relationship)

        self._dirty = False
        return relationships

    def _resolve_pair(
        self,
        light_path: str,
        geo_path: str,
        rules: List[LightLinkRule],
    ) -> Optional[LinkRelationship]:
        """Resolve linking for a single light-geometry pair"""
        # Start with defaults based on mode
        if self._mode == LinkMode.INCLUDE_ALL_EXCLUDE_LISTED:
            illumination = True
            shadow = True
        else:
            illumination = False
            shadow = False

        matched_rule = None

        # Apply rules in priority order
        for rule in rules:
            if self._matches_pattern(light_path, rule.light_pattern) and \
               self._matches_pattern(geo_path, rule.geometry_pattern):

                if rule.include:
                    illumination = rule.illumination
                    shadow = rule.shadow
                else:
                    if rule.illumination:
                        illumination = False
                    if rule.shadow:
                        shadow = False

                matched_rule = rule.name

        # Only return if there's a meaningful relationship
        if illumination or shadow:
            return LinkRelationship(
                light_path=light_path,
                geometry_path=geo_path,
                illumination=illumination,
                shadow=shadow,
                rule_source=matched_rule or "default",
            )

        return None

    def _matches_pattern(self, path: str, pattern: str) -> bool:
        """Check if path matches pattern"""
        if pattern == "*":
            return True

        # Exact match
        if path == pattern:
            return True

        # Glob pattern
        if "*" in pattern or "?" in pattern:
            return fnmatch.fnmatch(path, pattern)

        # Prefix match (for hierarchy patterns)
        if pattern.endswith("/"):
            return path.startswith(pattern)

        return False

    # USD Collection Generation

    def generate_collections(
        self,
        light_paths: List[str],
        geometry_paths: List[str],
    ) -> Dict[str, LinkCollection]:
        """
        Generate USD light linking collections.

        Returns dict of light_path -> LinkCollection
        """
        relationships = self.resolve(light_paths, geometry_paths)
        collections: Dict[str, LinkCollection] = {}

        # Group relationships by light
        by_light: Dict[str, List[LinkRelationship]] = {}
        for rel in relationships:
            if rel.light_path not in by_light:
                by_light[rel.light_path] = []
            by_light[rel.light_path].append(rel)

        # Generate collection for each light
        for light_path in deterministic_sort(light_paths):
            rels = by_light.get(light_path, [])

            # Determine includes/excludes based on mode
            if self._mode == LinkMode.INCLUDE_ALL_EXCLUDE_LISTED:
                # Start with all, add excludes
                includes = ["/*"]  # Root wildcard
                excludes = [
                    r.geometry_path for r in rels
                    if not r.illumination
                ]
            else:
                # Start with none, add includes
                includes = [r.geometry_path for r in rels if r.illumination]
                excludes = []

            collection = LinkCollection(
                name="lightLink",
                light_path=light_path,
                includes=deterministic_sort(includes),
                excludes=deterministic_sort(excludes),
            )
            collections[light_path] = collection

        return collections

    def generate_shadow_collections(
        self,
        light_paths: List[str],
        geometry_paths: List[str],
    ) -> Dict[str, LinkCollection]:
        """
        Generate USD shadow linking collections.

        Separate from light linking - controls shadow casting.
        """
        relationships = self.resolve(light_paths, geometry_paths)
        collections: Dict[str, LinkCollection] = {}

        by_light: Dict[str, List[LinkRelationship]] = {}
        for rel in relationships:
            if rel.light_path not in by_light:
                by_light[rel.light_path] = []
            by_light[rel.light_path].append(rel)

        for light_path in deterministic_sort(light_paths):
            rels = by_light.get(light_path, [])

            if self._mode == LinkMode.INCLUDE_ALL_EXCLUDE_LISTED:
                includes = ["/*"]
                excludes = [r.geometry_path for r in rels if not r.shadow]
            else:
                includes = [r.geometry_path for r in rels if r.shadow]
                excludes = []

            collection = LinkCollection(
                name="shadowLink",
                light_path=light_path,
                includes=deterministic_sort(includes),
                excludes=deterministic_sort(excludes),
            )
            collections[light_path] = collection

        return collections

    # Light Group Integration

    def link_group_to_geometry(
        self,
        light_group: LightGroup,
        geometry_pattern: str,
        illumination: bool = True,
        shadow: bool = True,
    ) -> List[LightLinkRule]:
        """
        Create linking rules for all lights in a group to geometry.

        Returns list of created rules.
        """
        rules = []

        for member in light_group.members:
            if not member.enabled:
                continue

            rule = self.create_rule(
                name=f"{light_group.name}_to_{geometry_pattern.replace('/', '_')}",
                light_pattern=member.prim_path,
                geometry_pattern=geometry_pattern,
                illumination=illumination,
                shadow=shadow,
                include=True,
                description=f"Link {light_group.name} group to {geometry_pattern}",
            )
            rules.append(rule)

        return rules

    def exclude_group_from_geometry(
        self,
        light_group: LightGroup,
        geometry_pattern: str,
    ) -> List[LightLinkRule]:
        """Exclude entire light group from geometry"""
        rules = []

        for member in light_group.members:
            if not member.enabled:
                continue

            rule = self.exclude_from_light(
                light_path=member.prim_path,
                geometry_pattern=geometry_pattern,
                name=f"exclude_{light_group.name}_from_{geometry_pattern.replace('/', '_')}",
            )
            rules.append(rule)

        return rules

    # Serialization

    def to_dict(self) -> Dict[str, Any]:
        """Serialize linker state"""
        return {
            "mode": self._mode.value,
            "rules": [r.to_dict() for r in self._rules.values()],
        }

    def from_dict(self, data: Dict[str, Any]) -> None:
        """Load linker state"""
        self._mode = LinkMode(data.get("mode", "include_all"))
        self._rules.clear()

        for rule_data in data.get("rules", []):
            rule = LightLinkRule.from_dict(rule_data)
            self._rules[rule.rule_id] = rule

        self._dirty = True

    def clear(self) -> None:
        """Clear all rules"""
        self._rules.clear()
        self._dirty = True


# Module-level instance
_linker: Optional[LightLinker] = None


def get_light_linker() -> LightLinker:
    """Get singleton light linker"""
    global _linker
    if _linker is None:
        _linker = LightLinker()
    return _linker
