"""
Engram - Project Memory for RadiantSuite

A persistent memory system for Houdini projects that enables AI assistants
to maintain context across sessions, shots, and workflows.

Inspired by:
- Google Conductor (markdown files in repo)
- Mem0 (tiered memory architecture)
- A-MEM (Zettelkasten-style linked notes)

Memory lives alongside your .hip file in $HIP/.engram/
Human-readable markdown + structured JSON for search.

Usage:
    from engram import EngineMemory, Memory

    # Initialize for current project
    mem = EngramMemory()

    # Add a memory
    mem.add("Changed key light to 6500K per client request",
            memory_type="decision",
            tags=["lighting", "client_feedback"])

    # Search memories
    results = mem.search("key light decisions")

    # Get full context for AI
    context = mem.get_context()

Author: Joe Ibrahim
Version: 1.0.0
"""

__title__ = "Engram"
__version__ = "1.0.0"
__author__ = "Joe Ibrahim"
__product__ = "Engram - Project Memory"

from .memory import (
    Memory,
    MemoryType,
    MemoryTier,
    MemoryLink,
    MemoryQuery,
)

from .store import (
    EngramMemory,
    MemoryStore,
    get_engram,
    reset_engram,
)

from .context import (
    ShotContext,
    load_context,
    save_context,
)

from .markdown import (
    MarkdownSync,
    parse_decisions_md,
    render_decisions_md,
)

# Panel (lazy import to avoid Qt dependency issues)
try:
    from .engram_tool import EngramPanel, create_panel
except ImportError:
    EngramPanel = None
    create_panel = None

__all__ = [
    # Core
    'Memory',
    'MemoryType',
    'MemoryTier',
    'MemoryLink',
    'MemoryQuery',

    # Store
    'EngramMemory',
    'MemoryStore',
    'get_engram',
    'reset_engram',

    # Context
    'ShotContext',
    'load_context',
    'save_context',

    # Markdown
    'MarkdownSync',
    'parse_decisions_md',
    'render_decisions_md',

    # Panel
    'EngramPanel',
    'create_panel',
]
