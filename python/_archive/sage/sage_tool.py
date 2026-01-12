"""
╔═══════════════════════════════════════════════════════════════════════════════╗
║                                                                               ║
║   ███████╗ █████╗  ██████╗ ███████╗                                           ║
║   ██╔════╝██╔══██╗██╔════╝ ██╔════╝                                           ║
║   ███████╗███████║██║  ███╗█████╗                                             ║
║   ╚════██║██╔══██║██║   ██║██╔══╝                                             ║
║   ███████║██║  ██║╚██████╔╝███████╗                                           ║
║   ╚══════╝╚═╝  ╚═╝ ╚═════╝ ╚══════╝                                           ║
║                                                                               ║
║   AI Assistant for Houdini 21                                                 ║
║   Your wise advisor inside Houdini.                                           ║
║                                                                               ║
╚═══════════════════════════════════════════════════════════════════════════════╝

Sage v2.2.0 | Houdini 21+ | Python 3.9+

Conversational AI assistant with deep Houdini context awareness.
Ask questions, get VEX help, debug nodes, and accelerate your workflow.

FEATURES:
• Atomic context capture (no race conditions)
• Multi-provider LLM support (OpenAI, Anthropic, Google Gemini, Ollama)
• Resilient client with retry and fallback
• Context-aware conversations with scene understanding
• Thread-safe background processing
• Conversation history with token management

USAGE:
    from sage import create_panel
    panel = create_panel()

LICENSE: MIT
AUTHOR: Joe Ibrahim
WEBSITE: https://github.com/yourusername/sage
"""

__title__ = "Sage"
__version__ = "2.2.0"
__author__ = "Joe Ibrahim"
__license__ = "MIT"
__product__ = "Sage - AI Assistant for Houdini"

import hou
import json
import threading
import time
import traceback
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple, Callable
from dataclasses import dataclass, field, asdict
from enum import Enum
from abc import ABC, abstractmethod
from PySide6 import QtWidgets, QtCore, QtGui

# Context limits to prevent explosion
MAX_SELECTED_NODES = 50
MAX_NETWORK_CHILDREN = 100
MAX_STAGE_PRIMS = 200
MAX_PARM_VALUES = 20
MAX_HISTORY = 20
MAX_TOKENS_ESTIMATE = 8000


# =============================================================================
# ENUMS
# =============================================================================

class LLMProvider(Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GOOGLE = "google"
    OLLAMA = "ollama"


class MessageRole(Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


# =============================================================================
# CONTEXT CAPTURE (Atomic - No Race Conditions)
# =============================================================================

@dataclass
class SageContextSnapshot:
    """Atomic snapshot of Houdini state - captured in single pass"""
    selected_nodes: List[Dict[str, Any]] = field(default_factory=list)
    current_network_path: str = ""
    current_network_type: str = ""
    network_children: List[Dict[str, str]] = field(default_factory=list)
    network_connections: List[Dict[str, str]] = field(default_factory=list)
    stage_prims: List[Dict[str, Any]] = field(default_factory=list)
    stage_selected_prims: List[str] = field(default_factory=list)
    houdini_version: str = ""
    hip_file: str = ""
    frame: float = 1.0
    fps: float = 24.0
    captured_at: float = 0.0
    
    def to_prompt_context(self) -> str:
        lines = [
            f"Houdini Version: {self.houdini_version}",
            f"HIP File: {self.hip_file}",
            f"Frame: {self.frame} @ {self.fps} fps",
            f"Current Network: {self.current_network_path} ({self.current_network_type})",
        ]
        
        if self.selected_nodes:
            lines.append(f"\nSelected Nodes ({len(self.selected_nodes)}):")
            for node in self.selected_nodes[:10]:
                lines.append(f"  - {node['path']} ({node['type']})")
                if node.get('parameters'):
                    for parm, val in list(node['parameters'].items())[:5]:
                        lines.append(f"      {parm}: {val}")
        
        if self.stage_prims:
            lines.append(f"\nUSD Stage Prims ({len(self.stage_prims)}):")
            for prim in self.stage_prims[:10]:
                lines.append(f"  - {prim['path']} ({prim['type']})")
        
        return "\n".join(lines)
    
    def to_dict(self) -> Dict:
        return asdict(self)


class AtomicContextExtractor:
    """Extracts Houdini context atomically to prevent race conditions"""
    
    @classmethod
    def capture_context(cls, pane: Optional[hou.Pane] = None) -> SageContextSnapshot:
        """
        CRITICAL: Capture ALL volatile state in a single pass.
        This prevents race conditions where selection changes mid-capture.
        """
        snapshot = SageContextSnapshot(captured_at=time.time())
        
        try:
            with hou.undos.disabler():
                # Capture all volatile state FIRST
                selected_nodes = list(hou.selectedNodes())
                
                current_pane = pane
                if not current_pane:
                    desktop = hou.ui.curDesktop()
                    if desktop:
                        current_pane = desktop.paneTabOfType(hou.paneTabType.NetworkEditor)
                
                current_pwd = None
                if current_pane and hasattr(current_pane, 'pwd'):
                    current_pwd = current_pane.pwd()
                
                current_frame = hou.frame()
                current_fps = hou.fps()
                
                # Now build snapshot from captured state
                snapshot.houdini_version = hou.applicationVersionString()
                snapshot.hip_file = hou.hipFile.path()
                snapshot.frame = current_frame
                snapshot.fps = current_fps
                
                # Process selected nodes
                for node in selected_nodes[:MAX_SELECTED_NODES]:
                    node_info = cls._extract_node_info(node)
                    snapshot.selected_nodes.append(node_info)
                
                # Process current network
                if current_pwd:
                    snapshot.current_network_path = current_pwd.path()
                    snapshot.current_network_type = current_pwd.type().name()
                    
                    children = list(current_pwd.children())[:MAX_NETWORK_CHILDREN]
                    for child in children:
                        snapshot.network_children.append({
                            "name": child.name(),
                            "type": child.type().name(),
                            "path": child.path()
                        })
                    
                    for child in children[:50]:
                        for conn in child.inputConnections():
                            snapshot.network_connections.append({
                                "from": conn.inputNode().path() if conn.inputNode() else "",
                                "to": child.path(),
                                "input_index": conn.inputIndex()
                            })
                
                # Process USD stage if in LOPs
                if current_pwd and current_pwd.type().category().name() == "Lop":
                    cls._extract_stage_info(current_pwd, snapshot)
                
        except Exception as e:
            print(f"[Sage] Context capture error: {e}")
            traceback.print_exc()
        
        return snapshot
    
    @classmethod
    def _extract_node_info(cls, node: hou.Node) -> Dict[str, Any]:
        info = {
            "name": node.name(),
            "path": node.path(),
            "type": node.type().name(),
            "category": node.type().category().name(),
            "parameters": {},
            "inputs": [],
            "outputs": []
        }
        
        # Extract non-default parameters only
        parm_count = 0
        for parm in node.parms():
            if parm_count >= MAX_PARM_VALUES:
                break
            try:
                if not parm.isAtDefault():
                    info["parameters"][parm.name()] = cls._safe_parm_value(parm)
                    parm_count += 1
            except:
                pass
        
        # Input connections
        for i, conn in enumerate(node.inputConnections()):
            if conn.inputNode():
                info["inputs"].append({
                    "index": i,
                    "from": conn.inputNode().path()
                })
        
        # Output connections
        for conn in node.outputConnections():
            if conn.outputNode():
                info["outputs"].append({
                    "to": conn.outputNode().path(),
                    "input_index": conn.inputIndex()
                })
        
        return info
    
    @classmethod
    def _safe_parm_value(cls, parm: hou.Parm) -> Any:
        try:
            val = parm.eval()
            if isinstance(val, (int, float, str, bool)):
                return val
            elif isinstance(val, hou.Vector3):
                return list(val)
            elif hasattr(val, '__iter__'):
                return list(val)[:10]
            else:
                return str(val)[:100]
        except:
            return None
    
    @classmethod
    def _extract_stage_info(cls, lop_node: hou.LopNode, snapshot: SageContextSnapshot):
        try:
            stage = lop_node.stage()
            if not stage:
                return
            
            prim_count = 0
            for prim in stage.Traverse():
                if prim_count >= MAX_STAGE_PRIMS:
                    break
                snapshot.stage_prims.append({
                    "path": str(prim.GetPath()),
                    "type": prim.GetTypeName(),
                    "active": prim.IsActive()
                })
                prim_count += 1
            
            # Selected prims
            selection = lop_node.selection()
            if selection:
                for path in list(selection.paths())[:20]:
                    snapshot.stage_selected_prims.append(str(path))
                    
        except Exception as e:
            print(f"[Sage] Stage extraction error: {e}")


# =============================================================================
# LLM CLIENTS
# =============================================================================

class LLMClientBase(ABC):
    @property
    @abstractmethod
    def provider(self) -> LLMProvider:
        pass
    
    @abstractmethod
    def complete(self, messages: List[Dict], on_progress: Optional[Callable] = None) -> str:
        pass
    
    @abstractmethod
    def is_available(self) -> bool:
        pass


class OpenAIClient(LLMClientBase):
    def __init__(self, api_key: str = "", model: str = "gpt-4o"):
        self.api_key = api_key
        self.model = model
        self._openai = None
    
    @property
    def provider(self) -> LLMProvider:
        return LLMProvider.OPENAI
    
    def is_available(self) -> bool:
        if not self.api_key:
            return False
        try:
            import openai
            self._openai = openai
            return True
        except ImportError:
            return False
    
    def complete(self, messages: List[Dict], on_progress: Optional[Callable] = None) -> str:
        if not self.is_available():
            raise RuntimeError("OpenAI not available")
        
        client = self._openai.OpenAI(api_key=self.api_key)
        
        if on_progress:
            on_progress("Sending to OpenAI...")
        
        response = client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=0.7,
            max_tokens=4096
        )
        
        return response.choices[0].message.content


class AnthropicClient(LLMClientBase):
    def __init__(self, api_key: str = "", model: str = "claude-sonnet-4-20250514"):
        self.api_key = api_key
        self.model = model
        self._anthropic = None
    
    @property
    def provider(self) -> LLMProvider:
        return LLMProvider.ANTHROPIC
    
    def is_available(self) -> bool:
        if not self.api_key:
            return False
        try:
            import anthropic
            self._anthropic = anthropic
            return True
        except ImportError:
            return False
    
    def complete(self, messages: List[Dict], on_progress: Optional[Callable] = None) -> str:
        if not self.is_available():
            raise RuntimeError("Anthropic not available")
        
        client = self._anthropic.Anthropic(api_key=self.api_key)
        
        if on_progress:
            on_progress("Sending to Claude...")
        
        system_msg = ""
        chat_messages = []
        for msg in messages:
            if msg["role"] == "system":
                system_msg = msg["content"]
            else:
                chat_messages.append(msg)
        
        response = client.messages.create(
            model=self.model,
            max_tokens=4096,
            system=system_msg,
            messages=chat_messages
        )
        
        return response.content[0].text


class OllamaClient(LLMClientBase):
    def __init__(self, host: str = "http://localhost:11434", model: str = "llama3.3"):
        self.host = host
        self.model = model
    
    @property
    def provider(self) -> LLMProvider:
        return LLMProvider.OLLAMA
    
    def is_available(self) -> bool:
        try:
            import urllib.request
            req = urllib.request.Request(f"{self.host}/api/tags")
            urllib.request.urlopen(req, timeout=2)
            return True
        except:
            return False
    
    def complete(self, messages: List[Dict], on_progress: Optional[Callable] = None) -> str:
        import urllib.request
        import json
        
        if on_progress:
            on_progress(f"Sending to Ollama ({self.model})...")
        
        data = json.dumps({
            "model": self.model,
            "messages": messages,
            "stream": False
        }).encode()
        
        req = urllib.request.Request(
            f"{self.host}/api/chat",
            data=data,
            headers={"Content-Type": "application/json"}
        )
        
        with urllib.request.urlopen(req, timeout=120) as response:
            result = json.loads(response.read().decode())
            return result["message"]["content"]


class GeminiClient(LLMClientBase):
    def __init__(self, api_key: str = "", model: str = "gemini-2.0-flash"):
        self.api_key = api_key
        self.model = model
        self._genai = None

    @property
    def provider(self) -> LLMProvider:
        return LLMProvider.GOOGLE

    def is_available(self) -> bool:
        if not self.api_key:
            return False
        try:
            import google.generativeai as genai
            self._genai = genai
            return True
        except ImportError:
            return False

    def complete(self, messages: List[Dict], on_progress: Optional[Callable] = None) -> str:
        if not self.is_available():
            raise RuntimeError("Google Gemini not available")

        self._genai.configure(api_key=self.api_key)
        model = self._genai.GenerativeModel(self.model)

        if on_progress:
            on_progress(f"Sending to Gemini ({self.model})...")

        # Convert messages to Gemini format
        system_instruction = ""
        chat_history = []

        for msg in messages:
            if msg["role"] == "system":
                system_instruction = msg["content"]
            elif msg["role"] == "user":
                chat_history.append({"role": "user", "parts": [msg["content"]]})
            elif msg["role"] == "assistant":
                chat_history.append({"role": "model", "parts": [msg["content"]]})

        # Create model with system instruction if present
        if system_instruction:
            model = self._genai.GenerativeModel(
                self.model,
                system_instruction=system_instruction
            )

        chat = model.start_chat(history=chat_history[:-1] if chat_history else [])

        # Send the last user message
        last_msg = chat_history[-1]["parts"][0] if chat_history else ""
        response = chat.send_message(last_msg)

        return response.text


class ResilientLLMClient:
    """Multi-provider client with retry and fallback"""
    
    def __init__(self, clients: List[LLMClientBase], max_retries: int = 3):
        self.clients = clients
        self.max_retries = max_retries
        self._primary_index = 0
    
    def complete(self, messages: List[Dict], on_progress: Optional[Callable] = None) -> Tuple[str, LLMProvider]:
        errors = []
        
        # Try primary client first
        for attempt in range(self.max_retries):
            for i, client in enumerate(self.clients):
                if not client.is_available():
                    continue
                
                try:
                    if on_progress:
                        on_progress(f"Attempt {attempt + 1}/{self.max_retries} with {client.provider.value}...")
                    
                    result = client.complete(messages, on_progress)
                    self._primary_index = i
                    return result, client.provider
                    
                except Exception as e:
                    errors.append(f"{client.provider.value}: {e}")
                    if on_progress:
                        on_progress(f"Error: {e}")
                    time.sleep(min(2 ** attempt, 10))
        
        raise RuntimeError(f"All providers failed: {'; '.join(errors)}")
    
    def get_available_providers(self) -> List[LLMProvider]:
        return [c.provider for c in self.clients if c.is_available()]


# =============================================================================
# CONVERSATION MANAGER
# =============================================================================

@dataclass
class SageMessage:
    role: MessageRole
    content: str
    context: Optional[SageContextSnapshot] = None
    timestamp: float = field(default_factory=time.time)
    provider: Optional[LLMProvider] = None


class ConversationManager:
    """Manages conversation history with token-aware truncation"""
    
    SYSTEM_PROMPT = """You are Sage, an expert Houdini assistant embedded directly in SideFX Houdini.

Your expertise includes:
- VEX programming and optimization
- SOP, DOP, LOP, COP node networks
- USD/Solaris workflows and Karma rendering
- Python scripting for Houdini (hou module)
- Performance optimization and debugging
- Procedural modeling and simulation

When the user provides context about their current scene, use it to give specific, actionable advice.

Guidelines:
- Be concise but thorough
- Provide code examples when helpful
- Explain VEX/Python with performance implications
- Reference specific node types and parameters
- If asked to generate code, ensure it's production-ready"""
    
    def __init__(self):
        self._messages: List[SageMessage] = []
        self._lock = threading.Lock()
    
    @property
    def messages(self) -> List[SageMessage]:
        with self._lock:
            return list(self._messages)
    
    def add_user_message(self, content: str, context: Optional[SageContextSnapshot] = None):
        with self._lock:
            self._messages.append(SageMessage(
                role=MessageRole.USER,
                content=content,
                context=context
            ))
            self._truncate_if_needed()
    
    def add_assistant_message(self, content: str, provider: Optional[LLMProvider] = None):
        with self._lock:
            self._messages.append(SageMessage(
                role=MessageRole.ASSISTANT,
                content=content,
                provider=provider
            ))
            self._truncate_if_needed()
    
    def get_messages_for_api(self) -> List[Dict]:
        with self._lock:
            api_messages = [{"role": "system", "content": self.SYSTEM_PROMPT}]
            
            for msg in self._messages:
                content = msg.content
                
                # Inject context for user messages
                if msg.role == MessageRole.USER and msg.context:
                    context_str = msg.context.to_prompt_context()
                    content = f"[Current Houdini Context]\n{context_str}\n\n[Question]\n{msg.content}"
                
                api_messages.append({
                    "role": msg.role.value,
                    "content": content
                })
            
            return api_messages
    
    def _truncate_if_needed(self):
        while len(self._messages) > MAX_HISTORY:
            self._messages.pop(0)
    
    def clear(self):
        with self._lock:
            self._messages.clear()
    
    def get_last_context(self) -> Optional[SageContextSnapshot]:
        with self._lock:
            for msg in reversed(self._messages):
                if msg.context:
                    return msg.context
            return None


# =============================================================================
# QT PANEL
# =============================================================================

class ChatMessageWidget(QtWidgets.QFrame):
    def __init__(self, message: SageMessage, parent=None):
        super().__init__(parent)
        self._init_ui(message)
    
    def _init_ui(self, message: SageMessage):
        is_user = message.role == MessageRole.USER
        
        if is_user:
            self.setStyleSheet("""
                QFrame { background-color: #2d261e; border-radius: 10px; margin: 5px; padding: 10px; }
            """)
        else:
            self.setStyleSheet("""
                QFrame { background-color: #1a1915; border-radius: 10px; margin: 5px; padding: 10px; }
            """)
        
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        
        # Header
        header = QtWidgets.QHBoxLayout()
        role_label = QtWidgets.QLabel("You" if is_user else "Sage")
        role_label.setStyleSheet("font-weight: bold; color: #7D8B69;" if not is_user else "font-weight: bold; color: #A0522D;")
        header.addWidget(role_label)
        
        if message.provider:
            provider_label = QtWidgets.QLabel(f"via {message.provider.value}")
            provider_label.setStyleSheet("color: #666; font-size: 10px;")
            header.addWidget(provider_label)
        
        header.addStretch()
        
        time_label = QtWidgets.QLabel(time.strftime("%H:%M", time.localtime(message.timestamp)))
        time_label.setStyleSheet("color: #666; font-size: 10px;")
        header.addWidget(time_label)
        
        layout.addLayout(header)
        
        # Content
        content = QtWidgets.QTextEdit()
        content.setReadOnly(True)
        content.setMarkdown(message.content)
        content.setStyleSheet("""
            QTextEdit { background: transparent; border: none; color: #e0e0e0; }
        """)
        content.setMinimumHeight(50)
        
        # Auto-size
        doc = content.document()
        doc.setTextWidth(content.viewport().width())
        height = min(int(doc.size().height()) + 20, 400)
        content.setFixedHeight(height)
        
        layout.addWidget(content)
        
        # Context indicator
        if message.context:
            ctx_label = QtWidgets.QLabel(f"📍 Context: {len(message.context.selected_nodes)} nodes selected")
            ctx_label.setStyleSheet("color: #888; font-size: 10px;")
            layout.addWidget(ctx_label)


class SagePanel(QtWidgets.QWidget):
    response_received = QtCore.Signal(str, object)
    status_updated = QtCore.Signal(str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.conversation = ConversationManager()
        self.llm_client: Optional[ResilientLLMClient] = None
        self._is_processing = False
        self._init_ui()
        self._load_settings()
        self._connect_signals()
    
    def _init_ui(self):
        self.setWindowTitle(f"{__title__} - AI Assistant")
        self.setMinimumSize(300, 250)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(5)

        # Header section - fixed height, doesn't expand
        header_widget = QtWidgets.QWidget()
        header_widget.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        header_layout = QtWidgets.QVBoxLayout(header_widget)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(2)

        header = QtWidgets.QLabel("🦉 SAGE")
        header.setStyleSheet("font-size: 84px; font-weight: bold; color: #7D8B69; padding: 10px 20px;")
        header.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        header_layout.addWidget(header)

        subtitle = QtWidgets.QLabel("AI Assistant for Houdini")
        subtitle.setStyleSheet("color: #888; font-size: 25px; padding-left: 20px;")
        subtitle.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        header_layout.addWidget(subtitle)

        version_label = QtWidgets.QLabel(f"v{__version__} | Atomic Context Capture")
        version_label.setStyleSheet("color: #666; font-size: 10px; padding-left: 20px;")
        version_label.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        header_layout.addWidget(version_label)

        layout.addWidget(header_widget)
        
        # Chat area
        self.chat_scroll = QtWidgets.QScrollArea()
        self.chat_scroll.setWidgetResizable(True)
        self.chat_scroll.setStyleSheet("QScrollArea { border: none; background: #0d0c0a; }")
        
        self.chat_container = QtWidgets.QWidget()
        self.chat_layout = QtWidgets.QVBoxLayout(self.chat_container)
        self.chat_layout.addStretch()
        self.chat_scroll.setWidget(self.chat_container)
        
        layout.addWidget(self.chat_scroll, 1)
        
        # Input area
        input_group = QtWidgets.QGroupBox()
        input_group.setStyleSheet("QGroupBox { border: 1px solid #3d3830; border-radius: 8px; padding: 10px; }")
        input_layout = QtWidgets.QVBoxLayout(input_group)
        
        # Context toggle
        ctx_layout = QtWidgets.QHBoxLayout()
        self.include_context = QtWidgets.QCheckBox("Include scene context")
        self.include_context.setChecked(True)
        self.include_context.setStyleSheet("color: #888;")
        ctx_layout.addWidget(self.include_context)
        
        self.context_status = QtWidgets.QLabel("")
        self.context_status.setStyleSheet("color: #666; font-size: 10px;")
        ctx_layout.addWidget(self.context_status)
        ctx_layout.addStretch()
        input_layout.addLayout(ctx_layout)
        
        # Text input
        self.input_text = QtWidgets.QTextEdit()
        self.input_text.setPlaceholderText("Ask Sage anything about Houdini...")
        self.input_text.setMaximumHeight(100)
        self.input_text.setStyleSheet("""
            QTextEdit { background: #1a1915; border: 1px solid #3d3830; border-radius: 5px; padding: 8px; color: #e0e0e0; }
        """)
        input_layout.addWidget(self.input_text)
        
        # Buttons
        btn_layout = QtWidgets.QHBoxLayout()
        
        self.send_btn = QtWidgets.QPushButton("🚀 Send")
        self.send_btn.setStyleSheet("""
            QPushButton { background-color: #7D8B69; color: white; padding: 10px 20px; font-weight: bold; border-radius: 5px; }
            QPushButton:hover { background-color: #8D9B79; }
            QPushButton:disabled { background-color: #555; }
        """)
        self.send_btn.clicked.connect(self._send_message)
        btn_layout.addWidget(self.send_btn)
        
        clear_btn = QtWidgets.QPushButton("🗑️ Clear")
        clear_btn.clicked.connect(self._clear_chat)
        btn_layout.addWidget(clear_btn)
        
        settings_btn = QtWidgets.QPushButton("⚙️ Settings")
        settings_btn.clicked.connect(self._show_settings)
        btn_layout.addWidget(settings_btn)
        
        btn_layout.addStretch()
        input_layout.addLayout(btn_layout)
        
        layout.addWidget(input_group)
        
        # Status bar
        self.status_label = QtWidgets.QLabel("Ready")
        self.status_label.setStyleSheet("color: #666; padding: 5px;")
        layout.addWidget(self.status_label)
    
    def _connect_signals(self):
        self.response_received.connect(self._on_response)
        self.status_updated.connect(self._set_status)
    
    def _load_settings(self):
        settings_file = Path(hou.expandString("$HOUDINI_USER_PREF_DIR")) / "sage_settings.json"
        
        clients = []

        if settings_file.exists():
            try:
                with open(settings_file, 'r') as f:
                    settings = json.load(f)

                if settings.get("openai_key"):
                    clients.append(OpenAIClient(settings["openai_key"], settings.get("openai_model", "gpt-4o")))

                if settings.get("anthropic_key"):
                    clients.append(AnthropicClient(settings["anthropic_key"], settings.get("anthropic_model", "claude-sonnet-4-20250514")))

                if settings.get("google_key"):
                    clients.append(GeminiClient(settings["google_key"], settings.get("google_model", "gemini-2.0-flash")))

                if settings.get("ollama_enabled", True):
                    clients.append(OllamaClient(settings.get("ollama_host", "http://localhost:11434"), settings.get("ollama_model", "llama3.3")))

            except Exception as e:
                print(f"[Sage] Settings load error: {e}")
        
        # Always include Ollama as fallback
        if not any(isinstance(c, OllamaClient) for c in clients):
            clients.append(OllamaClient())
        
        self.llm_client = ResilientLLMClient(clients)
        
        available = self.llm_client.get_available_providers()
        if available:
            self._set_status(f"Available: {', '.join(p.value for p in available)}")
        else:
            self._set_status("No LLM providers available. Configure in Settings.")
    
    def _save_settings(self, settings: Dict):
        settings_file = Path(hou.expandString("$HOUDINI_USER_PREF_DIR")) / "sage_settings.json"
        try:
            with open(settings_file, 'w') as f:
                json.dump(settings, f, indent=2)
        except Exception as e:
            print(f"[Sage] Settings save error: {e}")
    
    def _send_message(self):
        if self._is_processing:
            return
        
        text = self.input_text.toPlainText().strip()
        if not text:
            return
        
        context = None
        if self.include_context.isChecked():
            context = AtomicContextExtractor.capture_context()
            self.context_status.setText(f"Captured: {len(context.selected_nodes)} nodes, {len(context.stage_prims)} prims")
        
        self.conversation.add_user_message(text, context)
        self._add_message_widget(self.conversation.messages[-1])
        
        self.input_text.clear()
        self._is_processing = True
        self.send_btn.setEnabled(False)
        self._set_status("Processing...")
        
        # Process in background thread
        thread = threading.Thread(target=self._process_in_background, daemon=True)
        thread.start()
    
    def _process_in_background(self):
        try:
            messages = self.conversation.get_messages_for_api()
            
            def on_progress(status):
                QtCore.QMetaObject.invokeMethod(
                    self, "_set_status_slot",
                    QtCore.Qt.QueuedConnection,
                    QtCore.Q_ARG(str, status)
                )
            
            response, provider = self.llm_client.complete(messages, on_progress)
            
            # Emit signal to update UI from main thread
            self.response_received.emit(response, provider)
            
        except Exception as e:
            self.response_received.emit(f"Error: {e}", None)
    
    @QtCore.Slot(str)
    def _set_status_slot(self, status: str):
        self._set_status(status)
    
    @QtCore.Slot(str, object)
    def _on_response(self, response: str, provider):
        self.conversation.add_assistant_message(response, provider)
        self._add_message_widget(self.conversation.messages[-1])
        
        self._is_processing = False
        self.send_btn.setEnabled(True)
        self._set_status("Ready")
        
        # Scroll to bottom
        QtCore.QTimer.singleShot(100, lambda: self.chat_scroll.verticalScrollBar().setValue(
            self.chat_scroll.verticalScrollBar().maximum()
        ))
    
    def _add_message_widget(self, message: SageMessage):
        widget = ChatMessageWidget(message)
        self.chat_layout.insertWidget(self.chat_layout.count() - 1, widget)
    
    def _clear_chat(self):
        self.conversation.clear()
        
        # Clear widgets
        while self.chat_layout.count() > 1:
            item = self.chat_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        self._set_status("Conversation cleared")
    
    def _show_settings(self):
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle("Sage Settings")
        dialog.setMinimumWidth(500)

        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(scroll_widget)

        # OpenAI
        openai_group = QtWidgets.QGroupBox("OpenAI")
        openai_layout = QtWidgets.QFormLayout(openai_group)
        openai_key = QtWidgets.QLineEdit()
        openai_key.setEchoMode(QtWidgets.QLineEdit.Password)
        openai_layout.addRow("API Key:", openai_key)
        openai_model = QtWidgets.QComboBox()
        openai_model.addItems([
            "gpt-4o",
            "gpt-4o-mini",
            "o1",
            "o1-mini",
            "gpt-4-turbo",
            "gpt-4",
        ])
        openai_layout.addRow("Model:", openai_model)
        layout.addWidget(openai_group)

        # Anthropic
        anthropic_group = QtWidgets.QGroupBox("Anthropic (Claude)")
        anthropic_layout = QtWidgets.QFormLayout(anthropic_group)
        anthropic_key = QtWidgets.QLineEdit()
        anthropic_key.setEchoMode(QtWidgets.QLineEdit.Password)
        anthropic_layout.addRow("API Key:", anthropic_key)
        anthropic_model = QtWidgets.QComboBox()
        anthropic_model.addItems([
            "claude-sonnet-4-20250514",
            "claude-opus-4-5-20251101",
            "claude-3-5-sonnet-20241022",
            "claude-3-5-haiku-20241022",
            "claude-3-opus-20240229",
        ])
        anthropic_layout.addRow("Model:", anthropic_model)
        layout.addWidget(anthropic_group)

        # Google Gemini
        google_group = QtWidgets.QGroupBox("Google Gemini")
        google_layout = QtWidgets.QFormLayout(google_group)
        google_key = QtWidgets.QLineEdit()
        google_key.setEchoMode(QtWidgets.QLineEdit.Password)
        google_layout.addRow("API Key:", google_key)
        google_model = QtWidgets.QComboBox()
        google_model.addItems([
            "gemini-2.0-flash",
            "gemini-2.0-flash-thinking-exp",
            "gemini-1.5-pro",
            "gemini-1.5-flash",
        ])
        google_layout.addRow("Model:", google_model)
        layout.addWidget(google_group)

        # Ollama
        ollama_group = QtWidgets.QGroupBox("Ollama (Local)")
        ollama_layout = QtWidgets.QFormLayout(ollama_group)
        ollama_enabled = QtWidgets.QCheckBox("Enable")
        ollama_enabled.setChecked(True)
        ollama_layout.addRow("", ollama_enabled)
        ollama_host = QtWidgets.QLineEdit("http://localhost:11434")
        ollama_layout.addRow("Host:", ollama_host)
        ollama_model = QtWidgets.QComboBox()
        ollama_model.setEditable(True)
        ollama_model.addItems([
            "llama3.3",
            "qwen2.5-coder",
            "deepseek-coder-v2",
            "codellama",
            "mistral",
            "mixtral",
        ])
        ollama_layout.addRow("Model:", ollama_model)
        layout.addWidget(ollama_group)

        scroll.setWidget(scroll_widget)

        main_layout = QtWidgets.QVBoxLayout(dialog)
        main_layout.addWidget(scroll)

        # Buttons
        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Save | QtWidgets.QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        main_layout.addWidget(buttons)

        if dialog.exec() == QtWidgets.QDialog.Accepted:
            settings = {
                "openai_key": openai_key.text(),
                "openai_model": openai_model.currentText(),
                "anthropic_key": anthropic_key.text(),
                "anthropic_model": anthropic_model.currentText(),
                "google_key": google_key.text(),
                "google_model": google_model.currentText(),
                "ollama_enabled": ollama_enabled.isChecked(),
                "ollama_host": ollama_host.text(),
                "ollama_model": ollama_model.currentText(),
            }
            self._save_settings(settings)
            self._load_settings()
    
    def _set_status(self, message: str):
        self.status_label.setText(message)


# =============================================================================
# ENTRY POINT
# =============================================================================

def create_panel():
    """Create and show Sage panel"""
    panel = SagePanel()
    panel.setParent(hou.qt.mainWindow(), QtCore.Qt.Window)
    panel.show()
    return panel


if __name__ == "__main__":
    create_panel()
