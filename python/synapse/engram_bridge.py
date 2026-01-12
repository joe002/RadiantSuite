"""
Synapse-Engram Bridge

The integration layer that unifies Synapse (communication) with Engram (memory).

This module:
1. Auto-loads Engram context when AI connects
2. Auto-logs significant Synapse actions to Engram
3. Provides memory-aware commands to AI
4. Generates session summaries on disconnect

Author: Joe Ibrahim
Version: 1.0.0
"""

import time
import json
import threading
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, field
from enum import Enum

try:
    import hou
    HOU_AVAILABLE = True
except ImportError:
    HOU_AVAILABLE = False

# Import Engram
try:
    from engram import (
        EngramMemory,
        Memory,
        MemoryType,
        MemoryTier,
        MemoryQuery,
        get_engram,
        reset_engram
    )
    from engram.markdown import MarkdownSync, load_context
    ENGRAM_AVAILABLE = True
except ImportError:
    ENGRAM_AVAILABLE = False
    print("[Synapse-Engram] Warning: Engram module not available")


# =============================================================================
# SESSION TRACKING
# =============================================================================

@dataclass
class SynapseSession:
    """Tracks a single AI session for memory purposes."""
    session_id: str
    client_id: str
    started_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    ended_at: Optional[str] = None

    # Session activity
    commands_executed: int = 0
    nodes_created: List[str] = field(default_factory=list)
    nodes_modified: List[str] = field(default_factory=list)
    decisions_made: List[str] = field(default_factory=list)
    errors_encountered: List[str] = field(default_factory=list)

    # Conversation excerpts worth preserving
    notable_exchanges: List[Dict[str, str]] = field(default_factory=list)

    def duration_seconds(self) -> float:
        """Get session duration in seconds."""
        if self.ended_at:
            end = time.mktime(time.strptime(self.ended_at, "%Y-%m-%dT%H:%M:%SZ"))
        else:
            end = time.time()
        start = time.mktime(time.strptime(self.started_at, "%Y-%m-%dT%H:%M:%SZ"))
        return end - start

    def to_summary(self) -> str:
        """Generate a human-readable session summary."""
        duration = self.duration_seconds()
        duration_str = f"{int(duration // 60)}m {int(duration % 60)}s"

        lines = [
            f"## Session Summary",
            f"**Duration:** {duration_str}",
            f"**Commands:** {self.commands_executed}",
            ""
        ]

        if self.nodes_created:
            lines.append("**Nodes Created:**")
            for node in self.nodes_created[:10]:  # Limit to 10
                lines.append(f"- {node}")
            if len(self.nodes_created) > 10:
                lines.append(f"- ... and {len(self.nodes_created) - 10} more")
            lines.append("")

        if self.decisions_made:
            lines.append("**Decisions Made:**")
            for decision in self.decisions_made:
                lines.append(f"- {decision}")
            lines.append("")

        if self.errors_encountered:
            lines.append("**Errors Encountered:**")
            for error in self.errors_encountered[:5]:
                lines.append(f"- {error}")
            lines.append("")

        return "\n".join(lines)


# =============================================================================
# ENGRAM BRIDGE
# =============================================================================

class EngramBridge:
    """
    Bridges Synapse and Engram for unified AI-native workflow.

    Responsibilities:
    - Provide project context to AI on connect
    - Log significant actions to Engram
    - Handle memory-related commands
    - Generate session summaries
    """

    def __init__(self):
        self._sessions: Dict[str, SynapseSession] = {}
        self._engram: Optional[EngramMemory] = None
        self._markdown_sync: Optional[MarkdownSync] = None
        self._lock = threading.Lock()

        # Auto-logging settings
        self.log_node_creation = True
        self.log_node_modification = True
        self.log_parameter_changes = False  # Too noisy by default
        self.log_errors = True

        self._init_engram()

    def _init_engram(self):
        """Initialize Engram for current project."""
        if not ENGRAM_AVAILABLE:
            print("[EngramBridge] Engram not available")
            return

        try:
            self._engram = get_engram()
            if self._engram:
                self._markdown_sync = MarkdownSync(self._engram.storage_dir)
                self._markdown_sync.ensure_files()
                print(f"[EngramBridge] Connected to Engram at {self._engram.storage_dir}")
        except Exception as e:
            print(f"[EngramBridge] Failed to initialize Engram: {e}")

    def reload_engram(self):
        """Reload Engram (e.g., when project changes)."""
        reset_engram()
        self._init_engram()

    # =========================================================================
    # SESSION MANAGEMENT
    # =========================================================================

    def start_session(self, client_id: str) -> str:
        """
        Start a new session when AI connects.

        Returns:
            Session ID
        """
        session_id = f"sess_{int(time.time())}_{client_id}"

        session = SynapseSession(
            session_id=session_id,
            client_id=str(client_id)
        )

        with self._lock:
            self._sessions[session_id] = session

        # Log session start to Engram
        if self._engram:
            self._engram.add(
                content=f"AI session started (client: {client_id})",
                memory_type=MemoryType.NOTE,
                tags=["session", "start"],
                source="auto"
            )

        return session_id

    def end_session(self, session_id: str) -> Optional[str]:
        """
        End a session and generate summary.

        Returns:
            Session summary string
        """
        with self._lock:
            session = self._sessions.pop(session_id, None)

        if not session:
            return None

        session.ended_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        summary = session.to_summary()

        # Log session summary to Engram
        if self._engram and session.commands_executed > 0:
            self._engram.add(
                content=summary,
                memory_type=MemoryType.SUMMARY,
                tags=["session", "summary"],
                source="auto"
            )

        return summary

    def get_session(self, session_id: str) -> Optional[SynapseSession]:
        """Get a session by ID."""
        with self._lock:
            return self._sessions.get(session_id)

    # =========================================================================
    # CONTEXT LOADING
    # =========================================================================

    def get_connection_context(self) -> Dict[str, Any]:
        """
        Get full project context for AI on connection.

        This is sent to AI immediately when it connects, giving it
        full awareness of the project state.
        """
        context = {
            "project": {},
            "recent_decisions": [],
            "recent_activity": [],
            "current_state": {},
            "memory_stats": {}
        }

        if not self._engram:
            context["warning"] = "Engram not available"
            return context

        # Project context from context.md
        try:
            shot_context = load_context(self._engram.storage_dir)
            context["project"] = {
                "overview": shot_context.overview,
                "goals": shot_context.goals,
                "constraints": shot_context.constraints,
                "assets": shot_context.assets,
                "client_notes": shot_context.client_notes
            }
        except Exception as e:
            context["project"]["error"] = str(e)

        # Recent decisions
        try:
            decisions = self._engram.get_decisions()
            context["recent_decisions"] = [
                {
                    "date": d.created_at.split("T")[0] if d.created_at else "",
                    "summary": d.summary,
                    "id": d.id
                }
                for d in decisions[-5:]  # Last 5
            ]
        except Exception as e:
            context["recent_decisions"] = []

        # Recent activity
        try:
            recent = self._engram.get_recent(10)
            context["recent_activity"] = [
                {
                    "type": m.memory_type.value,
                    "summary": m.summary,
                    "timestamp": m.created_at
                }
                for m in recent
            ]
        except Exception as e:
            context["recent_activity"] = []

        # Current Houdini state
        if HOU_AVAILABLE:
            try:
                context["current_state"] = {
                    "hip_file": hou.hipFile.name(),
                    "frame": int(hou.frame()),
                    "fps": hou.fps(),
                    "selection": [n.path() for n in hou.selectedNodes()[:5]]
                }
            except:
                pass

        # Memory stats
        context["memory_stats"] = {
            "total_memories": self._engram.store.count(),
            "storage_dir": str(self._engram.storage_dir)
        }

        return context

    def get_context_markdown(self) -> str:
        """
        Get project context as markdown (for AI prompt injection).
        """
        if not self._markdown_sync:
            return "# No project context available\n"

        return self._markdown_sync.get_context_for_ai()

    # =========================================================================
    # ACTION LOGGING
    # =========================================================================

    def log_action(
        self,
        action: str,
        session_id: str = None,
        node_paths: List[str] = None,
        details: Dict[str, Any] = None
    ):
        """Log an action to Engram."""
        if not self._engram:
            return

        # Update session stats
        if session_id:
            session = self.get_session(session_id)
            if session:
                session.commands_executed += 1
                if node_paths:
                    session.nodes_modified.extend(node_paths)

        # Log to Engram
        self._engram.add(
            content=action,
            memory_type=MemoryType.ACTION,
            tags=["action", "ai"],
            node_paths=node_paths or [],
            source="ai"
        )

    def log_node_created(self, node_path: str, node_type: str, session_id: str = None):
        """Log node creation."""
        if not self.log_node_creation:
            return

        if session_id:
            session = self.get_session(session_id)
            if session:
                session.nodes_created.append(node_path)

        self.log_action(
            f"Created {node_type} node: {node_path}",
            session_id=session_id,
            node_paths=[node_path]
        )

    def log_decision(
        self,
        decision: str,
        reasoning: str,
        session_id: str = None,
        alternatives: List[str] = None
    ):
        """Log a decision with reasoning."""
        if not self._engram:
            return

        memory = self._engram.decision(
            decision=decision,
            reasoning=reasoning,
            alternatives=alternatives,
            tags=["ai_decision"]
        )

        # Update session
        if session_id:
            session = self.get_session(session_id)
            if session:
                session.decisions_made.append(decision)

        # Sync to markdown
        if self._markdown_sync:
            self._markdown_sync.append_decision(memory)

    def log_error(self, error: str, session_id: str = None):
        """Log an error."""
        if not self.log_errors or not self._engram:
            return

        if session_id:
            session = self.get_session(session_id)
            if session:
                session.errors_encountered.append(error)

        self._engram.add(
            content=error,
            memory_type=MemoryType.ERROR,
            tags=["error", "ai"],
            source="auto"
        )

    # =========================================================================
    # MEMORY COMMANDS (for Synapse handlers)
    # =========================================================================

    def handle_memory_search(self, payload: Dict) -> Dict:
        """Handle memory search command from Synapse."""
        if not self._engram:
            return {"error": "Engram not available", "results": []}

        query_text = payload.get("query", "")
        limit = payload.get("limit", 20)
        memory_types = payload.get("types", [])

        # Convert type strings to enums
        type_enums = []
        for t in memory_types:
            try:
                type_enums.append(MemoryType(t))
            except ValueError:
                pass

        query = MemoryQuery(
            text=query_text,
            memory_types=type_enums,
            limit=limit
        )

        results = self._engram.search(query_text, limit=limit)

        return {
            "query": query_text,
            "count": len(results),
            "results": [
                {
                    "id": r.memory.id,
                    "type": r.memory.memory_type.value,
                    "summary": r.memory.summary,
                    "content": r.memory.content,
                    "score": r.score,
                    "tags": r.memory.tags,
                    "created_at": r.memory.created_at
                }
                for r in results
            ]
        }

    def handle_memory_add(self, payload: Dict) -> Dict:
        """Handle memory add command from Synapse."""
        if not self._engram:
            return {"error": "Engram not available"}

        content = payload.get("content", "")
        memory_type_str = payload.get("type", "note")
        tags = payload.get("tags", [])
        keywords = payload.get("keywords", [])

        try:
            memory_type = MemoryType(memory_type_str)
        except ValueError:
            memory_type = MemoryType.NOTE

        memory = self._engram.add(
            content=content,
            memory_type=memory_type,
            tags=tags,
            keywords=keywords,
            source="ai"
        )

        return {
            "id": memory.id,
            "summary": memory.summary,
            "created": True
        }

    def handle_memory_decide(self, payload: Dict) -> Dict:
        """Handle decision recording from Synapse."""
        if not self._engram:
            return {"error": "Engram not available"}

        decision = payload.get("decision", "")
        reasoning = payload.get("reasoning", "")
        alternatives = payload.get("alternatives", [])
        tags = payload.get("tags", [])

        memory = self._engram.decision(
            decision=decision,
            reasoning=reasoning,
            alternatives=alternatives,
            tags=tags + ["ai_decision"]
        )

        # Sync to markdown
        if self._markdown_sync:
            self._markdown_sync.append_decision(memory)

        return {
            "id": memory.id,
            "summary": memory.summary,
            "recorded": True
        }

    def handle_memory_context(self, payload: Dict) -> Dict:
        """Handle context request from Synapse."""
        format_type = payload.get("format", "json")

        if format_type == "markdown":
            return {
                "format": "markdown",
                "context": self.get_context_markdown()
            }
        else:
            return {
                "format": "json",
                "context": self.get_connection_context()
            }

    def handle_memory_recall(self, payload: Dict) -> Dict:
        """
        Handle recall request - check if we've decided on something before.

        This is for questions like "Did we already decide on rim light color?"
        """
        if not self._engram:
            return {"error": "Engram not available", "found": False}

        query = payload.get("query", "")

        # Search specifically in decisions
        decisions = self._engram.get_decisions()

        # Simple keyword matching for now
        query_lower = query.lower()
        matches = []

        for d in decisions:
            content_lower = d.content.lower()
            summary_lower = d.summary.lower()

            if query_lower in content_lower or query_lower in summary_lower:
                matches.append({
                    "id": d.id,
                    "summary": d.summary,
                    "content": d.content,
                    "date": d.created_at.split("T")[0] if d.created_at else ""
                })

        return {
            "query": query,
            "found": len(matches) > 0,
            "count": len(matches),
            "matches": matches[:5]  # Top 5 matches
        }


# =============================================================================
# GLOBAL INSTANCE
# =============================================================================

_bridge: Optional[EngramBridge] = None


def get_bridge() -> EngramBridge:
    """Get or create the global EngramBridge instance."""
    global _bridge
    if _bridge is None:
        _bridge = EngramBridge()
    return _bridge


def reset_bridge():
    """Reset the bridge (e.g., when project changes)."""
    global _bridge
    _bridge = None
