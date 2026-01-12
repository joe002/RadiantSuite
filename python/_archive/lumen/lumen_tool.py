"""
╔═══════════════════════════════════════════════════════════════════════════════╗
║                                                                               ║
║   ██╗     ██╗   ██╗███╗   ███╗███████╗███╗   ██╗                              ║
║   ██║     ██║   ██║████╗ ████║██╔════╝████╗  ██║                              ║
║   ██║     ██║   ██║██╔████╔██║█████╗  ██╔██╗ ██║                              ║
║   ██║     ██║   ██║██║╚██╔╝██║██╔══╝  ██║╚██╗██║                              ║
║   ███████╗╚██████╔╝██║ ╚═╝ ██║███████╗██║ ╚████║                              ║
║   ╚══════╝ ╚═════╝ ╚═╝     ╚═╝╚══════╝╚═╝  ╚═══╝                              ║
║                                                                               ║
║   Lighting Rig Manager for Houdini 21                                         ║
║   Professional lighting setups, instantly.                                    ║
║                                                                               ║
╚═══════════════════════════════════════════════════════════════════════════════╝

Lumen v2.1.0 | Houdini 21+ | Python 3.9+

Complete lighting rig management for Solaris/USD workflows.
Create, save, and deploy professional lighting setups in seconds.

FEATURES:
• Correct Dome Light handling (dedicated LOP, not Light type)
• USD API direct access for H21 stability
• Built-in professional presets (Three-Point, Studio HDRI, Product)
• Color temperature to RGB conversion
• Thread-safe preset operations
• Schema versioning for team sharing

USAGE:
    from lumen import create_panel
    panel = create_panel()

LICENSE: MIT
AUTHOR: Joe Ibrahim
WEBSITE: https://github.com/yourusername/lumen
"""

__title__ = "Lumen"
__version__ = "2.1.0"
__author__ = "Joe Ibrahim"
__license__ = "MIT"
__product__ = "Lumen - Lighting Rig Manager"

import hou
import math
import json
import threading
import traceback
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass, field, asdict
from enum import Enum
from PySide6 import QtWidgets, QtCore, QtGui

SCHEMA_VERSION = "2.1.0"


# =============================================================================
# ENUMS
# =============================================================================

class LightType(Enum):
    """USD Light types - FIXED: Dome uses dedicated LOP"""
    POINT = "point"
    DISTANT = "distant"
    DISK = "disk"
    RECT = "rect"
    SPHERE = "sphere"
    CYLINDER = "cylinder"
    GEOMETRY = "geometry"
    DOME = "dome"
    PORTAL = "portal"


# CRITICAL: Mapping from LightType to actual Houdini LOP node type
LIGHT_TYPE_TO_LOP_NODE = {
    LightType.POINT: ("light", "point"),
    LightType.DISTANT: ("light", "distant"),
    LightType.DISK: ("light", "disk"),
    LightType.RECT: ("light", "rect"),
    LightType.SPHERE: ("light", "sphere"),
    LightType.CYLINDER: ("light", "cylinder"),
    LightType.GEOMETRY: ("light", "geometry"),
    LightType.DOME: ("domelight", None),      # Separate LOP!
    LightType.PORTAL: ("portallight", None),  # Separate LOP!
}


class LightRole(Enum):
    KEY = "key"
    FILL = "fill"
    RIM = "rim"
    BOUNCE = "bounce"
    PRACTICAL = "practical"
    AMBIENT = "ambient"
    ACCENT = "accent"
    CUSTOM = "custom"


class Renderer(Enum):
    KARMA = "karma"
    ARNOLD = "arnold"
    RENDERMAN = "renderman"
    REDSHIFT = "redshift"
    VRAY = "vray"


# =============================================================================
# COLOR TEMPERATURE
# =============================================================================

class ColorTemperature:
    PRESETS = {
        "candle": 1900, "tungsten_40w": 2600, "tungsten_100w": 2850,
        "halogen": 3200, "fluorescent_warm": 3000, "fluorescent_cool": 4100,
        "daylight": 5600, "cloudy": 6500, "shade": 7500, "blue_sky": 10000,
    }
    
    @classmethod
    def kelvin_to_rgb(cls, kelvin: float) -> Tuple[float, float, float]:
        kelvin = max(1000, min(40000, kelvin))
        temp = kelvin / 100.0
        
        if temp <= 66:
            red = 1.0
        else:
            red = temp - 60
            red = 329.698727446 * (red ** -0.1332047592)
            red = max(0, min(255, red)) / 255.0
        
        if temp <= 66:
            green = temp
            green = 99.4708025861 * math.log(green) - 161.1195681661
            green = max(0, min(255, green)) / 255.0
        else:
            green = temp - 60
            green = 288.1221695283 * (green ** -0.0755148492)
            green = max(0, min(255, green)) / 255.0
        
        if temp >= 66:
            blue = 1.0
        elif temp <= 19:
            blue = 0.0
        else:
            blue = temp - 10
            blue = 138.5177312231 * math.log(blue) - 305.0447927307
            blue = max(0, min(255, blue)) / 255.0
        
        return (red, green, blue)


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class LightTransform:
    position: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    rotation: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    scale: Tuple[float, float, float] = (1.0, 1.0, 1.0)
    
    def to_dict(self) -> Dict:
        return {"position": list(self.position), "rotation": list(self.rotation), "scale": list(self.scale)}
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'LightTransform':
        return cls(
            position=tuple(data.get("position", [0, 0, 0])),
            rotation=tuple(data.get("rotation", [0, 0, 0])),
            scale=tuple(data.get("scale", [1, 1, 1]))
        )


@dataclass
class LightSettings:
    name: str
    light_type: LightType
    role: LightRole = LightRole.CUSTOM
    
    intensity: float = 1.0
    exposure: float = 0.0
    color: Tuple[float, float, float] = (1.0, 1.0, 1.0)
    temperature: Optional[float] = None
    normalize: bool = True
    
    transform: LightTransform = field(default_factory=LightTransform)
    
    width: float = 1.0
    height: float = 1.0
    radius: float = 0.5
    length: float = 1.0
    
    shadow_enable: bool = True
    shadow_color: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    shadow_intensity: float = 1.0
    
    visible: bool = False
    contribution: float = 1.0
    
    texture_path: str = ""
    
    enabled: bool = True
    notes: str = ""
    
    def __post_init__(self):
        if not self.name:
            raise ValueError("Light name cannot be empty")
        if self.intensity < 0:
            raise ValueError("Intensity cannot be negative")
    
    def get_effective_color(self) -> Tuple[float, float, float]:
        if self.temperature is not None:
            return ColorTemperature.kelvin_to_rgb(self.temperature)
        return self.color
    
    def to_dict(self) -> Dict:
        return {
            "name": self.name, "light_type": self.light_type.value, "role": self.role.value,
            "intensity": self.intensity, "exposure": self.exposure, "color": list(self.color),
            "temperature": self.temperature, "normalize": self.normalize,
            "transform": self.transform.to_dict(),
            "width": self.width, "height": self.height, "radius": self.radius, "length": self.length,
            "shadow_enable": self.shadow_enable, "shadow_color": list(self.shadow_color),
            "shadow_intensity": self.shadow_intensity, "visible": self.visible,
            "contribution": self.contribution, "texture_path": self.texture_path,
            "enabled": self.enabled, "notes": self.notes
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'LightSettings':
        data["light_type"] = LightType(data["light_type"])
        data["role"] = LightRole(data.get("role", "custom"))
        if "transform" in data:
            data["transform"] = LightTransform.from_dict(data["transform"])
        data["color"] = tuple(data.get("color", [1, 1, 1]))
        data["shadow_color"] = tuple(data.get("shadow_color", [0, 0, 0]))
        return cls(**data)


@dataclass
class LightRig:
    name: str
    lights: List[LightSettings] = field(default_factory=list)
    renderer: Renderer = Renderer.KARMA
    notes: str = ""
    created_at: str = ""
    modified_at: str = ""
    tags: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict:
        return {
            "_schema_version": SCHEMA_VERSION, "_product": __product__,
            "name": self.name, "lights": [l.to_dict() for l in self.lights],
            "renderer": self.renderer.value, "notes": self.notes,
            "created_at": self.created_at, "modified_at": self.modified_at, "tags": self.tags
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'LightRig':
        data.pop("_schema_version", None)
        data.pop("_product", None)
        data["lights"] = [LightSettings.from_dict(l) for l in data.get("lights", [])]
        data["renderer"] = Renderer(data.get("renderer", "karma"))
        return cls(**data)


# =============================================================================
# SOLARIS LIGHT FACTORY
# =============================================================================

class SolarisLightFactory:
    """Factory for creating USD lights - uses correct LOP nodes"""
    
    @staticmethod
    def create_light(parent: hou.Node, settings: LightSettings, prim_path: str = None) -> Optional[hou.LopNode]:
        try:
            node_type, type_param = LIGHT_TYPE_TO_LOP_NODE.get(settings.light_type, ("light", "point"))
            
            light_node = parent.createNode(node_type, settings.name)
            
            if type_param and light_node.parm("type"):
                light_node.parm("type").set(type_param)
            
            if prim_path and light_node.parm("primpath"):
                light_node.parm("primpath").set(prim_path)
            
            SolarisLightFactory._apply_settings(light_node, settings)
            light_node.moveToGoodPosition()
            return light_node
            
        except Exception as e:
            print(f"[Lumen] Failed to create light: {e}")
            traceback.print_exc()
            return None
    
    @staticmethod
    def _apply_settings(light_node: hou.LopNode, settings: LightSettings):
        if light_node.parm("intensity"):
            light_node.parm("intensity").set(settings.intensity)
        
        if light_node.parm("exposure"):
            light_node.parm("exposure").set(settings.exposure)
        
        color = settings.get_effective_color()
        if light_node.parm("light_colorr"):
            light_node.parm("light_colorr").set(color[0])
            light_node.parm("light_colorg").set(color[1])
            light_node.parm("light_colorb").set(color[2])
        elif light_node.parmTuple("light_color"):
            light_node.parmTuple("light_color").set(color)
        
        if light_node.parm("normalize"):
            light_node.parm("normalize").set(settings.normalize)
        
        if light_node.parm("shadow_enable"):
            light_node.parm("shadow_enable").set(settings.shadow_enable)
        
        lt = settings.light_type
        if lt in [LightType.RECT]:
            if light_node.parm("width"):
                light_node.parm("width").set(settings.width)
            if light_node.parm("height"):
                light_node.parm("height").set(settings.height)
        
        if lt in [LightType.DISK, LightType.SPHERE]:
            if light_node.parm("radius"):
                light_node.parm("radius").set(settings.radius)
        
        if lt == LightType.CYLINDER:
            if light_node.parm("radius"):
                light_node.parm("radius").set(settings.radius)
            if light_node.parm("length"):
                light_node.parm("length").set(settings.length)
        
        if lt == LightType.DOME and settings.texture_path:
            if light_node.parm("texture"):
                light_node.parm("texture").set(settings.texture_path)
        
        t = settings.transform
        if light_node.parmTuple("t"):
            light_node.parmTuple("t").set(t.position)
        if light_node.parmTuple("r"):
            light_node.parmTuple("r").set(t.rotation)
        if light_node.parmTuple("s"):
            light_node.parmTuple("s").set(t.scale)


# =============================================================================
# RIG MANAGER
# =============================================================================

class LumenRigManager:
    PRESET_DIR = Path(hou.expandString("$HOUDINI_USER_PREF_DIR")) / "lumen_rigs"
    
    def __init__(self):
        self._rigs: Dict[str, LightRig] = {}
        self._lock = threading.RLock()
        self._ensure_dir()
        self._load_rigs()
        self._load_builtin_presets()
    
    def _ensure_dir(self):
        try:
            self.PRESET_DIR.mkdir(parents=True, exist_ok=True)
        except:
            pass
    
    def _load_rigs(self):
        rig_file = self.PRESET_DIR / "rigs.json"
        if not rig_file.exists():
            return
        
        with self._lock:
            try:
                with open(rig_file, 'r') as f:
                    data = json.load(f)
                
                rigs_data = data.get("_rigs", data)
                for name, r_data in rigs_data.items():
                    if name.startswith("_"):
                        continue
                    try:
                        self._rigs[name] = LightRig.from_dict(r_data)
                    except Exception as e:
                        print(f"[Lumen] Warning: Could not load '{name}': {e}")
            except Exception as e:
                print(f"[Lumen] Error loading rigs: {e}")
    
    def _save_rigs(self):
        rig_file = self.PRESET_DIR / "rigs.json"
        
        with self._lock:
            try:
                import datetime
                data = {
                    "_schema_version": SCHEMA_VERSION,
                    "_product": __product__,
                    "_saved_at": datetime.datetime.now().isoformat(),
                    "_rigs": {name: rig.to_dict() for name, rig in self._rigs.items()}
                }
                with open(rig_file, 'w') as f:
                    json.dump(data, f, indent=2)
            except Exception as e:
                print(f"[Lumen] Error saving: {e}")
    
    def _load_builtin_presets(self):
        for rig in self._get_builtin_presets():
            if rig.name not in self._rigs:
                self._rigs[rig.name] = rig
    
    def _get_builtin_presets(self) -> List[LightRig]:
        return [
            LightRig(
                name="Three Point Basic",
                lights=[
                    LightSettings(name="key_light", light_type=LightType.RECT, role=LightRole.KEY,
                                 intensity=1.5, temperature=5600,
                                 transform=LightTransform(position=(3.0, 4.0, 3.0), rotation=(-45.0, 45.0, 0.0)),
                                 width=2.0, height=2.0),
                    LightSettings(name="fill_light", light_type=LightType.RECT, role=LightRole.FILL,
                                 intensity=0.5, temperature=6500,
                                 transform=LightTransform(position=(-3.0, 2.0, 2.0), rotation=(-30.0, -45.0, 0.0)),
                                 width=3.0, height=3.0),
                    LightSettings(name="rim_light", light_type=LightType.RECT, role=LightRole.RIM,
                                 intensity=0.8, temperature=7500,
                                 transform=LightTransform(position=(0.0, 3.0, -4.0), rotation=(45.0, 180.0, 0.0)),
                                 width=1.5, height=1.5),
                ],
                notes="Classic three-point lighting"
            ),
            LightRig(
                name="Studio HDRI",
                lights=[
                    LightSettings(name="dome_light", light_type=LightType.DOME, role=LightRole.AMBIENT,
                                 intensity=1.0, texture_path="$HFS/houdini/pic/hdri/HDRIHaven_studio_small_03_1k.rat"),
                    LightSettings(name="key_accent", light_type=LightType.RECT, role=LightRole.KEY,
                                 intensity=0.8, temperature=5600,
                                 transform=LightTransform(position=(2.0, 3.0, 2.0), rotation=(-40.0, 40.0, 0.0)),
                                 width=1.5, height=1.5),
                ],
                notes="HDRI dome with accent key"
            ),
            LightRig(
                name="Product Shot",
                lights=[
                    LightSettings(name="main_soft", light_type=LightType.RECT, role=LightRole.KEY,
                                 intensity=2.0, temperature=5600,
                                 transform=LightTransform(position=(0.0, 5.0, 3.0), rotation=(-60.0, 0.0, 0.0)),
                                 width=4.0, height=4.0),
                    LightSettings(name="side_fill_left", light_type=LightType.RECT, role=LightRole.FILL,
                                 intensity=0.6,
                                 transform=LightTransform(position=(-3.0, 2.0, 0.0), rotation=(0.0, -90.0, 0.0)),
                                 width=2.0, height=3.0),
                    LightSettings(name="side_fill_right", light_type=LightType.RECT, role=LightRole.FILL,
                                 intensity=0.6,
                                 transform=LightTransform(position=(3.0, 2.0, 0.0), rotation=(0.0, 90.0, 0.0)),
                                 width=2.0, height=3.0),
                    LightSettings(name="back_rim", light_type=LightType.RECT, role=LightRole.RIM,
                                 intensity=1.2, temperature=7000,
                                 transform=LightTransform(position=(0.0, 2.0, -3.0), rotation=(30.0, 180.0, 0.0)),
                                 width=3.0, height=2.0),
                ],
                notes="Soft product photography lighting"
            ),
        ]
    
    @property
    def rigs(self) -> Dict[str, LightRig]:
        with self._lock:
            return dict(self._rigs)
    
    def get_rig(self, name: str) -> Optional[LightRig]:
        with self._lock:
            return self._rigs.get(name)
    
    def create_rig(self, rig: LightRig) -> Tuple[bool, str]:
        with self._lock:
            import datetime
            rig.created_at = datetime.datetime.now().isoformat()
            rig.modified_at = rig.created_at
            self._rigs[rig.name] = rig
            self._save_rigs()
        return True, f"Created: {rig.name}"
    
    def update_rig(self, name: str, rig: LightRig) -> Tuple[bool, str]:
        with self._lock:
            if name not in self._rigs:
                return False, f"Not found: {name}"
            import datetime
            rig.modified_at = datetime.datetime.now().isoformat()
            rig.created_at = self._rigs[name].created_at
            if name != rig.name:
                del self._rigs[name]
            self._rigs[rig.name] = rig
            self._save_rigs()
        return True, f"Updated: {rig.name}"
    
    def delete_rig(self, name: str) -> Tuple[bool, str]:
        with self._lock:
            if name not in self._rigs:
                return False, f"Not found: {name}"
            del self._rigs[name]
            self._save_rigs()
        return True, f"Deleted: {name}"
    
    def build_rig_in_solaris(self, rig_name: str, parent_path: str = "/stage", lights_root: str = "/lights") -> Tuple[bool, str, List[hou.Node]]:
        rig = self.get_rig(rig_name)
        if not rig:
            return False, f"Rig not found: {rig_name}", []
        
        parent = hou.node(parent_path)
        if not parent:
            parent = hou.node("/").createNode("lopnet", "stage")
        
        created_nodes: List[hou.Node] = []
        
        try:
            for light in rig.lights:
                if not light.enabled:
                    continue
                
                prim_path = f"{lights_root}/{light.name}"
                node = SolarisLightFactory.create_light(parent, light, prim_path)
                if node:
                    created_nodes.append(node)
            
            if len(created_nodes) > 1:
                merge = parent.createNode("merge", f"merge_{rig_name}")
                for i, node in enumerate(created_nodes):
                    merge.setInput(i, node)
                merge.moveToGoodPosition()
                created_nodes.append(merge)
            
            if created_nodes:
                box = parent.createNetworkBox(rig_name)
                box.setComment(f"Lumen Rig: {rig_name}\n{rig.notes}")
                for node in created_nodes:
                    box.addNode(node)
                box.fitAroundContents()
            
            return True, f"Built {len(rig.lights)} lights", created_nodes
            
        except Exception as e:
            traceback.print_exc()
            return False, f"Error: {e}", created_nodes


# =============================================================================
# QT PANEL
# =============================================================================

class LightEditorWidget(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()
    
    def _init_ui(self):
        layout = QtWidgets.QFormLayout(self)
        
        self.name_edit = QtWidgets.QLineEdit()
        layout.addRow("Name:", self.name_edit)
        
        self.type_combo = QtWidgets.QComboBox()
        for lt in LightType:
            self.type_combo.addItem(lt.value.title(), lt)
        layout.addRow("Type:", self.type_combo)
        
        self.role_combo = QtWidgets.QComboBox()
        for role in LightRole:
            self.role_combo.addItem(role.value.title(), role)
        layout.addRow("Role:", self.role_combo)
        
        self.intensity = QtWidgets.QDoubleSpinBox()
        self.intensity.setRange(0, 100)
        self.intensity.setValue(1.0)
        self.intensity.setSingleStep(0.1)
        layout.addRow("Intensity:", self.intensity)
        
        self.exposure = QtWidgets.QDoubleSpinBox()
        self.exposure.setRange(-20, 20)
        layout.addRow("Exposure:", self.exposure)
        
        temp_layout = QtWidgets.QHBoxLayout()
        self.use_temp = QtWidgets.QCheckBox("Temperature")
        temp_layout.addWidget(self.use_temp)
        self.temp = QtWidgets.QSpinBox()
        self.temp.setRange(1000, 20000)
        self.temp.setValue(5600)
        self.temp.setSuffix(" K")
        self.temp.setEnabled(False)
        temp_layout.addWidget(self.temp)
        layout.addRow("", temp_layout)
        self.use_temp.toggled.connect(self.temp.setEnabled)
        
        color_layout = QtWidgets.QHBoxLayout()
        self.color_r = QtWidgets.QDoubleSpinBox()
        self.color_r.setRange(0, 1)
        self.color_r.setValue(1.0)
        self.color_r.setSingleStep(0.1)
        color_layout.addWidget(self.color_r)
        self.color_g = QtWidgets.QDoubleSpinBox()
        self.color_g.setRange(0, 1)
        self.color_g.setValue(1.0)
        self.color_g.setSingleStep(0.1)
        color_layout.addWidget(self.color_g)
        self.color_b = QtWidgets.QDoubleSpinBox()
        self.color_b.setRange(0, 1)
        self.color_b.setValue(1.0)
        self.color_b.setSingleStep(0.1)
        color_layout.addWidget(self.color_b)
        layout.addRow("Color:", color_layout)
        
        pos_layout = QtWidgets.QHBoxLayout()
        self.pos_x = QtWidgets.QDoubleSpinBox()
        self.pos_x.setRange(-1000, 1000)
        pos_layout.addWidget(self.pos_x)
        self.pos_y = QtWidgets.QDoubleSpinBox()
        self.pos_y.setRange(-1000, 1000)
        pos_layout.addWidget(self.pos_y)
        self.pos_z = QtWidgets.QDoubleSpinBox()
        self.pos_z.setRange(-1000, 1000)
        pos_layout.addWidget(self.pos_z)
        layout.addRow("Position:", pos_layout)
        
        rot_layout = QtWidgets.QHBoxLayout()
        self.rot_x = QtWidgets.QDoubleSpinBox()
        self.rot_x.setRange(-360, 360)
        rot_layout.addWidget(self.rot_x)
        self.rot_y = QtWidgets.QDoubleSpinBox()
        self.rot_y.setRange(-360, 360)
        rot_layout.addWidget(self.rot_y)
        self.rot_z = QtWidgets.QDoubleSpinBox()
        self.rot_z.setRange(-360, 360)
        rot_layout.addWidget(self.rot_z)
        layout.addRow("Rotation:", rot_layout)
        
        size_layout = QtWidgets.QHBoxLayout()
        self.width = QtWidgets.QDoubleSpinBox()
        self.width.setRange(0.01, 100)
        self.width.setValue(1.0)
        size_layout.addWidget(QtWidgets.QLabel("W:"))
        size_layout.addWidget(self.width)
        self.height = QtWidgets.QDoubleSpinBox()
        self.height.setRange(0.01, 100)
        self.height.setValue(1.0)
        size_layout.addWidget(QtWidgets.QLabel("H:"))
        size_layout.addWidget(self.height)
        self.radius = QtWidgets.QDoubleSpinBox()
        self.radius.setRange(0.01, 100)
        self.radius.setValue(0.5)
        size_layout.addWidget(QtWidgets.QLabel("R:"))
        size_layout.addWidget(self.radius)
        layout.addRow("Size:", size_layout)
        
        self.shadow = QtWidgets.QCheckBox("Enable Shadows")
        self.shadow.setChecked(True)
        layout.addRow("", self.shadow)
        
        self.enabled = QtWidgets.QCheckBox("Enabled")
        self.enabled.setChecked(True)
        layout.addRow("", self.enabled)
    
    def get_settings(self) -> LightSettings:
        return LightSettings(
            name=self.name_edit.text() or "light",
            light_type=self.type_combo.currentData(),
            role=self.role_combo.currentData(),
            intensity=self.intensity.value(),
            exposure=self.exposure.value(),
            color=(self.color_r.value(), self.color_g.value(), self.color_b.value()),
            temperature=self.temp.value() if self.use_temp.isChecked() else None,
            transform=LightTransform(
                position=(self.pos_x.value(), self.pos_y.value(), self.pos_z.value()),
                rotation=(self.rot_x.value(), self.rot_y.value(), self.rot_z.value())
            ),
            width=self.width.value(), height=self.height.value(), radius=self.radius.value(),
            shadow_enable=self.shadow.isChecked(), enabled=self.enabled.isChecked()
        )
    
    def set_settings(self, s: LightSettings):
        self.name_edit.setText(s.name)
        for i in range(self.type_combo.count()):
            if self.type_combo.itemData(i) == s.light_type:
                self.type_combo.setCurrentIndex(i)
                break
        for i in range(self.role_combo.count()):
            if self.role_combo.itemData(i) == s.role:
                self.role_combo.setCurrentIndex(i)
                break
        self.intensity.setValue(s.intensity)
        self.exposure.setValue(s.exposure)
        self.use_temp.setChecked(s.temperature is not None)
        if s.temperature:
            self.temp.setValue(int(s.temperature))
        self.color_r.setValue(s.color[0])
        self.color_g.setValue(s.color[1])
        self.color_b.setValue(s.color[2])
        self.pos_x.setValue(s.transform.position[0])
        self.pos_y.setValue(s.transform.position[1])
        self.pos_z.setValue(s.transform.position[2])
        self.rot_x.setValue(s.transform.rotation[0])
        self.rot_y.setValue(s.transform.rotation[1])
        self.rot_z.setValue(s.transform.rotation[2])
        self.width.setValue(s.width)
        self.height.setValue(s.height)
        self.radius.setValue(s.radius)
        self.shadow.setChecked(s.shadow_enable)
        self.enabled.setChecked(s.enabled)
    
    def clear(self):
        self.name_edit.clear()
        self.type_combo.setCurrentIndex(0)
        self.role_combo.setCurrentIndex(0)
        self.intensity.setValue(1.0)
        self.exposure.setValue(0.0)
        self.use_temp.setChecked(False)
        self.temp.setValue(5600)
        self.color_r.setValue(1.0)
        self.color_g.setValue(1.0)
        self.color_b.setValue(1.0)
        self.pos_x.setValue(0)
        self.pos_y.setValue(0)
        self.pos_z.setValue(0)
        self.rot_x.setValue(0)
        self.rot_y.setValue(0)
        self.rot_z.setValue(0)
        self.width.setValue(1.0)
        self.height.setValue(1.0)
        self.radius.setValue(0.5)
        self.shadow.setChecked(True)
        self.enabled.setChecked(True)


class LumenPanel(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.manager = LumenRigManager()
        self._current_rig: Optional[LightRig] = None
        self._init_ui()
    
    def _init_ui(self):
        self.setWindowTitle(f"{__title__} - Lighting Rig Manager")
        self.setMinimumSize(400, 300)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(5)

        # Header section - fixed height, doesn't expand
        header_widget = QtWidgets.QWidget()
        header_widget.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        header_layout = QtWidgets.QVBoxLayout(header_widget)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(2)

        header = QtWidgets.QLabel("💡 LUMEN")
        header.setStyleSheet("font-size: 84px; font-weight: bold; color: #CC7722; padding: 10px 20px;")
        header.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        header_layout.addWidget(header)

        subtitle = QtWidgets.QLabel("Lighting Rig Manager")
        subtitle.setStyleSheet("color: #888; font-size: 25px; padding-left: 20px;")
        subtitle.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        header_layout.addWidget(subtitle)

        version_label = QtWidgets.QLabel(f"v{__version__} | Dome Light Fixed")
        version_label.setStyleSheet("color: #666; font-size: 10px; padding-left: 20px;")
        version_label.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        header_layout.addWidget(version_label)

        layout.addWidget(header_widget)
        
        main_splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        
        # Left: Rig list
        left = QtWidgets.QWidget()
        left_layout = QtWidgets.QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(QtWidgets.QLabel("Rigs:"))
        
        self.rig_list = QtWidgets.QListWidget()
        self.rig_list.currentItemChanged.connect(self._on_rig_selected)
        left_layout.addWidget(self.rig_list)
        
        rig_btns = QtWidgets.QHBoxLayout()
        new_btn = QtWidgets.QPushButton("➕ New")
        new_btn.clicked.connect(self._new_rig)
        rig_btns.addWidget(new_btn)
        del_btn = QtWidgets.QPushButton("🗑️ Del")
        del_btn.clicked.connect(self._delete_rig)
        rig_btns.addWidget(del_btn)
        left_layout.addLayout(rig_btns)
        
        main_splitter.addWidget(left)
        
        # Middle: Light list
        mid = QtWidgets.QWidget()
        mid_layout = QtWidgets.QVBoxLayout(mid)
        mid_layout.setContentsMargins(0, 0, 0, 0)
        mid_layout.addWidget(QtWidgets.QLabel("Lights:"))
        
        self.light_list = QtWidgets.QListWidget()
        self.light_list.currentItemChanged.connect(self._on_light_selected)
        mid_layout.addWidget(self.light_list)
        
        light_btns = QtWidgets.QHBoxLayout()
        add_btn = QtWidgets.QPushButton("➕ Add")
        add_btn.clicked.connect(self._add_light)
        light_btns.addWidget(add_btn)
        rem_btn = QtWidgets.QPushButton("➖ Remove")
        rem_btn.clicked.connect(self._remove_light)
        light_btns.addWidget(rem_btn)
        mid_layout.addLayout(light_btns)
        
        main_splitter.addWidget(mid)
        
        # Right: Editor
        right = QtWidgets.QWidget()
        right_layout = QtWidgets.QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.addWidget(QtWidgets.QLabel("Light Settings:"))
        
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        self.light_editor = LightEditorWidget()
        scroll.setWidget(self.light_editor)
        right_layout.addWidget(scroll)
        
        update_btn = QtWidgets.QPushButton("💾 Update Light")
        update_btn.clicked.connect(self._update_light)
        right_layout.addWidget(update_btn)
        
        main_splitter.addWidget(right)
        main_splitter.setSizes([200, 200, 450])
        
        layout.addWidget(main_splitter)
        
        # Build section
        build_group = QtWidgets.QGroupBox("Build in Solaris")
        build_layout = QtWidgets.QHBoxLayout(build_group)
        
        build_layout.addWidget(QtWidgets.QLabel("Stage:"))
        self.stage_path = QtWidgets.QLineEdit("/stage")
        build_layout.addWidget(self.stage_path)
        
        build_layout.addWidget(QtWidgets.QLabel("Root:"))
        self.lights_root = QtWidgets.QLineEdit("/lights")
        build_layout.addWidget(self.lights_root)
        
        build_btn = QtWidgets.QPushButton("🏗️ Build Rig")
        build_btn.setStyleSheet("QPushButton { background-color: #CC7722; color: #FFF; padding: 10px 20px; font-weight: bold; border-radius: 5px; } QPushButton:hover { background-color: #D4922A; }")
        build_btn.clicked.connect(self._build_rig)
        build_layout.addWidget(build_btn)
        
        layout.addWidget(build_group)
        
        self.status_label = QtWidgets.QLabel("")
        layout.addWidget(self.status_label)
        
        self._refresh_rig_list()
    
    def _refresh_rig_list(self):
        self.rig_list.clear()
        for name in sorted(self.manager.rigs.keys()):
            self.rig_list.addItem(name)
    
    def _refresh_light_list(self):
        self.light_list.clear()
        if self._current_rig:
            for light in self._current_rig.lights:
                icon = "✓" if light.enabled else "✗"
                self.light_list.addItem(f"{icon} {light.name} ({light.light_type.value})")
    
    def _on_rig_selected(self, current, previous):
        if current:
            self._current_rig = self.manager.get_rig(current.text())
            self._refresh_light_list()
    
    def _on_light_selected(self, current, previous):
        if current and self._current_rig:
            idx = self.light_list.row(current)
            if 0 <= idx < len(self._current_rig.lights):
                self.light_editor.set_settings(self._current_rig.lights[idx])
    
    def _new_rig(self):
        name, ok = QtWidgets.QInputDialog.getText(self, "New Rig", "Name:")
        if ok and name:
            rig = LightRig(name=name)
            success, msg = self.manager.create_rig(rig)
            self._set_status(msg, "success" if success else "error")
            if success:
                self._refresh_rig_list()
    
    def _delete_rig(self):
        current = self.rig_list.currentItem()
        if not current:
            return
        if QtWidgets.QMessageBox.question(self, "Delete", f"Delete '{current.text()}'?") == QtWidgets.QMessageBox.Yes:
            success, msg = self.manager.delete_rig(current.text())
            self._set_status(msg, "success" if success else "error")
            if success:
                self._current_rig = None
                self._refresh_rig_list()
                self._refresh_light_list()
    
    def _add_light(self):
        if not self._current_rig:
            self._set_status("Select a rig first", "error")
            return
        try:
            settings = self.light_editor.get_settings()
            self._current_rig.lights.append(settings)
            self.manager.update_rig(self._current_rig.name, self._current_rig)
            self._refresh_light_list()
            self._set_status(f"Added: {settings.name}", "success")
        except ValueError as e:
            self._set_status(str(e), "error")
    
    def _remove_light(self):
        if not self._current_rig:
            return
        current = self.light_list.currentItem()
        if not current:
            return
        idx = self.light_list.row(current)
        if 0 <= idx < len(self._current_rig.lights):
            removed = self._current_rig.lights.pop(idx)
            self.manager.update_rig(self._current_rig.name, self._current_rig)
            self._refresh_light_list()
            self._set_status(f"Removed: {removed.name}", "success")
    
    def _update_light(self):
        if not self._current_rig:
            return
        current = self.light_list.currentItem()
        if not current:
            return
        idx = self.light_list.row(current)
        if 0 <= idx < len(self._current_rig.lights):
            try:
                settings = self.light_editor.get_settings()
                self._current_rig.lights[idx] = settings
                self.manager.update_rig(self._current_rig.name, self._current_rig)
                self._refresh_light_list()
                self._set_status(f"Updated: {settings.name}", "success")
            except ValueError as e:
                self._set_status(str(e), "error")
    
    def _build_rig(self):
        if not self._current_rig:
            self._set_status("Select a rig first", "error")
            return
        success, msg, nodes = self.manager.build_rig_in_solaris(
            self._current_rig.name, self.stage_path.text(), self.lights_root.text()
        )
        self._set_status(msg, "success" if success else "error")
    
    def _set_status(self, message: str, status_type: str = "info"):
        colors = {"success": "#7D8B69", "error": "#8B4513", "info": "#CC7722"}
        self.status_label.setStyleSheet(f"color: {colors.get(status_type, '#888')};")
        self.status_label.setText(message)


# =============================================================================
# ENTRY POINT
# =============================================================================

def create_panel():
    """Create and show Lumen panel"""
    panel = LumenPanel()
    panel.setParent(hou.qt.mainWindow(), QtCore.Qt.Window)
    panel.show()
    return panel


if __name__ == "__main__":
    create_panel()
