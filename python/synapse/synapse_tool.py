"""
┌───────────────────────────────────────────────────────────────────────┐
│                                                                       │▒
│   ███████╗██╗   ██╗███╗   ██╗ █████╗ ██████╗ ███████╗███████╗        │▒
│   ██╔════╝╚██╗ ██╔╝████╗  ██║██╔══██╗██╔══██╗██╔════╝██╔════╝        │▒
│   ███████╗ ╚████╔╝ ██╔██╗ ██║███████║██████╔╝███████╗█████╗          │▒
│   ╚════██║  ╚██╔╝  ██║╚██╗██║██╔══██║██╔═══╝ ╚════██║██╔══╝          │▒
│   ███████║   ██║   ██║ ╚████║██║  ██║██║     ███████║███████╗        │▒
│   ╚══════╝   ╚═╝   ╚═╝  ╚═══╝╚═╝  ╚═╝╚═╝     ╚══════╝╚══════╝        │▒
│                                                                       │▒
│   AI ↔ Houdini Bridge                                                 │▒
│   Connect Claude Code, Cursor, or any AI assistant directly to Houdini│▒
│                                                                       │▒
└───────────────────────────────────────────────────────────────────────┘▒
 ▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒

Synapse v2.1.0 | Houdini 21+ | Python 3.9+

WebSocket-based bridge enabling AI assistants to create nodes, manipulate scenes,
and control Houdini in real-time. Designed for production stability.

FEATURES:
• Thread-safe command processing with FIFO guarantee
• Deterministic command ordering via sequence numbers
• WebSocket heartbeat/keepalive for connection stability
• USD API direct access (no encoded parameter fragility)
• Protocol versioning for forward compatibility
• Graceful shutdown and reconnection handling

USAGE:
    from synapse import create_panel
    panel = create_panel()

LICENSE: MIT
AUTHOR: Joe Ibrahim
WEBSITE: https://github.com/yourusername/synapse
"""

__title__ = "Synapse"
__version__ = "2.2.0"  # Circuit breaker fix + flexible parameter names
__author__ = "Joe Ibrahim"
__license__ = "MIT"
__product__ = "Synapse - AI ↔ Houdini Bridge"

import hou
import json
import threading
import queue
import time
import traceback
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple, Callable, Set
from dataclasses import dataclass, field, asdict
from enum import Enum
from collections import OrderedDict
from abc import ABC, abstractmethod
from PySide6 import QtWidgets, QtCore, QtGui

# Protocol version for compatibility checking
PROTOCOL_VERSION = "2.1.0"
HEARTBEAT_INTERVAL = 30.0
COMMAND_TIMEOUT = 60.0
MAX_PENDING_COMMANDS = 100

# Optional websockets import
try:
    from websockets.sync.server import serve
    from websockets.exceptions import ConnectionClosed
    WEBSOCKETS_AVAILABLE = True
except ImportError:
    WEBSOCKETS_AVAILABLE = False

# Import resilience layer
try:
    from .resilience import (
        RateLimiter,
        CircuitBreaker,
        CircuitBreakerConfig,
        PortManager,
        Watchdog,
        BackpressureController,
        HealthMonitor,
        BackpressureLevel
    )
    RESILIENCE_AVAILABLE = True
except ImportError:
    RESILIENCE_AVAILABLE = False
    print("[Synapse] Warning: Resilience module not available")

# Import Engram bridge
try:
    from .engram_bridge import EngramBridge, get_bridge
    ENGRAM_AVAILABLE = True
except ImportError:
    ENGRAM_AVAILABLE = False
    print("[Synapse] Warning: Engram bridge not available")


# =============================================================================
# HOUDINI-NATIVE STYLING
# =============================================================================
# Both Synapse and Engram inherit Houdini's native Qt theme.
# Only minimal overrides for branding elements (headers).
# This ensures the panels feel like native Houdini tools.


# =============================================================================
# COMMAND TYPES AND PROTOCOL
# =============================================================================

class CommandType(Enum):
    """Command types for the Synapse protocol"""
    # Node operations
    CREATE_NODE = "create_node"
    DELETE_NODE = "delete_node"
    MODIFY_NODE = "modify_node"
    CONNECT_NODES = "connect_nodes"
    
    # Scene operations
    GET_SCENE_INFO = "get_scene_info"
    GET_SELECTION = "get_selection"
    SET_SELECTION = "set_selection"
    
    # Parameter operations
    GET_PARM = "get_parm"
    SET_PARM = "set_parm"
    
    # Execution
    EXECUTE_PYTHON = "execute_python"
    EXECUTE_VEX = "execute_vex"
    
    # USD/Solaris operations
    CREATE_USD_PRIM = "create_usd_prim"
    MODIFY_USD_PRIM = "modify_usd_prim"
    GET_STAGE_INFO = "get_stage_info"
    SET_USD_ATTRIBUTE = "set_usd_attribute"
    GET_USD_ATTRIBUTE = "get_usd_attribute"
    
    # Utility
    PING = "ping"
    GET_NODE_TYPES = "get_node_types"
    GET_HELP = "get_help"
    GET_HEALTH = "get_health"

    # Engram (Memory) operations
    ENGRAM_CONTEXT = "engram_context"
    ENGRAM_SEARCH = "engram_search"
    ENGRAM_ADD = "engram_add"
    ENGRAM_DECIDE = "engram_decide"
    ENGRAM_RECALL = "engram_recall"

    # Protocol
    RESPONSE = "response"
    ERROR = "error"
    HEARTBEAT = "heartbeat"
    BACKPRESSURE = "backpressure"


@dataclass
class SynapseCommand:
    """Command structure for Synapse communication"""
    type: str
    id: str
    payload: Dict[str, Any] = field(default_factory=dict)
    sequence: int = 0
    timestamp: float = field(default_factory=time.time)
    protocol_version: str = PROTOCOL_VERSION
    
    def to_json(self) -> str:
        return json.dumps(asdict(self))
    
    @classmethod
    def from_json(cls, data: str) -> 'SynapseCommand':
        parsed = json.loads(data)
        return cls(
            type=parsed.get("type", ""),
            id=parsed.get("id", ""),
            payload=parsed.get("payload", {}),
            sequence=parsed.get("sequence", 0),
            timestamp=parsed.get("timestamp", time.time()),
            protocol_version=parsed.get("protocol_version", "1.0.0")
        )


@dataclass
class SynapseResponse:
    """Response structure for Synapse communication"""
    id: str
    success: bool
    data: Any = None
    error: Optional[str] = None
    sequence: int = 0
    timestamp: float = field(default_factory=time.time)
    protocol_version: str = PROTOCOL_VERSION
    
    def to_json(self) -> str:
        return json.dumps(asdict(self))


# =============================================================================
# DETERMINISTIC COMMAND PROCESSOR
# =============================================================================

class DeterministicCommandQueue:
    """
    Thread-safe command queue with FIFO ordering guarantee.
    Commands are processed in strict sequence order.
    """
    
    def __init__(self, max_size: int = MAX_PENDING_COMMANDS):
        self._pending: OrderedDict[str, Tuple[SynapseCommand, Any]] = OrderedDict()
        self._lock = threading.RLock()
        self._sequence_counter = 0
        self._max_size = max_size
        self._condition = threading.Condition(self._lock)
    
    def enqueue(self, command: SynapseCommand, client: Any) -> int:
        """Add command with guaranteed sequence number."""
        with self._lock:
            if len(self._pending) >= self._max_size:
                self._evict_oldest()
            
            seq = self._sequence_counter
            self._sequence_counter += 1
            command.sequence = seq
            
            key = f"{seq}:{command.id}"
            self._pending[key] = (command, client)
            
            self._condition.notify_all()
            return seq
    
    def dequeue(self, timeout: float = 0.1) -> Optional[Tuple[SynapseCommand, Any]]:
        """Get next command in FIFO order."""
        with self._condition:
            if not self._pending:
                self._condition.wait(timeout=timeout)
                if not self._pending:
                    return None
            
            key, value = self._pending.popitem(last=False)
            return value
    
    def _evict_oldest(self):
        if self._pending:
            key, (cmd, client) = self._pending.popitem(last=False)
            print(f"[Synapse] Evicted command {cmd.id} due to queue overflow")
    
    def size(self) -> int:
        with self._lock:
            return len(self._pending)
    
    def clear(self):
        with self._lock:
            self._pending.clear()


class ResponseDeliveryQueue:
    """Thread-safe queue for delivering responses to clients"""
    
    def __init__(self):
        self._responses: Dict[Any, List[SynapseResponse]] = {}
        self._lock = threading.Lock()
    
    def enqueue(self, response: SynapseResponse, client: Any):
        with self._lock:
            if client not in self._responses:
                self._responses[client] = []
            self._responses[client].append(response)
    
    def get_responses(self, client: Any) -> List[SynapseResponse]:
        with self._lock:
            responses = self._responses.pop(client, [])
            return responses
    
    def has_responses(self, client: Any) -> bool:
        with self._lock:
            return client in self._responses and len(self._responses[client]) > 0


# =============================================================================
# COMMAND HANDLERS
# =============================================================================

class CommandHandlerRegistry:
    """Registry for command handlers with validation"""
    
    def __init__(self):
        self._handlers: Dict[str, Callable] = {}
        self._validators: Dict[str, Callable] = {}
    
    def register(self, command_type: str, handler: Callable, validator: Optional[Callable] = None):
        self._handlers[command_type] = handler
        if validator:
            self._validators[command_type] = validator
    
    def validate(self, command: SynapseCommand) -> Optional[str]:
        validator = self._validators.get(command.type)
        if validator:
            try:
                return validator(command.payload)
            except Exception as e:
                return f"Validation error: {e}"
        return None
    
    def execute(self, command: SynapseCommand) -> SynapseResponse:
        handler = self._handlers.get(command.type)
        
        if not handler:
            return SynapseResponse(
                id=command.id,
                success=False,
                error=f"Unknown command type: {command.type}",
                sequence=command.sequence
            )
        
        validation_error = self.validate(command)
        if validation_error:
            return SynapseResponse(
                id=command.id,
                success=False,
                error=validation_error,
                sequence=command.sequence
            )
        
        try:
            result = handler(command.payload)
            return SynapseResponse(
                id=command.id,
                success=True,
                data=result,
                sequence=command.sequence
            )
        except Exception as e:
            return SynapseResponse(
                id=command.id,
                success=False,
                error=f"{type(e).__name__}: {str(e)}",
                sequence=command.sequence
            )


class SynapseHandler:
    """Handles Synapse commands with Houdini API using USD API directly."""

    def __init__(self):
        self.registry = CommandHandlerRegistry()
        self._register_handlers()
        self._register_radiant_tools()

    def _register_radiant_tools(self):
        """Register RadiantSuite tool commands.

        Note: Aurora and Spectrum have been moved to _archive/.
        This hook remains for future tool integrations.
        """
        pass

    def _register_handlers(self):
        # Node operations
        self.registry.register(CommandType.CREATE_NODE.value, self._handle_create_node, self._validate_create_node)
        self.registry.register(CommandType.DELETE_NODE.value, self._handle_delete_node, lambda p: None if "path" in p else "Missing 'path'")
        self.registry.register(CommandType.MODIFY_NODE.value, self._handle_modify_node)
        self.registry.register(CommandType.CONNECT_NODES.value, self._handle_connect_nodes)
        
        # Scene operations
        self.registry.register(CommandType.GET_SCENE_INFO.value, self._handle_get_scene_info)
        self.registry.register(CommandType.GET_SELECTION.value, self._handle_get_selection)
        self.registry.register(CommandType.SET_SELECTION.value, self._handle_set_selection)
        
        # Parameter operations
        self.registry.register(CommandType.GET_PARM.value, self._handle_get_parm)
        self.registry.register(CommandType.SET_PARM.value, self._handle_set_parm)
        
        # Execution
        self.registry.register(CommandType.EXECUTE_PYTHON.value, self._handle_execute_python)
        
        # USD operations
        self.registry.register(CommandType.CREATE_USD_PRIM.value, self._handle_create_usd_prim)
        self.registry.register(CommandType.GET_STAGE_INFO.value, self._handle_get_stage_info)
        self.registry.register(CommandType.SET_USD_ATTRIBUTE.value, self._handle_set_usd_attribute)
        self.registry.register(CommandType.GET_USD_ATTRIBUTE.value, self._handle_get_usd_attribute)
        
        # Utility
        self.registry.register(CommandType.PING.value, self._handle_ping)
        self.registry.register(CommandType.GET_NODE_TYPES.value, self._handle_get_node_types)
        self.registry.register(CommandType.GET_HELP.value, self._handle_get_help)

        # Engram (Memory) operations
        if ENGRAM_AVAILABLE:
            self.registry.register(CommandType.ENGRAM_CONTEXT.value, self._handle_engram_context)
            self.registry.register(CommandType.ENGRAM_SEARCH.value, self._handle_engram_search)
            self.registry.register(CommandType.ENGRAM_ADD.value, self._handle_engram_add)
            self.registry.register(CommandType.ENGRAM_DECIDE.value, self._handle_engram_decide)
            self.registry.register(CommandType.ENGRAM_RECALL.value, self._handle_engram_recall)
            print("[Synapse] Engram commands registered")
    
    def handle(self, command: SynapseCommand) -> SynapseResponse:
        return self.registry.execute(command)
    
    def _validate_create_node(self, payload: Dict) -> Optional[str]:
        required = ["parent", "type"]
        missing = [k for k in required if k not in payload]
        if missing:
            return f"Missing required fields: {missing}"
        parent = hou.node(payload["parent"])
        if not parent:
            return f"Parent node not found: {payload['parent']}"
        return None
    
    def _handle_create_node(self, payload: Dict) -> Dict:
        parent_path = payload["parent"]
        node_type = payload["type"]
        name = payload.get("name")
        position = payload.get("position")
        parameters = payload.get("parameters", {})
        
        parent = hou.node(parent_path)
        node = parent.createNode(node_type, name) if name else parent.createNode(node_type)
        
        if position:
            node.setPosition(hou.Vector2(position[0], position[1]))
        
        for parm_name, value in parameters.items():
            parm = node.parm(parm_name)
            if parm:
                parm.set(value)
            else:
                pt = node.parmTuple(parm_name)
                if pt and isinstance(value, (list, tuple)):
                    pt.set(value)
        
        node.moveToGoodPosition()
        return {"path": node.path(), "name": node.name(), "type": node.type().name()}
    
    def _handle_delete_node(self, payload: Dict) -> Dict:
        path = payload["path"]
        node = hou.node(path)
        if not node:
            raise ValueError(f"Node not found: {path}")
        node.destroy()
        return {"deleted": path}
    
    def _handle_modify_node(self, payload: Dict) -> Dict:
        path = payload["path"]
        parameters = payload.get("parameters", {})
        node = hou.node(path)
        if not node:
            raise ValueError(f"Node not found: {path}")
        
        modified = []
        for parm_name, value in parameters.items():
            parm = node.parm(parm_name)
            if parm:
                parm.set(value)
                modified.append(parm_name)
            else:
                pt = node.parmTuple(parm_name)
                if pt and isinstance(value, (list, tuple)):
                    pt.set(value)
                    modified.append(parm_name)
        return {"modified": modified}
    
    def _handle_connect_nodes(self, payload: Dict) -> Dict:
        # Accept both naming conventions: source/target OR from_node/to_node
        source_path = payload.get("source") or payload.get("from_node")
        target_path = payload.get("target") or payload.get("to_node")

        if not source_path:
            raise ValueError("Missing 'source' or 'from_node' in payload")
        if not target_path:
            raise ValueError("Missing 'target' or 'to_node' in payload")

        source = hou.node(source_path)
        target = hou.node(target_path)
        if not source:
            raise ValueError(f"Source not found: {source_path}")
        if not target:
            raise ValueError(f"Target not found: {target_path}")

        # Accept both naming conventions for input/output indices
        target_input = payload.get("target_input") or payload.get("to_input", 0)
        source_output = payload.get("source_output") or payload.get("from_output", 0)

        target.setInput(target_input, source, source_output)
        return {"connected": True, "source": source_path, "target": target_path}
    
    def _handle_get_scene_info(self, payload: Dict) -> Dict:
        root_path = payload.get("root", "/")
        depth = payload.get("depth", 2)
        
        def get_node_tree(node: hou.Node, current_depth: int) -> Dict:
            info = {
                "path": node.path(),
                "name": node.name(),
                "type": node.type().name(),
                "category": node.type().category().name(),
                "children": []
            }
            if current_depth < depth:
                for child in node.children():
                    info["children"].append(get_node_tree(child, current_depth + 1))
            return info
        
        root = hou.node(root_path)
        if not root:
            raise ValueError(f"Root not found: {root_path}")
        return get_node_tree(root, 0)
    
    def _handle_get_selection(self, payload: Dict) -> Dict:
        return {"selected": [{"path": n.path(), "name": n.name(), "type": n.type().name()} for n in hou.selectedNodes()]}
    
    def _handle_set_selection(self, payload: Dict) -> Dict:
        paths = payload.get("paths", [])
        if payload.get("clear", True):
            hou.clearAllSelected()
        selected = []
        for path in paths:
            node = hou.node(path)
            if node:
                node.setSelected(True)
                selected.append(path)
        return {"selected": selected}
    
    def _handle_get_parm(self, payload: Dict) -> Dict:
        node = hou.node(payload["path"])
        if not node:
            raise ValueError(f"Node not found: {payload['path']}")
        
        parm = node.parm(payload["parm"])
        if parm:
            return {"value": parm.eval(), "type": str(parm.parmTemplate().type()), "is_expression": parm.isExpression()}
        
        pt = node.parmTuple(payload["parm"])
        if pt:
            return {"value": list(pt.eval()), "type": str(pt.parmTemplate().type()), "is_expression": any(p.isExpression() for p in pt)}
        
        raise ValueError(f"Parameter not found: {payload['parm']}")
    
    def _handle_set_parm(self, payload: Dict) -> Dict:
        # Accept both 'path' and 'node' parameter names
        node_path = payload.get("path") or payload.get("node")
        if not node_path:
            raise ValueError("Missing 'path' or 'node' in payload")

        node = hou.node(node_path)
        if not node:
            raise ValueError(f"Node not found: {node_path}")

        parm_name = payload.get("parm") or payload.get("parameter")
        if not parm_name:
            raise ValueError("Missing 'parm' or 'parameter' in payload")

        value = payload["value"]

        parm = node.parm(parm_name)
        if parm:
            if payload.get("expression", False):
                parm.setExpression(value)
            else:
                parm.set(value)
            return {"set": parm_name, "value": value, "node": node_path}

        pt = node.parmTuple(parm_name)
        if pt and isinstance(value, (list, tuple)):
            pt.set(value)
            return {"set": parm_name, "value": value, "node": node_path}

        raise ValueError(f"Parameter not found: {parm_name} on {node_path}")
    
    def _handle_execute_python(self, payload: Dict) -> Dict:
        code = payload["code"]
        context = payload.get("context", {})
        namespace = {"hou": hou, "__builtins__": __builtins__, "__result__": None, "result": None, **context}
        exec(code, namespace)

        # Check both 'result' and '__result__' variable names for flexibility
        result = namespace.get("result") or namespace.get("__result__")

        # Convert Houdini objects to serializable format
        if result is not None:
            if hasattr(result, "path"):
                result = {"path": result.path(), "name": result.name() if hasattr(result, "name") else None}
            elif hasattr(result, "__iter__") and not isinstance(result, (str, dict)):
                result = list(result)

        return {"result": result}
    
    def _handle_create_usd_prim(self, payload: Dict) -> Dict:
        """Create USD prim using USD API directly for H21 stability."""
        parent = hou.node(payload["parent"])
        if not parent:
            raise ValueError(f"Parent LOP not found: {payload['parent']}")
        
        prim_type = payload["type"]
        prim_path = payload["path"]
        attributes = payload.get("attributes", {})
        
        python_lop = parent.createNode("pythonscript", f"create_{prim_path.split('/')[-1]}")
        
        code_lines = [
            "from pxr import Usd, UsdGeom, UsdLux, Sdf, Gf",
            "",
            "node = hou.pwd()",
            "stage = node.editableStage()",
            f'prim_path = "{prim_path}"',
            f'prim_type = "{prim_type}"',
            "",
            "# Create prim using USD API",
            "prim_map = {",
            "    'Xform': lambda: stage.DefinePrim(prim_path, 'Xform'),",
            "    'Scope': lambda: stage.DefinePrim(prim_path, 'Scope'),",
            "    'Mesh': lambda: UsdGeom.Mesh.Define(stage, prim_path),",
            "    'RectLight': lambda: UsdLux.RectLight.Define(stage, prim_path),",
            "    'DiskLight': lambda: UsdLux.DiskLight.Define(stage, prim_path),",
            "    'SphereLight': lambda: UsdLux.SphereLight.Define(stage, prim_path),",
            "    'DistantLight': lambda: UsdLux.DistantLight.Define(stage, prim_path),",
            "    'DomeLight': lambda: UsdLux.DomeLight.Define(stage, prim_path),",
            "    'CylinderLight': lambda: UsdLux.CylinderLight.Define(stage, prim_path),",
            "}",
            "creator = prim_map.get(prim_type, lambda: stage.DefinePrim(prim_path, prim_type))",
            "prim = creator()",
        ]
        
        if attributes:
            code_lines.append("")
            code_lines.append("prim_obj = stage.GetPrimAtPath(prim_path)")
            for attr_name, attr_value in attributes.items():
                if isinstance(attr_value, (list, tuple)) and len(attr_value) == 3:
                    code_lines.append(f"prim_obj.GetAttribute('{attr_name}').Set(Gf.Vec3f{tuple(attr_value)})")
                elif isinstance(attr_value, float):
                    code_lines.append(f"prim_obj.GetAttribute('{attr_name}').Set({attr_value})")
                elif isinstance(attr_value, bool):
                    code_lines.append(f"prim_obj.GetAttribute('{attr_name}').Set({attr_value})")
                else:
                    code_lines.append(f"prim_obj.GetAttribute('{attr_name}').Set({repr(attr_value)})")
        
        python_lop.parm("python").set("\n".join(code_lines))
        python_lop.moveToGoodPosition()
        
        return {"prim_path": prim_path, "prim_type": prim_type, "lop_node": python_lop.path()}
    
    def _handle_set_usd_attribute(self, payload: Dict) -> Dict:
        lop_node = hou.node(payload["lop_path"])
        if not lop_node:
            raise ValueError(f"LOP node not found: {payload['lop_path']}")
        
        stage = lop_node.stage()
        if not stage:
            raise ValueError(f"No stage at: {payload['lop_path']}")
        
        prim = stage.GetPrimAtPath(payload["prim_path"])
        if not prim:
            raise ValueError(f"Prim not found: {payload['prim_path']}")
        
        attr = prim.GetAttribute(payload["attribute"])
        if not attr:
            raise ValueError(f"Attribute not found: {payload['attribute']}")
        
        attr.Set(payload["value"])
        return {"prim_path": payload["prim_path"], "attribute": payload["attribute"], "value": payload["value"]}
    
    def _handle_get_usd_attribute(self, payload: Dict) -> Dict:
        lop_node = hou.node(payload["lop_path"])
        if not lop_node:
            raise ValueError(f"LOP node not found: {payload['lop_path']}")
        
        stage = lop_node.stage()
        if not stage:
            raise ValueError(f"No stage at: {payload['lop_path']}")
        
        prim = stage.GetPrimAtPath(payload["prim_path"])
        if not prim:
            raise ValueError(f"Prim not found: {payload['prim_path']}")
        
        attr = prim.GetAttribute(payload["attribute"])
        if not attr:
            raise ValueError(f"Attribute not found: {payload['attribute']}")
        
        value = attr.Get()
        if hasattr(value, "__iter__") and not isinstance(value, str):
            value = list(value)
        
        return {"prim_path": payload["prim_path"], "attribute": payload["attribute"], "value": value, "type": str(attr.GetTypeName())}
    
    def _handle_get_stage_info(self, payload: Dict) -> Dict:
        lop_path = payload.get("lop_path", "/stage")
        prim_limit = payload.get("prim_limit", 100)
        prim_filter = payload.get("filter", None)
        include_attributes = payload.get("include_attributes", False)
        
        lop_node = hou.node(lop_path)
        if not lop_node:
            stage_net = hou.node("/stage")
            if stage_net:
                children = list(stage_net.children())
                if children:
                    lop_node = children[-1]
        
        if not lop_node:
            return {"prims": [], "error": "No stage found"}
        
        stage = lop_node.stage()
        if not stage:
            return {"prims": [], "error": "Stage not available"}
        
        prims = []
        count = 0
        
        for prim in stage.Traverse():
            if count >= prim_limit:
                break
            if prim_filter and prim_filter not in str(prim.GetPath()):
                continue
            
            prim_info = {"path": str(prim.GetPath()), "type": prim.GetTypeName(), "active": prim.IsActive(), "has_payload": prim.HasPayload()}
            
            if include_attributes:
                prim_info["attributes"] = [{"name": attr.GetName(), "type": str(attr.GetTypeName())} for attr in prim.GetAttributes()[:20]]
            
            prims.append(prim_info)
            count += 1
        
        return {"prims": prims, "count": len(prims), "truncated": count >= prim_limit, "stage_root": str(stage.GetPseudoRoot().GetPath())}
    
    def _handle_ping(self, payload: Dict) -> Dict:
        return {
            "pong": True,
            "product": __product__,
            "protocol_version": PROTOCOL_VERSION,
            "houdini_version": hou.applicationVersionString(),
            "timestamp": time.time()
        }
    
    def _handle_get_node_types(self, payload: Dict) -> Dict:
        category_name = payload.get("category", "Sop")
        filter_text = payload.get("filter", "")
        
        try:
            category = hou.nodeTypeCategories()[category_name]
        except KeyError:
            raise ValueError(f"Unknown category: {category_name}. Available: {list(hou.nodeTypeCategories().keys())}")
        
        node_types = []
        for name, node_type in category.nodeTypes().items():
            if filter_text and filter_text.lower() not in name.lower():
                continue
            node_types.append({"name": name, "label": node_type.description(), "hidden": node_type.hidden()})
        
        return {"node_types": node_types[:100]}
    
    def _handle_get_help(self, payload: Dict) -> Dict:
        return {
            "product": __product__,
            "version": __version__,
            "protocol_version": PROTOCOL_VERSION,
            "commands": [ct.value for ct in CommandType],
            "examples": {
                "create_node": {"type": "create_node", "id": "1", "payload": {"parent": "/obj", "type": "geo", "name": "my_geo"}},
                "create_usd_prim": {"type": "create_usd_prim", "id": "2", "payload": {"parent": "/stage", "type": "RectLight", "path": "/lights/key", "attributes": {"inputs:intensity": 1.5}}},
            }
        }

    # =========================================================================
    # ENGRAM (Memory) Handlers
    # =========================================================================

    def _handle_engram_context(self, payload: Dict) -> Dict:
        """Get project context from Engram."""
        if not ENGRAM_AVAILABLE:
            return {"error": "Engram not available", "context": None}
        from synapse.engram_bridge import get_bridge
        bridge = get_bridge()
        return bridge.handle_memory_context(payload)

    def _handle_engram_search(self, payload: Dict) -> Dict:
        """Search memories in Engram."""
        if not ENGRAM_AVAILABLE:
            return {"error": "Engram not available", "results": []}
        from synapse.engram_bridge import get_bridge
        bridge = get_bridge()
        return bridge.handle_memory_search(payload)

    def _handle_engram_add(self, payload: Dict) -> Dict:
        """Add a memory to Engram."""
        if not ENGRAM_AVAILABLE:
            return {"error": "Engram not available", "created": False}
        from synapse.engram_bridge import get_bridge
        bridge = get_bridge()
        return bridge.handle_memory_add(payload)

    def _handle_engram_decide(self, payload: Dict) -> Dict:
        """Record a decision in Engram with reasoning."""
        if not ENGRAM_AVAILABLE:
            return {"error": "Engram not available", "recorded": False}
        from synapse.engram_bridge import get_bridge
        bridge = get_bridge()
        return bridge.handle_memory_decide(payload)

    def _handle_engram_recall(self, payload: Dict) -> Dict:
        """Recall past decisions related to a query."""
        if not ENGRAM_AVAILABLE:
            return {"error": "Engram not available", "found": False}
        from synapse.engram_bridge import get_bridge
        bridge = get_bridge()
        return bridge.handle_memory_recall(payload)


# =============================================================================
# WEBSOCKET SERVER
# =============================================================================

class SynapseServer:
    """WebSocket server with heartbeat, graceful shutdown, and resilience layer."""

    def __init__(self, host: str = "localhost", port: int = 9999, handler: SynapseHandler = None):
        self.host = host
        self.port = port
        self.handler = handler or SynapseHandler()

        self.command_queue = DeterministicCommandQueue()
        self.response_queue = ResponseDeliveryQueue()

        self._server = None
        self._server_thread: Optional[threading.Thread] = None
        self._clients: Set[Any] = set()
        self._clients_lock = threading.Lock()
        self._running = False
        self._shutdown_event = threading.Event()
        self._last_heartbeat: Dict[Any, float] = {}

        # Resilience components
        if RESILIENCE_AVAILABLE:
            self.rate_limiter = RateLimiter(
                tokens_per_second=100.0,  # Increased for rapid AI commands
                bucket_size=200,          # Larger burst allowance
                per_client_bucket=50      # Per-client burst allowance
            )
            self.circuit_breaker = CircuitBreaker(
                name="synapse",
                config=CircuitBreakerConfig(
                    failure_threshold=20,      # Much higher - only trip on persistent issues
                    timeout_seconds=10.0,      # Faster recovery
                    success_threshold=2,       # Quick recovery from half-open
                    half_open_max_calls=10     # More test calls in half-open
                )
            )
            self.port_manager = PortManager(
                primary_port=port,
                backup_ports=[port - 1, port - 2, port - 3]
            )
            self.watchdog = Watchdog(
                heartbeat_interval=1.0,
                freeze_threshold=5.0,
                on_freeze=self._on_main_thread_freeze,
                on_recover=self._on_main_thread_recover
            )
            self.backpressure = BackpressureController()
            self.health_monitor = HealthMonitor(
                rate_limiter=self.rate_limiter,
                circuit_breaker=self.circuit_breaker,
                port_manager=self.port_manager,
                watchdog=self.watchdog,
                backpressure=self.backpressure
            )
            self._resilience_enabled = True
        else:
            self._resilience_enabled = False

        # Stats tracking
        self._commands_succeeded = 0
        self._commands_failed = 0
        self._commands_rejected = 0

    def _on_main_thread_freeze(self, duration: float):
        """Called when watchdog detects main thread freeze."""
        print(f"[Synapse] WARNING: Main thread frozen for {duration:.1f}s")
        if self._resilience_enabled:
            self.circuit_breaker.force_open()

    def _on_main_thread_recover(self):
        """Called when main thread recovers from freeze."""
        print("[Synapse] Main thread recovered")
    
    def start(self):
        if self._running:
            return

        self._running = True
        self._shutdown_event.clear()

        # Start watchdog if resilience is enabled
        if self._resilience_enabled:
            self.watchdog.start()
            self.port_manager.mark_active(self.port)

        self._server_thread = threading.Thread(target=self._run_server, daemon=True, name="Synapse-Server")
        self._server_thread.start()
    
    def stop(self):
        """Gracefully stop the server."""
        print("[Synapse] Stopping server...")
        self._running = False
        self._shutdown_event.set()

        # Close all client connections
        with self._clients_lock:
            for client in list(self._clients):
                try:
                    client.close()
                except Exception:
                    pass
            self._clients.clear()
            self._last_heartbeat.clear()

        # Shutdown server
        if self._server:
            try:
                self._server.shutdown()
            except Exception:
                pass
            self._server = None

        # Wait for server thread to exit
        if self._server_thread and self._server_thread.is_alive():
            self._server_thread.join(timeout=2.0)
            if self._server_thread.is_alive():
                print("[Synapse] Warning: Server thread did not exit cleanly")

        # Clear command queue
        self.command_queue.clear()

        # Stop watchdog
        if self._resilience_enabled:
            self.watchdog.stop()

        print("[Synapse] Server stopped")
    
    def _run_server(self):
        try:
            # websockets sync API - serve_forever() handles connections
            with serve(self._handle_client, self.host, self.port) as server:
                self._server = server
                print(f"[Synapse] Server started on ws://{self.host}:{self.port}")
                # serve_forever() blocks and processes connections
                # It will exit when server.shutdown() is called
                server.serve_forever()
        except OSError as e:
            # Port already in use or permission denied
            print(f"[Synapse] Server bind error: {e}")
            print(f"[Synapse] Port {self.port} may already be in use")
        except Exception as e:
            if self._running:  # Only log if not intentionally shutting down
                print(f"[Synapse] Server error: {e}")
                traceback.print_exc()
        finally:
            self._running = False
            print("[Synapse] Server thread exited")
    
    def _handle_client(self, websocket):
        client_id = id(websocket)

        with self._clients_lock:
            self._clients.add(websocket)
            self._last_heartbeat[websocket] = time.time()

        print(f"[Synapse] Client connected: {client_id}")

        try:
            # Start heartbeat monitoring in background
            heartbeat_thread = threading.Thread(
                target=self._heartbeat_loop,
                args=(websocket,),
                daemon=True,
                name=f"Synapse-Heartbeat-{client_id}"
            )
            heartbeat_thread.start()

            for message in websocket:
                if not self._running:
                    break

                try:
                    command = SynapseCommand.from_json(message)

                    # Handle heartbeat immediately (no rate limiting)
                    if command.type == CommandType.HEARTBEAT.value:
                        self._last_heartbeat[websocket] = time.time()
                        response = SynapseResponse(id=command.id, success=True, data={"heartbeat": "ack"})
                        websocket.send(response.to_json())
                        continue

                    # Handle health check immediately (no rate limiting)
                    if command.type == CommandType.GET_HEALTH.value:
                        health_data = self.get_health()
                        health_data["stats"] = self.get_stats()
                        response = SynapseResponse(id=command.id, success=True, data=health_data)
                        websocket.send(response.to_json())
                        continue

                    # Check rate limiting and circuit breaker before accepting command
                    if self._resilience_enabled:
                        # Check rate limit
                        allowed, rate_info = self.rate_limiter.acquire(str(client_id))
                        if not allowed:
                            self._commands_rejected += 1
                            response = SynapseResponse(
                                id=command.id,
                                success=False,
                                error="Rate limit exceeded",
                                data={
                                    "type": CommandType.BACKPRESSURE.value,
                                    **rate_info
                                }
                            )
                            websocket.send(response.to_json())
                            continue

                        # Check circuit breaker
                        can_exec, circuit_info = self.circuit_breaker.can_execute()
                        if not can_exec:
                            self._commands_rejected += 1
                            response = SynapseResponse(
                                id=command.id,
                                success=False,
                                error="Service temporarily unavailable (circuit open)",
                                data={
                                    "type": CommandType.BACKPRESSURE.value,
                                    **circuit_info
                                }
                            )
                            websocket.send(response.to_json())
                            continue

                        # Check backpressure (reject non-critical under high load)
                        is_critical = command.type in ("ping", "get_health", "heartbeat")
                        if not self.backpressure.should_accept(is_critical):
                            self._commands_rejected += 1
                            response = SynapseResponse(
                                id=command.id,
                                success=False,
                                error="Server under heavy load, try again later",
                                data={
                                    "type": CommandType.BACKPRESSURE.value,
                                    "level": self.backpressure.level.value,
                                    "retry_after": 1.0
                                }
                            )
                            websocket.send(response.to_json())
                            continue

                    self.command_queue.enqueue(command, websocket)

                    # Wait for response with timeout
                    start_time = time.time()
                    while time.time() - start_time < COMMAND_TIMEOUT:
                        if not self._running:
                            break
                        if self.response_queue.has_responses(websocket):
                            for response in self.response_queue.get_responses(websocket):
                                try:
                                    websocket.send(response.to_json())
                                except Exception:
                                    pass  # Connection may have closed
                            break
                        time.sleep(0.01)

                except json.JSONDecodeError as e:
                    error_response = SynapseResponse(id="unknown", success=False, error=f"Invalid JSON: {e}")
                    try:
                        websocket.send(error_response.to_json())
                    except Exception:
                        pass

        except ConnectionClosed:
            print(f"[Synapse] Client disconnected: {client_id}")
        except Exception as e:
            print(f"[Synapse] Client error: {type(e).__name__}: {e}")
        finally:
            with self._clients_lock:
                self._clients.discard(websocket)
                self._last_heartbeat.pop(websocket, None)

            # Clean up rate limiter tracking for this client
            if self._resilience_enabled:
                self.rate_limiter.remove_client(str(client_id))
    
    def _heartbeat_loop(self, websocket):
        """Heartbeat monitoring loop - checks if client is responsive."""
        while self._running:
            try:
                time.sleep(HEARTBEAT_INTERVAL)

                # Check if websocket still in clients
                with self._clients_lock:
                    if websocket not in self._clients:
                        break

                last_beat = self._last_heartbeat.get(websocket, 0)
                if time.time() - last_beat > HEARTBEAT_INTERVAL * 2:
                    print(f"[Synapse] Client heartbeat timeout")
                    try:
                        websocket.close()
                    except Exception:
                        pass
                    break

                # Skip ping() - websockets 16.0 handles keepalive internally
                # The client heartbeat messages are sufficient

            except Exception:
                break
    
    def process_commands(self) -> int:
        """Process pending commands with resilience checks.

        Error Classification:
        - USER_ERROR: ValueError, KeyError, AttributeError, hou.OperationFailed
          These are user/validation errors - DO NOT trip circuit breaker
        - SERVICE_ERROR: TimeoutError, threading errors, Houdini crashes
          These are service failures - DO trip circuit breaker
        """
        processed = 0

        # Error types that should NOT trip the circuit breaker
        USER_ERROR_TYPES = (
            ValueError,
            KeyError,
            AttributeError,
            TypeError,
            IndexError,
            NameError,
        )

        # Send watchdog heartbeat (proves main thread is responsive)
        if self._resilience_enabled:
            self.watchdog.heartbeat()

            # Update backpressure based on queue size
            queue_size = self.command_queue.size()
            avg_latency = 0.0
            if hasattr(self.watchdog, 'get_stats'):
                stats = self.watchdog.get_stats()
                avg_latency = stats.get('avg_latency', 0.0)
            self.backpressure.evaluate(queue_size, avg_latency, self.circuit_breaker.state.value)

        # Check circuit breaker before processing
        if self._resilience_enabled:
            can_exec, info = self.circuit_breaker.can_execute()
            if not can_exec:
                # Circuit is open - skip processing this tick
                return 0

        while True:
            item = self.command_queue.dequeue(timeout=0.001)
            if item is None:
                break

            command, client = item

            try:
                response = self.handler.handle(command)

                # Track success/failure - but DON'T trip circuit on user errors
                if self._resilience_enabled:
                    if response.success:
                        # Successful command - record success (helps close circuit)
                        self.circuit_breaker.record_success()
                        self._commands_succeeded += 1
                    else:
                        # Command returned error - this is a USER error, not SERVICE error
                        # DO NOT record as circuit breaker failure
                        self._commands_failed += 1
                        # But DO record success for circuit breaker since service is working
                        self.circuit_breaker.record_success()

                self.response_queue.enqueue(response, client)
                processed += 1

            except USER_ERROR_TYPES as e:
                # User/validation error - service is working, user made a mistake
                # DO NOT trip circuit breaker
                self._commands_failed += 1
                if self._resilience_enabled:
                    # Record as success since service processed the request
                    self.circuit_breaker.record_success()

                error_response = SynapseResponse(
                    id=command.id,
                    success=False,
                    error=f"{type(e).__name__}: {str(e)}",
                    sequence=command.sequence
                )
                self.response_queue.enqueue(error_response, client)
                processed += 1

            except Exception as e:
                # Service error (timeout, threading, crash) - DO trip circuit
                if self._resilience_enabled:
                    self.circuit_breaker.record_failure(e)
                self._commands_failed += 1

                error_response = SynapseResponse(
                    id=command.id,
                    success=False,
                    error=f"Service error: {type(e).__name__}: {str(e)}",
                    sequence=command.sequence
                )
                self.response_queue.enqueue(error_response, client)
                processed += 1
                print(f"[Synapse] SERVICE ERROR (circuit breaker notified): {e}")

        return processed

    def get_health(self) -> Dict:
        """Get system health status."""
        if self._resilience_enabled:
            return self.health_monitor.to_dict()
        return {
            "healthy": self._running,
            "level": "unknown",
            "message": "Resilience layer not available"
        }

    def get_stats(self) -> Dict:
        """Get server statistics."""
        stats = {
            "running": self._running,
            "client_count": self.client_count,
            "queue_size": self.command_queue.size(),
            "commands_succeeded": self._commands_succeeded,
            "commands_failed": self._commands_failed,
            "commands_rejected": self._commands_rejected
        }
        if self._resilience_enabled:
            stats["circuit_state"] = self.circuit_breaker.state.value
            stats["backpressure_level"] = self.backpressure.level.value
            stats["rate_limiter"] = self.rate_limiter.get_stats()
        return stats
    
    @property
    def is_running(self) -> bool:
        return self._running
    
    @property
    def client_count(self) -> int:
        with self._clients_lock:
            return len(self._clients)


# =============================================================================
# QT PANEL
# =============================================================================

class SynapsePanel(QtWidgets.QWidget):
    """Control panel for Synapse"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.server: Optional[SynapseServer] = None
        self._process_timer: Optional[QtCore.QTimer] = None
        self._commands_processed = 0
        self._init_ui()
    
    def _init_ui(self):
        # No custom stylesheet - inherit Houdini's native Qt theme
        self.setWindowTitle(f"{__title__} - AI ↔ Houdini Bridge")
        self.setMinimumSize(300, 250)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        # Header - styled to match Houdini's panel headers
        header = QtWidgets.QLabel("SYNAPSE")
        header.setStyleSheet("font-size: 24px; font-weight: bold;")
        layout.addWidget(header)

        subtitle = QtWidgets.QLabel("AI ↔ Houdini Bridge")
        subtitle.setStyleSheet("color: palette(mid); font-size: 11px;")
        layout.addWidget(subtitle)

        version_label = QtWidgets.QLabel(f"v{__version__} | Protocol {PROTOCOL_VERSION}")
        version_label.setStyleSheet("color: palette(mid); font-size: 9px;")
        layout.addWidget(version_label)
        
        # Status
        status_group = QtWidgets.QGroupBox("Server Status")
        status_layout = QtWidgets.QFormLayout(status_group)
        
        self.status_indicator = QtWidgets.QLabel("○ Stopped")
        self.status_indicator.setStyleSheet("font-weight: bold; color: palette(mid);")
        status_layout.addRow("Status:", self.status_indicator)
        
        self.client_count_label = QtWidgets.QLabel("0")
        status_layout.addRow("Connected Clients:", self.client_count_label)
        
        self.commands_label = QtWidgets.QLabel("0")
        status_layout.addRow("Commands Processed:", self.commands_label)
        
        layout.addWidget(status_group)
        
        # Configuration
        config_group = QtWidgets.QGroupBox("Configuration")
        config_layout = QtWidgets.QFormLayout(config_group)
        
        self.host_input = QtWidgets.QLineEdit("localhost")
        config_layout.addRow("Host:", self.host_input)
        
        self.port_input = QtWidgets.QSpinBox()
        self.port_input.setRange(1024, 65535)
        self.port_input.setValue(9999)
        config_layout.addRow("Port:", self.port_input)
        
        layout.addWidget(config_group)
        
        # Controls
        controls = QtWidgets.QHBoxLayout()
        
        self.start_btn = QtWidgets.QPushButton("▶ Start Server")
        self.start_btn.clicked.connect(self._start_server)
        controls.addWidget(self.start_btn)

        self.stop_btn = QtWidgets.QPushButton("■ Stop Server")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._stop_server)
        controls.addWidget(self.stop_btn)
        
        layout.addLayout(controls)
        
        # Connection URL
        url_group = QtWidgets.QGroupBox("Connection URL")
        url_layout = QtWidgets.QVBoxLayout(url_group)
        
        self.url_label = QtWidgets.QLabel("ws://localhost:9999")
        self.url_label.setStyleSheet("font-family: monospace; padding: 8px; background: palette(base); border: 1px solid palette(mid); border-radius: 3px;")
        self.url_label.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
        url_layout.addWidget(self.url_label)

        copy_btn = QtWidgets.QPushButton("Copy URL")
        copy_btn.clicked.connect(lambda: QtWidgets.QApplication.clipboard().setText(self.url_label.text()))
        url_layout.addWidget(copy_btn)
        
        layout.addWidget(url_group)
        
        # Log
        log_group = QtWidgets.QGroupBox("Activity Log")
        log_layout = QtWidgets.QVBoxLayout(log_group)
        
        self.log_text = QtWidgets.QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(120)
        self.log_text.setStyleSheet("font-family: monospace; font-size: 10px;")
        log_layout.addWidget(self.log_text)

        layout.addWidget(log_group)

        if not WEBSOCKETS_AVAILABLE:
            warning = QtWidgets.QLabel("⚠ websockets library not installed.\nRun: pip install websockets")
            warning.setStyleSheet("color: palette(highlight); font-weight: bold; padding: 10px;")
            layout.addWidget(warning)
            self.start_btn.setEnabled(False)
        
        self._update_url()
    
    def _start_server(self):
        if not WEBSOCKETS_AVAILABLE:
            return
        
        self.server = SynapseServer(self.host_input.text(), self.port_input.value())
        self.server.start()
        
        self._process_timer = QtCore.QTimer(self)
        self._process_timer.timeout.connect(self._process_commands)
        self._process_timer.start(10)
        
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.host_input.setEnabled(False)
        self.port_input.setEnabled(False)
        
        self._update_status()
        self._log("Server started")
    
    def _stop_server(self):
        if self._process_timer:
            self._process_timer.stop()
            self._process_timer = None
        
        if self.server:
            self.server.stop()
            self.server = None
        
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.host_input.setEnabled(True)
        self.port_input.setEnabled(True)
        
        self._update_status()
        self._log("Server stopped")
    
    def _process_commands(self):
        if self.server:
            processed = self.server.process_commands()
            if processed > 0:
                self._commands_processed += processed
                self._log(f"Processed {processed} command(s)")
            self._update_status()
    
    def _update_status(self):
        if self.server and self.server.is_running:
            self.status_indicator.setText("● Running")
            self.status_indicator.setStyleSheet("font-weight: bold; color: #4CAF50;")  # Houdini green
            self.client_count_label.setText(str(self.server.client_count))
        else:
            self.status_indicator.setText("○ Stopped")
            self.status_indicator.setStyleSheet("font-weight: bold; color: palette(mid);")
            self.client_count_label.setText("0")
        
        self.commands_label.setText(str(self._commands_processed))
    
    def _update_url(self):
        self.url_label.setText(f"ws://{self.host_input.text()}:{self.port_input.value()}")
    
    def _log(self, message: str):
        import datetime
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        self.log_text.append(f"[{timestamp}] {message}")
    
    def closeEvent(self, event):
        self._stop_server()
        event.accept()


# =============================================================================
# ENTRY POINT
# =============================================================================

def create_panel():
    """Create and show Synapse panel"""
    panel = SynapsePanel()
    panel.setParent(hou.qt.mainWindow(), QtCore.Qt.Window)
    panel.show()
    return panel


if __name__ == "__main__":
    create_panel()
