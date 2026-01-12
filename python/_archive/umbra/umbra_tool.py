"""
╔═══════════════════════════════════════════════════════════════════════════════╗
║                                                                               ║
║   ██╗   ██╗███╗   ███╗██████╗ ██████╗  █████╗                                 ║
║   ██║   ██║████╗ ████║██╔══██╗██╔══██╗██╔══██╗                                ║
║   ██║   ██║██╔████╔██║██████╔╝██████╔╝███████║                                ║
║   ██║   ██║██║╚██╔╝██║██╔══██╗██╔══██╗██╔══██║                                ║
║   ╚██████╔╝██║ ╚═╝ ██║██████╔╝██║  ██║██║  ██║                                ║
║    ╚═════╝ ╚═╝     ╚═╝╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝                                ║
║                                                                               ║
║   GOBO Preset Generator for Houdini 21                                        ║
║   Create, manage, and apply shadow patterns to your lights                    ║
║                                                                               ║
╚═══════════════════════════════════════════════════════════════════════════════╝

Umbra v2.1.0 | Houdini 21+ | Python 3.9+

Professional GOBO preset management for Solaris/USD lighting workflows.
Full Copernicus 3.0 support with cross-renderer compatibility.

FEATURES:
• Comprehensive COP network detection (Legacy + Copernicus 3.0)
• Schema-versioned preset files for team sharing
• Multi-renderer support (Karma, Arnold, RenderMan, Redshift, V-Ray)
• Thread-safe preset operations
• USD API direct access for H21 stability
• Input validation with descriptive errors

USAGE:
    from umbra import create_panel
    panel = create_panel()

LICENSE: MIT
AUTHOR: Joe Ibrahim
WEBSITE: https://github.com/yourusername/umbra
"""

__title__ = "Umbra"
__version__ = "2.1.0"
__author__ = "Joe Ibrahim"
__license__ = "MIT"
__product__ = "Umbra - GOBO Preset Generator"

import hou
import os
import json
import threading
import traceback
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple, Set
from dataclasses import dataclass, field, asdict
from enum import Enum
from abc import ABC, abstractmethod
from PySide6 import QtWidgets, QtCore, QtGui

SCHEMA_VERSION = "2.1.0"


# =============================================================================
# ENUMS AND DATA CLASSES
# =============================================================================

class Renderer(Enum):
    KARMA = "karma"
    ARNOLD = "arnold"
    RENDERMAN = "renderman"
    REDSHIFT = "redshift"
    VRAY = "vray"
    
    @classmethod
    def from_string(cls, value: str) -> 'Renderer':
        for r in cls:
            if r.value == value.lower():
                return r
        raise ValueError(f"Unknown renderer: {value}")


class BlendMode(Enum):
    MULTIPLY = "multiply"
    SCREEN = "screen"
    OVERLAY = "overlay"
    SOFT_LIGHT = "soft_light"
    HARD_LIGHT = "hard_light"


@dataclass
class UmbraPreset:
    """GOBO preset configuration with validation and versioning"""
    name: str
    cop_path: str
    resolution: Tuple[int, int] = (1024, 1024)
    blur: float = 0.0
    scale: float = 1.0
    rotation: float = 0.0
    offset_u: float = 0.0
    offset_v: float = 0.0
    invert: bool = False
    blend_mode: BlendMode = BlendMode.MULTIPLY
    intensity: float = 1.0
    falloff: float = 0.0
    animated: bool = False
    frame_range: Tuple[int, int] = (1, 100)
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    modified_at: str = ""
    tags: List[str] = field(default_factory=list)
    
    def __post_init__(self):
        self._validate()
    
    def _validate(self):
        if not self.name or not self.name.strip():
            raise ValueError("Preset name cannot be empty")
        if not self.cop_path:
            raise ValueError("COP path cannot be empty")
        if self.resolution[0] < 1 or self.resolution[1] < 1:
            raise ValueError("Resolution must be positive")
        if self.resolution[0] > 16384 or self.resolution[1] > 16384:
            raise ValueError("Resolution exceeds maximum (16384)")
        if not 0.0 <= self.blur <= 100.0:
            raise ValueError("Blur must be between 0 and 100")
        if not 0.01 <= self.scale <= 100.0:
            raise ValueError("Scale must be between 0.01 and 100")
        if not 0.0 <= self.intensity <= 10.0:
            raise ValueError("Intensity must be between 0 and 10")
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "_schema_version": SCHEMA_VERSION,
            "_product": __product__,
            "name": self.name,
            "cop_path": self.cop_path,
            "resolution": list(self.resolution),
            "blur": self.blur,
            "scale": self.scale,
            "rotation": self.rotation,
            "offset_u": self.offset_u,
            "offset_v": self.offset_v,
            "invert": self.invert,
            "blend_mode": self.blend_mode.value,
            "intensity": self.intensity,
            "falloff": self.falloff,
            "animated": self.animated,
            "frame_range": list(self.frame_range),
            "metadata": self.metadata,
            "created_at": self.created_at,
            "modified_at": self.modified_at,
            "tags": self.tags
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'UmbraPreset':
        data.pop("_schema_version", None)
        data.pop("_product", None)
        
        data["resolution"] = tuple(data.get("resolution", [1024, 1024]))
        data["frame_range"] = tuple(data.get("frame_range", [1, 100]))
        
        blend_str = data.get("blend_mode", "multiply")
        try:
            data["blend_mode"] = BlendMode(blend_str)
        except ValueError:
            data["blend_mode"] = BlendMode.MULTIPLY
        
        defaults = {"blur": 0.0, "scale": 1.0, "rotation": 0.0, "offset_u": 0.0, "offset_v": 0.0,
                   "invert": False, "intensity": 1.0, "falloff": 0.0, "animated": False,
                   "metadata": {}, "created_at": "", "modified_at": "", "tags": []}
        
        for key, val in defaults.items():
            if key not in data:
                data[key] = val
        
        return cls(**data)


# =============================================================================
# RENDERER ADAPTERS
# =============================================================================

class RendererAdapterBase(ABC):
    @property
    @abstractmethod
    def renderer(self) -> Renderer:
        pass
    
    @property
    @abstractmethod
    def texture_attribute(self) -> str:
        pass
    
    @property
    @abstractmethod
    def light_types(self) -> List[str]:
        pass
    
    @abstractmethod
    def format_texture_reference(self, cop_path: str, is_copernicus: bool) -> str:
        pass
    
    @abstractmethod
    def get_additional_attributes(self, preset: UmbraPreset) -> Dict[str, Any]:
        pass


class KarmaAdapter(RendererAdapterBase):
    @property
    def renderer(self) -> Renderer:
        return Renderer.KARMA
    
    @property
    def texture_attribute(self) -> str:
        return "inputs:texture:file"
    
    @property
    def light_types(self) -> List[str]:
        return ["RectLight", "DiskLight", "DistantLight", "SphereLight", "CylinderLight"]
    
    def format_texture_reference(self, cop_path: str, is_copernicus: bool) -> str:
        return f"op:{cop_path}"
    
    def get_additional_attributes(self, preset: UmbraPreset) -> Dict[str, Any]:
        return {
            "inputs:texture:scaleS": preset.scale,
            "inputs:texture:scaleT": preset.scale,
            "inputs:texture:rotate": preset.rotation,
            "inputs:texture:offsetS": preset.offset_u,
            "inputs:texture:offsetT": preset.offset_v,
            "karma:light:textureSoftness": preset.blur / 100.0,
        }


class ArnoldAdapter(RendererAdapterBase):
    @property
    def renderer(self) -> Renderer:
        return Renderer.ARNOLD
    
    @property
    def texture_attribute(self) -> str:
        return "arnold:filters"
    
    @property
    def light_types(self) -> List[str]:
        return ["RectLight", "DiskLight", "DistantLight", "SphereLight"]
    
    def format_texture_reference(self, cop_path: str, is_copernicus: bool) -> str:
        return f"op:{cop_path}"
    
    def get_additional_attributes(self, preset: UmbraPreset) -> Dict[str, Any]:
        return {
            "arnold:gobo:scale_s": preset.scale,
            "arnold:gobo:scale_t": preset.scale,
            "arnold:gobo:rotate": preset.rotation,
            "arnold:gobo:offset_s": preset.offset_u,
            "arnold:gobo:offset_t": preset.offset_v,
        }


class RenderManAdapter(RendererAdapterBase):
    @property
    def renderer(self) -> Renderer:
        return Renderer.RENDERMAN
    
    @property
    def texture_attribute(self) -> str:
        return "ri:light:lightBlockerMap"
    
    @property
    def light_types(self) -> List[str]:
        return ["RectLight", "DiskLight", "DistantLight", "SphereLight"]
    
    def format_texture_reference(self, cop_path: str, is_copernicus: bool) -> str:
        return f"op:{cop_path}"
    
    def get_additional_attributes(self, preset: UmbraPreset) -> Dict[str, Any]:
        return {"ri:light:blockerWidth": preset.scale, "ri:light:blockerHeight": preset.scale, "ri:light:blockerRot": preset.rotation}


class RedshiftAdapter(RendererAdapterBase):
    @property
    def renderer(self) -> Renderer:
        return Renderer.REDSHIFT
    
    @property
    def texture_attribute(self) -> str:
        return "redshift:light:gobo"
    
    @property
    def light_types(self) -> List[str]:
        return ["RectLight", "DiskLight", "DomeLight", "SphereLight"]
    
    def format_texture_reference(self, cop_path: str, is_copernicus: bool) -> str:
        return f"op:{cop_path}"
    
    def get_additional_attributes(self, preset: UmbraPreset) -> Dict[str, Any]:
        return {
            "redshift:light:gobo_scale_x": preset.scale,
            "redshift:light:gobo_scale_y": preset.scale,
            "redshift:light:gobo_rotation": preset.rotation,
            "redshift:light:gobo_offset_x": preset.offset_u,
            "redshift:light:gobo_offset_y": preset.offset_v,
        }


class VRayAdapter(RendererAdapterBase):
    @property
    def renderer(self) -> Renderer:
        return Renderer.VRAY
    
    @property
    def texture_attribute(self) -> str:
        return "vray:light:texmap"
    
    @property
    def light_types(self) -> List[str]:
        return ["RectLight", "DomeLight", "SphereLight"]
    
    def format_texture_reference(self, cop_path: str, is_copernicus: bool) -> str:
        return f"op:{cop_path}"
    
    def get_additional_attributes(self, preset: UmbraPreset) -> Dict[str, Any]:
        return {"vray:light:texmap_scale_u": preset.scale, "vray:light:texmap_scale_v": preset.scale, "vray:light:texmap_rotate": preset.rotation}


class RendererAdapterFactory:
    """Thread-safe factory for renderer adapters"""
    _adapters: Dict[Renderer, RendererAdapterBase] = {}
    _lock = threading.Lock()
    
    @classmethod
    def get_adapter(cls, renderer: Renderer) -> RendererAdapterBase:
        if renderer not in cls._adapters:
            with cls._lock:
                if renderer not in cls._adapters:
                    adapters = {
                        Renderer.KARMA: KarmaAdapter,
                        Renderer.ARNOLD: ArnoldAdapter,
                        Renderer.RENDERMAN: RenderManAdapter,
                        Renderer.REDSHIFT: RedshiftAdapter,
                        Renderer.VRAY: VRayAdapter,
                    }
                    cls._adapters[renderer] = adapters[renderer]()
        return cls._adapters[renderer]


# =============================================================================
# COP NETWORK SCANNER (Copernicus 3.0 Support)
# =============================================================================

@dataclass
class CopNetworkInfo:
    path: str
    name: str
    is_copernicus: bool
    category: str
    output_nodes: List[str] = field(default_factory=list)
    node_count: int = 0


class CopNetworkScanner:
    """Comprehensive COP scanner with Copernicus 3.0 support"""
    
    COPERNICUS_PATTERNS = ["copernicus", "cop2net", "copinput", "copoutput", "copimport", "copio", "cop2"]
    OUTPUT_NODE_TYPES = ["output", "null", "composite", "over", "tilepattern", "render", "rop_comp", "file"]
    
    @classmethod
    def scan_all_networks(cls) -> List[CopNetworkInfo]:
        networks = []
        scanned: Set[str] = set()
        
        # Scan /img (legacy)
        img = hou.node("/img")
        if img:
            for child in img.children():
                path = child.path()
                if path in scanned:
                    continue
                scanned.add(path)
                if child.type().category().name() == "Cop2" or "cop" in child.type().name().lower():
                    networks.append(CopNetworkInfo(
                        path=path, name=child.name(), is_copernicus=False, category="Cop2",
                        output_nodes=cls._find_outputs(child),
                        node_count=len(child.children()) if hasattr(child, 'children') else 0
                    ))
        
        # Scan /stage (Copernicus in Solaris)
        stage = hou.node("/stage")
        if stage:
            for node in stage.allSubChildren():
                path = node.path()
                if path in scanned:
                    continue
                type_name = node.type().name().lower()
                if any(p in type_name for p in cls.COPERNICUS_PATTERNS):
                    scanned.add(path)
                    networks.append(CopNetworkInfo(
                        path=path, name=node.name(), is_copernicus=True, category="Lop/Copernicus",
                        output_nodes=cls._find_outputs(node),
                        node_count=len(node.children()) if hasattr(node, 'children') else 0
                    ))
        
        # Deep scan all
        for node in hou.node("/").allSubChildren():
            path = node.path()
            if path in scanned:
                continue
            if node.type().category().name() == "Cop2":
                scanned.add(path)
                networks.append(CopNetworkInfo(
                    path=path, name=node.name(),
                    is_copernicus="copernicus" in node.type().name().lower(),
                    category="Cop2/Deep",
                    output_nodes=cls._find_outputs(node),
                    node_count=len(node.children()) if hasattr(node, 'children') else 0
                ))
        
        return networks
    
    @classmethod
    def _find_outputs(cls, network: hou.Node) -> List[str]:
        outputs = []
        if not hasattr(network, 'children'):
            return outputs
        
        for child in network.children():
            type_name = child.type().name().lower()
            if hasattr(child, 'isRenderFlagSet'):
                try:
                    if child.isRenderFlagSet():
                        outputs.append(child.path())
                        continue
                except:
                    pass
            if hasattr(child, 'isDisplayFlagSet'):
                try:
                    if child.isDisplayFlagSet():
                        outputs.append(child.path())
                        continue
                except:
                    pass
            if type_name in cls.OUTPUT_NODE_TYPES:
                outputs.append(child.path())
        
        return outputs


# =============================================================================
# PRESET MANAGER
# =============================================================================

class UmbraPresetManager:
    """Thread-safe preset manager"""
    
    PRESET_DIR = Path(hou.expandString("$HOUDINI_USER_PREF_DIR")) / "umbra_presets"
    
    def __init__(self):
        self._presets: Dict[str, UmbraPreset] = {}
        self._lock = threading.RLock()
        self._ensure_dir()
        self._load_presets()
    
    def _ensure_dir(self):
        try:
            self.PRESET_DIR.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            print(f"[Umbra] Warning: {e}")
    
    def _load_presets(self):
        preset_file = self.PRESET_DIR / "presets.json"
        if not preset_file.exists():
            return
        
        with self._lock:
            try:
                with open(preset_file, 'r') as f:
                    data = json.load(f)
                
                presets_data = data.get("_presets", data)
                for name, p_data in presets_data.items():
                    if name.startswith("_"):
                        continue
                    try:
                        self._presets[name] = UmbraPreset.from_dict(p_data)
                    except Exception as e:
                        print(f"[Umbra] Warning: Could not load '{name}': {e}")
            except Exception as e:
                print(f"[Umbra] Error loading presets: {e}")
    
    def _save_presets(self):
        preset_file = self.PRESET_DIR / "presets.json"
        
        with self._lock:
            try:
                import datetime
                data = {
                    "_schema_version": SCHEMA_VERSION,
                    "_product": __product__,
                    "_saved_at": datetime.datetime.now().isoformat(),
                    "_presets": {name: p.to_dict() for name, p in self._presets.items()}
                }
                with open(preset_file, 'w') as f:
                    json.dump(data, f, indent=2)
            except Exception as e:
                print(f"[Umbra] Error saving: {e}")
    
    @property
    def presets(self) -> Dict[str, UmbraPreset]:
        with self._lock:
            return dict(self._presets)
    
    def get_preset(self, name: str) -> Optional[UmbraPreset]:
        with self._lock:
            return self._presets.get(name)
    
    def create_preset(self, preset: UmbraPreset) -> Tuple[bool, str]:
        if not self._validate_cop(preset.cop_path):
            return False, f"Invalid COP path: {preset.cop_path}"
        
        with self._lock:
            import datetime
            now = datetime.datetime.now().isoformat()
            preset.created_at = now
            preset.modified_at = now
            self._presets[preset.name] = preset
            self._save_presets()
        
        return True, f"Created preset: {preset.name}"
    
    def update_preset(self, name: str, preset: UmbraPreset) -> Tuple[bool, str]:
        with self._lock:
            if name not in self._presets:
                return False, f"Preset not found: {name}"
            
            import datetime
            preset.modified_at = datetime.datetime.now().isoformat()
            preset.created_at = self._presets[name].created_at
            
            if name != preset.name:
                del self._presets[name]
            
            self._presets[preset.name] = preset
            self._save_presets()
        
        return True, f"Updated: {preset.name}"
    
    def delete_preset(self, name: str) -> Tuple[bool, str]:
        with self._lock:
            if name not in self._presets:
                return False, f"Not found: {name}"
            del self._presets[name]
            self._save_presets()
        return True, f"Deleted: {name}"
    
    def duplicate_preset(self, name: str, new_name: str) -> Tuple[bool, str]:
        with self._lock:
            if name not in self._presets:
                return False, f"Not found: {name}"
            if new_name in self._presets:
                return False, f"Already exists: {new_name}"
            
            import datetime
            orig = self._presets[name]
            dup = UmbraPreset(
                name=new_name, cop_path=orig.cop_path, resolution=orig.resolution,
                blur=orig.blur, scale=orig.scale, rotation=orig.rotation,
                offset_u=orig.offset_u, offset_v=orig.offset_v, invert=orig.invert,
                blend_mode=orig.blend_mode, intensity=orig.intensity, falloff=orig.falloff,
                animated=orig.animated, frame_range=orig.frame_range,
                metadata=dict(orig.metadata), tags=list(orig.tags),
                created_at=datetime.datetime.now().isoformat(),
                modified_at=datetime.datetime.now().isoformat()
            )
            self._presets[new_name] = dup
            self._save_presets()
        
        return True, f"Duplicated as '{new_name}'"
    
    def _validate_cop(self, cop_path: str) -> bool:
        return hou.node(cop_path) is not None
    
    def apply_to_light_usd(self, preset: UmbraPreset, lop_node: hou.LopNode, prim_path: str, renderer: Renderer) -> Tuple[bool, str]:
        try:
            adapter = RendererAdapterFactory.get_adapter(renderer)
            
            cop_info = None
            for info in CopNetworkScanner.scan_all_networks():
                if preset.cop_path.startswith(info.path):
                    cop_info = info
                    break
            
            is_copernicus = cop_info.is_copernicus if cop_info else False
            texture_ref = adapter.format_texture_reference(preset.cop_path, is_copernicus)
            
            parent = lop_node.parent()
            python_lop = parent.createNode("pythonscript", f"umbra_{preset.name.replace(' ', '_')}")
            python_lop.setInput(0, lop_node)
            
            attrs = adapter.get_additional_attributes(preset)
            attrs[adapter.texture_attribute] = texture_ref
            
            code_lines = [
                "from pxr import Usd, Sdf, Gf",
                "",
                "node = hou.pwd()",
                "stage = node.editableStage()",
                f'prim_path = "{prim_path}"',
                "",
                "prim = stage.GetPrimAtPath(prim_path)",
                "if not prim:",
                f'    raise RuntimeError("Prim not found: {prim_path}")',
                "",
                f"# Umbra GOBO attributes for {renderer.value}",
            ]
            
            for attr_name, attr_value in attrs.items():
                if isinstance(attr_value, str):
                    code_lines.append(f'prim.CreateAttribute("{attr_name}", Sdf.ValueTypeNames.String).Set("{attr_value}")')
                elif isinstance(attr_value, float):
                    code_lines.append(f'prim.CreateAttribute("{attr_name}", Sdf.ValueTypeNames.Float).Set({attr_value})')
                elif isinstance(attr_value, bool):
                    code_lines.append(f'prim.CreateAttribute("{attr_name}", Sdf.ValueTypeNames.Bool).Set({attr_value})')
            
            if preset.invert:
                code_lines.append(f'prim.CreateAttribute("{adapter.texture_attribute}:invert", Sdf.ValueTypeNames.Bool).Set(True)')
            
            python_lop.parm("python").set("\n".join(code_lines))
            python_lop.moveToGoodPosition()
            
            return True, f"Applied '{preset.name}' to {prim_path}"
            
        except Exception as e:
            traceback.print_exc()
            return False, f"Error: {e}"


# =============================================================================
# QT PANEL
# =============================================================================

class CopBrowserWidget(QtWidgets.QWidget):
    cop_selected = QtCore.Signal(str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()
    
    def _init_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        toolbar = QtWidgets.QHBoxLayout()
        refresh_btn = QtWidgets.QPushButton("🔄 Refresh")
        refresh_btn.clicked.connect(self._refresh)
        toolbar.addWidget(refresh_btn)
        
        self.filter_combo = QtWidgets.QComboBox()
        self.filter_combo.addItems(["All", "Copernicus Only", "Legacy Only"])
        self.filter_combo.currentIndexChanged.connect(self._refresh)
        toolbar.addWidget(self.filter_combo)
        toolbar.addStretch()
        layout.addLayout(toolbar)
        
        self.tree = QtWidgets.QTreeWidget()
        self.tree.setHeaderLabels(["Name", "Type", "Outputs"])
        self.tree.setAlternatingRowColors(True)
        self.tree.itemDoubleClicked.connect(self._on_double_click)
        layout.addWidget(self.tree)
        
        self._refresh()
    
    def _refresh(self):
        self.tree.clear()
        networks = CopNetworkScanner.scan_all_networks()
        filter_mode = self.filter_combo.currentText()
        
        for info in networks:
            if filter_mode == "Copernicus Only" and not info.is_copernicus:
                continue
            if filter_mode == "Legacy Only" and info.is_copernicus:
                continue
            
            item = QtWidgets.QTreeWidgetItem([info.name, "Copernicus" if info.is_copernicus else "Legacy", str(len(info.output_nodes))])
            item.setData(0, QtCore.Qt.UserRole, info.path)
            item.setToolTip(0, info.path)
            
            for output_path in info.output_nodes:
                child = QtWidgets.QTreeWidgetItem([output_path.split("/")[-1], "Output", ""])
                child.setData(0, QtCore.Qt.UserRole, output_path)
                item.addChild(child)
            
            self.tree.addTopLevelItem(item)
        
        self.tree.expandAll()
        self.tree.resizeColumnToContents(0)
    
    def _on_double_click(self, item, column):
        path = item.data(0, QtCore.Qt.UserRole)
        if path:
            self.cop_selected.emit(path)
    
    def get_selected_path(self) -> Optional[str]:
        items = self.tree.selectedItems()
        return items[0].data(0, QtCore.Qt.UserRole) if items else None


class PresetEditorWidget(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()
    
    def _init_ui(self):
        layout = QtWidgets.QFormLayout(self)
        
        self.name_edit = QtWidgets.QLineEdit()
        layout.addRow("Name:", self.name_edit)
        
        cop_layout = QtWidgets.QHBoxLayout()
        self.cop_path_edit = QtWidgets.QLineEdit()
        cop_layout.addWidget(self.cop_path_edit)
        cop_browse = QtWidgets.QPushButton("...")
        cop_browse.setMaximumWidth(30)
        cop_browse.clicked.connect(self._browse_cop)
        cop_layout.addWidget(cop_browse)
        layout.addRow("COP Path:", cop_layout)
        
        res_layout = QtWidgets.QHBoxLayout()
        self.res_x = QtWidgets.QSpinBox()
        self.res_x.setRange(1, 16384)
        self.res_x.setValue(1024)
        res_layout.addWidget(self.res_x)
        res_layout.addWidget(QtWidgets.QLabel("x"))
        self.res_y = QtWidgets.QSpinBox()
        self.res_y.setRange(1, 16384)
        self.res_y.setValue(1024)
        res_layout.addWidget(self.res_y)
        layout.addRow("Resolution:", res_layout)
        
        self.scale_spin = QtWidgets.QDoubleSpinBox()
        self.scale_spin.setRange(0.01, 100.0)
        self.scale_spin.setValue(1.0)
        self.scale_spin.setSingleStep(0.1)
        layout.addRow("Scale:", self.scale_spin)
        
        self.rotation_spin = QtWidgets.QDoubleSpinBox()
        self.rotation_spin.setRange(-360.0, 360.0)
        self.rotation_spin.setSuffix("°")
        layout.addRow("Rotation:", self.rotation_spin)
        
        offset_layout = QtWidgets.QHBoxLayout()
        self.offset_u = QtWidgets.QDoubleSpinBox()
        self.offset_u.setRange(-10.0, 10.0)
        self.offset_u.setSingleStep(0.01)
        offset_layout.addWidget(QtWidgets.QLabel("U:"))
        offset_layout.addWidget(self.offset_u)
        self.offset_v = QtWidgets.QDoubleSpinBox()
        self.offset_v.setRange(-10.0, 10.0)
        self.offset_v.setSingleStep(0.01)
        offset_layout.addWidget(QtWidgets.QLabel("V:"))
        offset_layout.addWidget(self.offset_v)
        layout.addRow("Offset:", offset_layout)
        
        self.blur_spin = QtWidgets.QDoubleSpinBox()
        self.blur_spin.setRange(0.0, 100.0)
        layout.addRow("Blur:", self.blur_spin)
        
        self.intensity_spin = QtWidgets.QDoubleSpinBox()
        self.intensity_spin.setRange(0.0, 10.0)
        self.intensity_spin.setValue(1.0)
        self.intensity_spin.setSingleStep(0.1)
        layout.addRow("Intensity:", self.intensity_spin)
        
        self.invert_check = QtWidgets.QCheckBox()
        layout.addRow("Invert:", self.invert_check)
        
        self.blend_combo = QtWidgets.QComboBox()
        for mode in BlendMode:
            self.blend_combo.addItem(mode.value.replace("_", " ").title(), mode)
        layout.addRow("Blend Mode:", self.blend_combo)
        
        self.tags_edit = QtWidgets.QLineEdit()
        self.tags_edit.setPlaceholderText("tag1, tag2, tag3")
        layout.addRow("Tags:", self.tags_edit)
    
    def _browse_cop(self):
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle("Select COP Network")
        dialog.setMinimumSize(400, 500)
        
        layout = QtWidgets.QVBoxLayout(dialog)
        browser = CopBrowserWidget()
        layout.addWidget(browser)
        
        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        
        if dialog.exec() == QtWidgets.QDialog.Accepted:
            path = browser.get_selected_path()
            if path:
                self.cop_path_edit.setText(path)
    
    def get_preset(self) -> UmbraPreset:
        return UmbraPreset(
            name=self.name_edit.text(),
            cop_path=self.cop_path_edit.text(),
            resolution=(self.res_x.value(), self.res_y.value()),
            blur=self.blur_spin.value(),
            scale=self.scale_spin.value(),
            rotation=self.rotation_spin.value(),
            offset_u=self.offset_u.value(),
            offset_v=self.offset_v.value(),
            invert=self.invert_check.isChecked(),
            blend_mode=self.blend_combo.currentData(),
            intensity=self.intensity_spin.value(),
            tags=[t.strip() for t in self.tags_edit.text().split(",") if t.strip()]
        )
    
    def set_preset(self, preset: UmbraPreset):
        self.name_edit.setText(preset.name)
        self.cop_path_edit.setText(preset.cop_path)
        self.res_x.setValue(preset.resolution[0])
        self.res_y.setValue(preset.resolution[1])
        self.blur_spin.setValue(preset.blur)
        self.scale_spin.setValue(preset.scale)
        self.rotation_spin.setValue(preset.rotation)
        self.offset_u.setValue(preset.offset_u)
        self.offset_v.setValue(preset.offset_v)
        self.invert_check.setChecked(preset.invert)
        self.intensity_spin.setValue(preset.intensity)
        self.tags_edit.setText(", ".join(preset.tags))
        
        for i in range(self.blend_combo.count()):
            if self.blend_combo.itemData(i) == preset.blend_mode:
                self.blend_combo.setCurrentIndex(i)
                break
    
    def clear(self):
        self.name_edit.clear()
        self.cop_path_edit.clear()
        self.res_x.setValue(1024)
        self.res_y.setValue(1024)
        self.blur_spin.setValue(0.0)
        self.scale_spin.setValue(1.0)
        self.rotation_spin.setValue(0.0)
        self.offset_u.setValue(0.0)
        self.offset_v.setValue(0.0)
        self.invert_check.setChecked(False)
        self.intensity_spin.setValue(1.0)
        self.blend_combo.setCurrentIndex(0)
        self.tags_edit.clear()


class UmbraPanel(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.manager = UmbraPresetManager()
        self._init_ui()
    
    def _init_ui(self):
        self.setWindowTitle(f"{__title__} - GOBO Preset Generator")
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

        header = QtWidgets.QLabel("🌑 UMBRA")
        header.setStyleSheet("font-size: 84px; font-weight: bold; color: #9A8B99; padding: 10px 20px;")
        header.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        header_layout.addWidget(header)

        subtitle = QtWidgets.QLabel("GOBO Preset Generator")
        subtitle.setStyleSheet("color: #888; font-size: 25px; padding-left: 20px;")
        subtitle.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        header_layout.addWidget(subtitle)

        version_label = QtWidgets.QLabel(f"v{__version__}")
        version_label.setStyleSheet("color: #666; font-size: 10px; padding-left: 20px;")
        version_label.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        header_layout.addWidget(version_label)

        layout.addWidget(header_widget)
        
        splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        
        # Left: List
        left = QtWidgets.QWidget()
        left_layout = QtWidgets.QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(QtWidgets.QLabel("Presets:"))
        
        self.preset_list = QtWidgets.QListWidget()
        self.preset_list.setAlternatingRowColors(True)
        self.preset_list.currentItemChanged.connect(self._on_preset_selected)
        left_layout.addWidget(self.preset_list)
        
        list_btns = QtWidgets.QHBoxLayout()
        new_btn = QtWidgets.QPushButton("➕ New")
        new_btn.clicked.connect(self._new_preset)
        list_btns.addWidget(new_btn)
        dup_btn = QtWidgets.QPushButton("📋 Dup")
        dup_btn.clicked.connect(self._duplicate_preset)
        list_btns.addWidget(dup_btn)
        del_btn = QtWidgets.QPushButton("🗑️ Del")
        del_btn.clicked.connect(self._delete_preset)
        list_btns.addWidget(del_btn)
        left_layout.addLayout(list_btns)
        
        splitter.addWidget(left)
        
        # Right: Editor
        right = QtWidgets.QWidget()
        right_layout = QtWidgets.QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.addWidget(QtWidgets.QLabel("Preset Editor:"))
        
        self.editor = PresetEditorWidget()
        right_layout.addWidget(self.editor)
        
        save_btn = QtWidgets.QPushButton("💾 Save Preset")
        save_btn.setStyleSheet("QPushButton { background-color: #8E7B94; color: white; padding: 10px; font-weight: bold; border-radius: 5px; } QPushButton:hover { background-color: #9E8BA4; }")
        save_btn.clicked.connect(self._save_preset)
        right_layout.addWidget(save_btn)
        
        splitter.addWidget(right)
        splitter.setSizes([250, 500])
        
        layout.addWidget(splitter)
        
        # Apply section
        apply_group = QtWidgets.QGroupBox("Apply to Light")
        apply_layout = QtWidgets.QHBoxLayout(apply_group)
        
        apply_layout.addWidget(QtWidgets.QLabel("Renderer:"))
        self.renderer_combo = QtWidgets.QComboBox()
        for r in Renderer:
            self.renderer_combo.addItem(r.value.title(), r)
        apply_layout.addWidget(self.renderer_combo)
        
        apply_btn = QtWidgets.QPushButton("🎯 Apply to Selected Light")
        apply_btn.clicked.connect(self._apply_to_light)
        apply_layout.addWidget(apply_btn)
        
        layout.addWidget(apply_group)
        
        self.status_label = QtWidgets.QLabel("")
        self.status_label.setStyleSheet("padding: 5px;")
        layout.addWidget(self.status_label)
        
        self._refresh_list()
    
    def _refresh_list(self):
        self.preset_list.clear()
        for name in sorted(self.manager.presets.keys()):
            self.preset_list.addItem(name)
    
    def _on_preset_selected(self, current, previous):
        if current:
            preset = self.manager.get_preset(current.text())
            if preset:
                self.editor.set_preset(preset)
    
    def _new_preset(self):
        self.editor.clear()
        self.preset_list.clearSelection()
        self._set_status("Creating new preset...", "info")
    
    def _duplicate_preset(self):
        current = self.preset_list.currentItem()
        if not current:
            self._set_status("No preset selected", "error")
            return
        
        name, ok = QtWidgets.QInputDialog.getText(self, "Duplicate Preset", "New name:", text=f"{current.text()}_copy")
        if ok and name:
            success, msg = self.manager.duplicate_preset(current.text(), name)
            self._set_status(msg, "success" if success else "error")
            if success:
                self._refresh_list()
    
    def _delete_preset(self):
        current = self.preset_list.currentItem()
        if not current:
            self._set_status("No preset selected", "error")
            return
        
        if QtWidgets.QMessageBox.question(self, "Delete", f"Delete '{current.text()}'?") == QtWidgets.QMessageBox.Yes:
            success, msg = self.manager.delete_preset(current.text())
            self._set_status(msg, "success" if success else "error")
            if success:
                self._refresh_list()
                self.editor.clear()
    
    def _save_preset(self):
        try:
            preset = self.editor.get_preset()
            current = self.preset_list.currentItem()
            
            if current and current.text() in self.manager.presets:
                success, msg = self.manager.update_preset(current.text(), preset)
            else:
                success, msg = self.manager.create_preset(preset)
            
            self._set_status(msg, "success" if success else "error")
            if success:
                self._refresh_list()
        except ValueError as e:
            self._set_status(str(e), "error")
    
    def _apply_to_light(self):
        current = self.preset_list.currentItem()
        if not current:
            self._set_status("Select a preset first", "error")
            return
        
        preset = self.manager.get_preset(current.text())
        if not preset:
            self._set_status("Preset not found", "error")
            return
        
        renderer = self.renderer_combo.currentData()
        selected = hou.selectedNodes()
        lop_nodes = [n for n in selected if n.type().category().name() == "Lop"]
        
        if not lop_nodes:
            self._set_status("Select a LOP node first", "error")
            return
        
        lop_node = lop_nodes[0]
        stage = lop_node.stage()
        
        if not stage:
            self._set_status("No USD stage found", "error")
            return
        
        light_path = None
        adapter = RendererAdapterFactory.get_adapter(renderer)
        for prim in stage.Traverse():
            if prim.GetTypeName() in adapter.light_types:
                light_path = str(prim.GetPath())
                break
        
        if not light_path:
            self._set_status("No compatible light found", "error")
            return
        
        success, msg = self.manager.apply_to_light_usd(preset, lop_node, light_path, renderer)
        self._set_status(msg, "success" if success else "error")
    
    def _set_status(self, message: str, status_type: str = "info"):
        colors = {"success": "#7D8B69", "error": "#8B4513", "info": "#9A8B99"}
        self.status_label.setStyleSheet(f"color: {colors.get(status_type, '#888')}; padding: 5px;")
        self.status_label.setText(message)


# =============================================================================
# ENTRY POINT
# =============================================================================

def create_panel():
    """Create and show Umbra panel"""
    panel = UmbraPanel()
    panel.setParent(hou.qt.mainWindow(), QtCore.Qt.Window)
    panel.show()
    return panel


if __name__ == "__main__":
    create_panel()
