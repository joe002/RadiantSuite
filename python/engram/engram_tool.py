"""
┌────────────────────────────────────────────────────────────────┐
│                                                                │▒
│   ███████╗███╗   ██╗ ██████╗ ██████╗  █████╗ ███╗   ███╗      │▒
│   ██╔════╝████╗  ██║██╔════╝ ██╔══██╗██╔══██╗████╗ ████║      │▒
│   █████╗  ██╔██╗ ██║██║  ███╗██████╔╝███████║██╔████╔██║      │▒
│   ██╔══╝  ██║╚██╗██║██║   ██║██╔══██╗██╔══██║██║╚██╔╝██║      │▒
│   ███████╗██║ ╚████║╚██████╔╝██║  ██║██║  ██║██║ ╚═╝ ██║      │▒
│   ╚══════╝╚═╝  ╚═══╝ ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝     ╚═╝      │▒
│                                                                │▒
│   Project Memory                                               │▒
│   Persistent context, decisions, and task history for Houdini  │▒
│                                                                │▒
└────────────────────────────────────────────────────────────────┘▒
 ▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒

Engram v1.0.0 | Houdini 21+ | Python 3.9+

Qt-based panel for viewing and editing project context, decisions, and memories.
Memory lives alongside your .hip file in $HIP/.engram/

FEATURES:
• Context.md editor with structured sections
• Decision log with reasoning and alternatives
• Memory search with type filters
• Real-time activity feed
• Human-readable markdown + structured JSON

LICENSE: MIT
AUTHOR: Joe Ibrahim
"""

import os
import sys
import time
from pathlib import Path
from typing import Optional, List, Dict, Any

# Try to import Houdini
try:
    import hou
    HOU_AVAILABLE = True
except ImportError:
    HOU_AVAILABLE = False
    hou = None

# Try to import Qt (PySide6 for Houdini 21+, PySide2 for older)
QT_AVAILABLE = False
try:
    from PySide6 import QtWidgets, QtCore, QtGui
    QT_AVAILABLE = True
except ImportError:
    try:
        from PySide2 import QtWidgets, QtCore, QtGui
        QT_AVAILABLE = True
    except ImportError:
        pass

if not QT_AVAILABLE:
    # Stubs for development outside Houdini
    class QtWidgets:
        QWidget = object
        QVBoxLayout = object
        QHBoxLayout = object
        QTabWidget = object
        QTextEdit = object
        QPushButton = object
        QLabel = object
        QLineEdit = object
        QListWidget = object
        QListWidgetItem = object
        QGroupBox = object
        QFormLayout = object
        QScrollArea = object
        QFrame = object
        QSplitter = object
        QComboBox = object
        QApplication = object
        QMessageBox = object
    class QtCore:
        Qt = type('Qt', (), {'UserRole': 0, 'Window': 0, 'Widget': 0})()
        Signal = lambda *args: lambda f: f
        QTimer = object
    class QtGui:
        QFont = object
        QColor = object

from engram import (
    EngramMemory,
    Memory,
    MemoryType,
    get_engram,
    reset_engram,
)
from engram.markdown import MarkdownSync
from engram.context import ShotContext, load_context, save_context

__title__ = "Engram"
__version__ = "1.0.0"
__author__ = "Joe Ibrahim"
__license__ = "MIT"
__product__ = "Engram - Project Memory"


# =============================================================================
# HOUDINI-NATIVE STYLING
# =============================================================================
# Engram inherits Houdini's native Qt theme.
# Only minimal overrides for branding elements (headers) and monospace text.
# This ensures the panel feels like a native Houdini tool.


# =============================================================================
# CONTEXT TAB
# =============================================================================

class ContextTab(QtWidgets.QWidget):
    """Tab for editing context.md sections."""

    context_changed = QtCore.Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._engram: Optional[EngramMemory] = None
        self._markdown_sync: Optional[MarkdownSync] = None
        self._modified = False
        self._setup_ui()

    def _setup_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # Header - Houdini native styling
        header_layout = QtWidgets.QHBoxLayout()
        title = QtWidgets.QLabel("Shot Context")
        title.setStyleSheet("font-size: 13px; font-weight: bold;")
        header_layout.addWidget(title)
        header_layout.addStretch()

        self.status_label = QtWidgets.QLabel("○ No project loaded")
        self.status_label.setStyleSheet("color: palette(mid);")
        header_layout.addWidget(self.status_label)
        layout.addLayout(header_layout)

        # Scroll area for sections
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QtWidgets.QFrame.NoFrame)

        scroll_content = QtWidgets.QWidget()
        scroll_layout = QtWidgets.QVBoxLayout(scroll_content)
        scroll_layout.setSpacing(15)

        # Context sections
        self.sections = {}
        section_configs = [
            ("overview", "Overview", "Describe what this shot is about..."),
            ("goals", "Goals", "What are we trying to achieve?"),
            ("constraints", "Constraints", "Technical or creative constraints..."),
            ("assets", "Assets", "Key assets used in this shot..."),
            ("client_notes", "Client Notes", "Feedback and direction from client/supervisor..."),
        ]

        for key, label, placeholder in section_configs:
            group = QtWidgets.QGroupBox(label)
            group_layout = QtWidgets.QVBoxLayout(group)

            text_edit = QtWidgets.QTextEdit()
            text_edit.setPlaceholderText(placeholder)
            text_edit.setMinimumHeight(80)
            text_edit.setMaximumHeight(150)
            text_edit.textChanged.connect(self._on_text_changed)
            group_layout.addWidget(text_edit)

            self.sections[key] = text_edit
            scroll_layout.addWidget(group)

        scroll_layout.addStretch()
        scroll.setWidget(scroll_content)
        layout.addWidget(scroll)

        # Buttons - Houdini native styling
        btn_layout = QtWidgets.QHBoxLayout()
        btn_layout.addStretch()

        self.revert_btn = QtWidgets.QPushButton("Revert")
        self.revert_btn.clicked.connect(self._revert)
        self.revert_btn.setEnabled(False)
        btn_layout.addWidget(self.revert_btn)

        self.save_btn = QtWidgets.QPushButton("Save Context")
        self.save_btn.clicked.connect(self._save)
        self.save_btn.setEnabled(False)
        btn_layout.addWidget(self.save_btn)

        layout.addLayout(btn_layout)

    def set_engram(self, engram: EngramMemory):
        """Set the Engram instance and load context."""
        self._engram = engram
        if engram:
            self._markdown_sync = MarkdownSync(engram.storage_dir)
            self._load_context()
            self.status_label.setText("● Loaded")
            self.status_label.setStyleSheet("color: #4CAF50;")  # Houdini green
        else:
            self.status_label.setText("○ No project")
            self.status_label.setStyleSheet("color: palette(mid);")

    def _load_context(self):
        """Load context from markdown file."""
        if not self._engram:
            return

        try:
            context = load_context(self._engram.storage_dir)
            self.sections["overview"].setPlainText(context.overview or "")
            self.sections["goals"].setPlainText(context.goals or "")
            self.sections["constraints"].setPlainText(context.constraints or "")
            self.sections["assets"].setPlainText(context.assets or "")
            self.sections["client_notes"].setPlainText(context.client_notes or "")
            self._modified = False
            self._update_buttons()
        except Exception as e:
            print(f"[Engram] Failed to load context: {e}")

    def _on_text_changed(self):
        """Mark as modified when text changes."""
        self._modified = True
        self._update_buttons()

    def _update_buttons(self):
        """Update button states based on modification status."""
        self.save_btn.setEnabled(self._modified and self._engram is not None)
        self.revert_btn.setEnabled(self._modified)

    def _save(self):
        """Save context to markdown file."""
        if not self._engram:
            return

        try:
            context = ShotContext(
                overview=self.sections["overview"].toPlainText(),
                goals=self.sections["goals"].toPlainText(),
                constraints=self.sections["constraints"].toPlainText(),
                assets=self.sections["assets"].toPlainText(),
                client_notes=self.sections["client_notes"].toPlainText(),
            )
            save_context(self._engram.storage_dir, context)
            self._modified = False
            self._update_buttons()
            self.status_label.setText("● Saved")
            self.status_label.setStyleSheet("color: #4CAF50;")  # Houdini green
            self.context_changed.emit()
        except Exception as e:
            self.status_label.setText(f"✖ Failed: {e}")
            self.status_label.setStyleSheet("color: #F44336;")  # Houdini red

    def _revert(self):
        """Revert to last saved state."""
        self._load_context()


# =============================================================================
# DECISIONS TAB
# =============================================================================

class DecisionItem(QtWidgets.QFrame):
    """A single decision entry widget."""

    def __init__(self, memory: Memory, parent=None):
        super().__init__(parent)
        self.memory = memory
        self._setup_ui()

    def _setup_ui(self):
        # Houdini-native styling - use StyledPanel for native look
        self.setFrameStyle(QtWidgets.QFrame.StyledPanel)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(6)
        layout.setContentsMargins(8, 8, 8, 8)

        # Header with date
        header = QtWidgets.QHBoxLayout()
        date_str = self.memory.created_at.split("T")[0] if self.memory.created_at else "Unknown"
        date_label = QtWidgets.QLabel(date_str)
        date_label.setStyleSheet("color: palette(mid); font-size: 11px;")
        header.addWidget(date_label)
        header.addStretch()

        # Tags
        if self.memory.tags:
            tags_str = " ".join([f"#{t}" for t in self.memory.tags[:3]])
            tags_label = QtWidgets.QLabel(tags_str)
            tags_label.setStyleSheet("color: palette(mid); font-size: 10px;")
            header.addWidget(tags_label)

        layout.addLayout(header)

        # Decision summary
        summary = QtWidgets.QLabel(self.memory.summary)
        summary.setWordWrap(True)
        summary.setStyleSheet("font-weight: bold; font-size: 12px;")
        layout.addWidget(summary)

        # Reasoning (if available in content)
        content_lines = self.memory.content.split("\n")
        reasoning = ""
        for line in content_lines:
            if line.startswith("**Reasoning:**"):
                reasoning = line.replace("**Reasoning:**", "").strip()
                break

        if reasoning:
            reason_label = QtWidgets.QLabel(reasoning)
            reason_label.setWordWrap(True)
            reason_label.setStyleSheet("color: palette(mid); font-size: 11px;")
            layout.addWidget(reason_label)


class DecisionsTab(QtWidgets.QWidget):
    """Tab for viewing and adding decisions."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._engram: Optional[EngramMemory] = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # Header - Houdini native styling
        header = QtWidgets.QHBoxLayout()
        title = QtWidgets.QLabel("Decision Log")
        title.setStyleSheet("font-size: 13px; font-weight: bold;")
        header.addWidget(title)
        header.addStretch()

        refresh_btn = QtWidgets.QPushButton("Refresh")
        refresh_btn.clicked.connect(self._refresh)
        header.addWidget(refresh_btn)

        layout.addLayout(header)

        # Add decision form
        add_group = QtWidgets.QGroupBox("Record New Decision")
        add_layout = QtWidgets.QVBoxLayout(add_group)

        self.decision_input = QtWidgets.QLineEdit()
        self.decision_input.setPlaceholderText("What did you decide?")
        add_layout.addWidget(self.decision_input)

        self.reasoning_input = QtWidgets.QTextEdit()
        self.reasoning_input.setPlaceholderText("Why? What was the reasoning?")
        self.reasoning_input.setMaximumHeight(80)
        add_layout.addWidget(self.reasoning_input)

        self.alternatives_input = QtWidgets.QLineEdit()
        self.alternatives_input.setPlaceholderText("Alternatives considered (comma-separated)")
        add_layout.addWidget(self.alternatives_input)

        self.tags_input = QtWidgets.QLineEdit()
        self.tags_input.setPlaceholderText("Tags (comma-separated)")
        add_layout.addWidget(self.tags_input)

        add_btn_layout = QtWidgets.QHBoxLayout()
        add_btn_layout.addStretch()
        self.add_btn = QtWidgets.QPushButton("Record Decision")
        self.add_btn.clicked.connect(self._add_decision)
        add_btn_layout.addWidget(self.add_btn)
        add_layout.addLayout(add_btn_layout)

        layout.addWidget(add_group)

        # Decisions list
        self.decisions_scroll = QtWidgets.QScrollArea()
        self.decisions_scroll.setWidgetResizable(True)
        self.decisions_scroll.setFrameShape(QtWidgets.QFrame.NoFrame)

        self.decisions_container = QtWidgets.QWidget()
        self.decisions_layout = QtWidgets.QVBoxLayout(self.decisions_container)
        self.decisions_layout.setSpacing(10)
        self.decisions_layout.addStretch()

        self.decisions_scroll.setWidget(self.decisions_container)
        layout.addWidget(self.decisions_scroll)

    def set_engram(self, engram: EngramMemory):
        """Set the Engram instance and load decisions."""
        self._engram = engram
        self._refresh()

    def _refresh(self):
        """Refresh the decisions list."""
        # Clear existing
        while self.decisions_layout.count() > 1:
            item = self.decisions_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not self._engram:
            return

        try:
            decisions = self._engram.get_decisions()
            for decision in reversed(decisions):  # Newest first
                item = DecisionItem(decision)
                self.decisions_layout.insertWidget(self.decisions_layout.count() - 1, item)
        except Exception as e:
            print(f"[Engram] Failed to load decisions: {e}")

    def _add_decision(self):
        """Add a new decision."""
        if not self._engram:
            return

        decision_text = self.decision_input.text().strip()
        if not decision_text:
            return

        reasoning = self.reasoning_input.toPlainText().strip()
        alternatives = [a.strip() for a in self.alternatives_input.text().split(",") if a.strip()]
        tags = [t.strip() for t in self.tags_input.text().split(",") if t.strip()]

        try:
            self._engram.decision(
                decision=decision_text,
                reasoning=reasoning,
                alternatives=alternatives,
                tags=tags
            )

            # Clear form
            self.decision_input.clear()
            self.reasoning_input.clear()
            self.alternatives_input.clear()
            self.tags_input.clear()

            # Refresh list
            self._refresh()
        except Exception as e:
            print(f"[Engram] Failed to add decision: {e}")


# =============================================================================
# SEARCH TAB
# =============================================================================

class SearchTab(QtWidgets.QWidget):
    """Tab for searching memories."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._engram: Optional[EngramMemory] = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # Header - Houdini native styling
        title = QtWidgets.QLabel("Search Memories")
        title.setStyleSheet("font-size: 13px; font-weight: bold;")
        layout.addWidget(title)

        # Search input
        search_layout = QtWidgets.QHBoxLayout()

        self.search_input = QtWidgets.QLineEdit()
        self.search_input.setPlaceholderText("Search memories...")
        self.search_input.returnPressed.connect(self._search)
        search_layout.addWidget(self.search_input)

        self.type_filter = QtWidgets.QComboBox()
        self.type_filter.addItem("All Types", "")
        self.type_filter.addItem("Decisions", "decision")
        self.type_filter.addItem("Context", "context")
        self.type_filter.addItem("Actions", "action")
        self.type_filter.addItem("Notes", "note")
        self.type_filter.addItem("Errors", "error")
        search_layout.addWidget(self.type_filter)

        search_btn = QtWidgets.QPushButton("Search")
        search_btn.clicked.connect(self._search)
        search_layout.addWidget(search_btn)

        layout.addLayout(search_layout)

        # Results count
        self.results_label = QtWidgets.QLabel("")
        self.results_label.setStyleSheet("color: palette(mid); font-size: 11px;")
        layout.addWidget(self.results_label)

        # Results list
        self.results_list = QtWidgets.QListWidget()
        self.results_list.itemDoubleClicked.connect(self._show_details)
        layout.addWidget(self.results_list)

        # Details panel
        self.details_group = QtWidgets.QGroupBox("Memory Details")
        details_layout = QtWidgets.QVBoxLayout(self.details_group)

        self.details_text = QtWidgets.QTextEdit()
        self.details_text.setReadOnly(True)
        self.details_text.setMaximumHeight(200)
        details_layout.addWidget(self.details_text)

        self.details_group.setVisible(False)
        layout.addWidget(self.details_group)

    def set_engram(self, engram: EngramMemory):
        """Set the Engram instance."""
        self._engram = engram

    def _search(self):
        """Perform search."""
        self.results_list.clear()
        self.details_group.setVisible(False)

        if not self._engram:
            return

        query = self.search_input.text().strip()
        type_filter = self.type_filter.currentData()

        try:
            results = self._engram.search(query, limit=50)

            # Filter by type if specified
            if type_filter:
                results = [r for r in results if r.memory.memory_type.value == type_filter]

            self.results_label.setText(f"Found {len(results)} results")

            for result in results:
                memory = result.memory
                item = QtWidgets.QListWidgetItem()
                item.setText(f"[{memory.memory_type.value}] {memory.summary}")
                item.setData(QtCore.Qt.UserRole, memory)
                self.results_list.addItem(item)

        except Exception as e:
            self.results_label.setText(f"Search error: {e}")

    def _show_details(self, item):
        """Show details for selected memory."""
        memory = item.data(QtCore.Qt.UserRole)
        if not memory:
            return

        details = f"""ID: {memory.id}
Type: {memory.memory_type.value}
Created: {memory.created_at}
Tags: {', '.join(memory.tags) if memory.tags else 'none'}
Keywords: {', '.join(memory.keywords) if memory.keywords else 'none'}

--- Content ---
{memory.content}
"""
        self.details_text.setPlainText(details)
        self.details_group.setVisible(True)


# =============================================================================
# ACTIVITY TAB
# =============================================================================

class ActivityTab(QtWidgets.QWidget):
    """Tab showing recent memory activity."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._engram: Optional[EngramMemory] = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # Header - Houdini native styling
        header = QtWidgets.QHBoxLayout()
        title = QtWidgets.QLabel("Recent Activity")
        title.setStyleSheet("font-size: 13px; font-weight: bold;")
        header.addWidget(title)
        header.addStretch()

        refresh_btn = QtWidgets.QPushButton("Refresh")
        refresh_btn.clicked.connect(self._refresh)
        header.addWidget(refresh_btn)

        layout.addLayout(header)

        # Activity log - monospace for readability, native background
        self.activity_list = QtWidgets.QListWidget()
        self.activity_list.setStyleSheet("font-family: monospace; font-size: 11px;")
        layout.addWidget(self.activity_list)

        # Stats
        self.stats_label = QtWidgets.QLabel("")
        self.stats_label.setStyleSheet("color: palette(mid); font-size: 11px;")
        layout.addWidget(self.stats_label)

    def set_engram(self, engram: EngramMemory):
        """Set the Engram instance and load activity."""
        self._engram = engram
        self._refresh()

    def _refresh(self):
        """Refresh activity list."""
        self.activity_list.clear()

        if not self._engram:
            self.stats_label.setText("No project loaded")
            return

        try:
            recent = self._engram.get_recent(30)
            total = self._engram.store.count()

            self.stats_label.setText(f"Total memories: {total}")

            type_icons = {
                MemoryType.CONTEXT: "[CTX]",
                MemoryType.DECISION: "[DEC]",
                MemoryType.TASK: "[TSK]",
                MemoryType.ACTION: "[ACT]",
                MemoryType.NOTE: "[NOTE]",
                MemoryType.REFERENCE: "[REF]",
                MemoryType.FEEDBACK: "[FB]",
                MemoryType.ERROR: "[ERR]",
                MemoryType.SUMMARY: "[SUM]",
            }

            for memory in recent:
                icon = type_icons.get(memory.memory_type, "[?]")
                time_str = memory.created_at.split("T")[1][:5] if "T" in memory.created_at else ""
                text = f"{time_str} {icon} {memory.summary}"

                item = QtWidgets.QListWidgetItem(text)
                item.setData(QtCore.Qt.UserRole, memory)

                # Color by type - using Houdini standard colors
                if memory.memory_type == MemoryType.ERROR:
                    item.setForeground(QtGui.QColor("#F44336"))  # Houdini red
                elif memory.memory_type == MemoryType.DECISION:
                    item.setForeground(QtGui.QColor("#4CAF50"))  # Houdini green

                self.activity_list.addItem(item)

        except Exception as e:
            self.stats_label.setText(f"Error: {e}")


# =============================================================================
# MAIN PANEL
# =============================================================================

class EngramPanel(QtWidgets.QWidget):
    """Main Engram panel with tabs for context, decisions, search, and activity."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._engram: Optional[EngramMemory] = None
        self._setup_ui()
        self._init_engram()

        # Auto-refresh timer
        self._refresh_timer = QtCore.QTimer()
        self._refresh_timer.timeout.connect(self._check_project_change)
        self._refresh_timer.start(5000)  # Check every 5 seconds

        self._last_hip = ""

    def _setup_ui(self):
        # No custom stylesheet - inherit Houdini's native Qt theme
        self.setWindowTitle("Engram - Project Memory")
        self.setMinimumSize(300, 250)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # Header section - Houdini native styling
        header_layout = QtWidgets.QHBoxLayout()

        title = QtWidgets.QLabel("ENGRAM")
        title.setStyleSheet("font-size: 24px; font-weight: bold;")
        header_layout.addWidget(title)

        subtitle = QtWidgets.QLabel("Project Memory")
        subtitle.setStyleSheet("color: palette(mid); font-size: 11px;")
        header_layout.addWidget(subtitle)

        header_layout.addStretch()

        version_label = QtWidgets.QLabel(f"v{__version__}")
        version_label.setStyleSheet("color: palette(mid); font-size: 10px;")
        header_layout.addWidget(version_label)

        layout.addLayout(header_layout)

        # Project status group
        status_group = QtWidgets.QGroupBox("Memory Status")
        status_layout = QtWidgets.QFormLayout(status_group)

        # Status indicator - Houdini native colors
        self.status_indicator = QtWidgets.QLabel("○ No Project")
        self.status_indicator.setStyleSheet("font-weight: bold; color: palette(mid);")
        status_layout.addRow("Status:", self.status_indicator)

        self.project_label = QtWidgets.QLabel("untitled")
        status_layout.addRow("Project:", self.project_label)

        self.memory_count_label = QtWidgets.QLabel("0")
        status_layout.addRow("Memories:", self.memory_count_label)

        layout.addWidget(status_group)

        # Storage path group
        storage_group = QtWidgets.QGroupBox("Storage Location")
        storage_layout = QtWidgets.QVBoxLayout(storage_group)

        self.storage_label = QtWidgets.QLabel("$HIP/.engram/")
        self.storage_label.setStyleSheet("font-family: monospace;")
        self.storage_label.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
        storage_layout.addWidget(self.storage_label)

        open_folder_btn = QtWidgets.QPushButton("Open Folder")
        open_folder_btn.clicked.connect(self._open_folder)
        storage_layout.addWidget(open_folder_btn)

        layout.addWidget(storage_group)

        # Tabs - no emojis, Houdini native labels
        self.tabs = QtWidgets.QTabWidget()

        self.context_tab = ContextTab()
        self.tabs.addTab(self.context_tab, "Context")

        self.decisions_tab = DecisionsTab()
        self.tabs.addTab(self.decisions_tab, "Decisions")

        self.search_tab = SearchTab()
        self.tabs.addTab(self.search_tab, "Search")

        self.activity_tab = ActivityTab()
        self.tabs.addTab(self.activity_tab, "Activity")

        layout.addWidget(self.tabs)

        # Footer controls - Houdini native button styling
        controls = QtWidgets.QHBoxLayout()

        self.reload_btn = QtWidgets.QPushButton("Reload")
        self.reload_btn.clicked.connect(self._reload_project)
        controls.addWidget(self.reload_btn)

        controls.addStretch()

        self.clear_btn = QtWidgets.QPushButton("Clear All")
        self.clear_btn.clicked.connect(self._clear_memories)
        controls.addWidget(self.clear_btn)

        layout.addLayout(controls)

    def _init_engram(self):
        """Initialize Engram for current project."""
        try:
            self._engram = get_engram()
            self._update_ui()
        except Exception as e:
            print(f"[Engram Panel] Init failed: {e}")
            self._engram = None
            self._update_ui()

    def _update_ui(self):
        """Update all tabs with current Engram instance."""
        if self._engram:
            project_path = self._engram.project_path
            hip_name = Path(project_path).stem if project_path else "untitled"
            memory_count = self._engram.store.count()

            # Status indicator - Houdini native colors
            self.status_indicator.setText("● Active")
            self.status_indicator.setStyleSheet("font-weight: bold; color: #4CAF50;")  # Houdini green

            self.project_label.setText(hip_name)
            self.storage_label.setText(str(self._engram.storage_dir))
            self.memory_count_label.setText(str(memory_count))
            self._last_hip = str(project_path) if project_path else ""

            # Enable/disable clear button based on memory count
            self.clear_btn.setEnabled(memory_count > 0)
        else:
            self.status_indicator.setText("○ No Project")
            self.status_indicator.setStyleSheet("font-weight: bold; color: palette(mid);")
            self.project_label.setText("untitled")
            self.storage_label.setText("$HIP/.engram/")
            self.memory_count_label.setText("0")
            self.clear_btn.setEnabled(False)

        self.context_tab.set_engram(self._engram)
        self.decisions_tab.set_engram(self._engram)
        self.search_tab.set_engram(self._engram)
        self.activity_tab.set_engram(self._engram)

    def _check_project_change(self):
        """Check if the project has changed and reload if needed."""
        if not HOU_AVAILABLE:
            return

        try:
            current_hip = hou.hipFile.name()
            if current_hip != self._last_hip:
                print(f"[Engram] Project changed: {current_hip}")
                self._reload_project()
        except:
            pass

    def _reload_project(self):
        """Reload Engram for current project."""
        reset_engram()
        self._init_engram()

    def _clear_memories(self):
        """Clear all memories after confirmation."""
        if not self._engram:
            return

        # Confirm with user
        reply = QtWidgets.QMessageBox.question(
            self,
            "Clear All Memories",
            "⚠️ This will delete all memories for this project.\n\nAre you sure?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No
        )

        if reply == QtWidgets.QMessageBox.Yes:
            try:
                self._engram.store.clear()
                self._update_ui()
            except Exception as e:
                print(f"[Engram] Failed to clear memories: {e}")

    def _open_folder(self):
        """Open the .engram folder in file explorer."""
        if not self._engram:
            return

        folder = str(self._engram.storage_dir)
        if os.path.exists(folder):
            if os.name == 'nt':  # Windows
                os.startfile(folder)
            elif os.name == 'posix':  # macOS/Linux
                import subprocess
                subprocess.run(['open' if sys.platform == 'darwin' else 'xdg-open', folder])

    def closeEvent(self, event):
        """Handle panel close."""
        self._refresh_timer.stop()
        super().closeEvent(event)


# =============================================================================
# ENTRY POINT
# =============================================================================

def create_panel():
    """Create and show Engram panel."""
    if not QT_AVAILABLE:
        raise RuntimeError("PySide2 not available. Engram panel requires Qt.")

    panel = EngramPanel()
    if HOU_AVAILABLE and hou:
        panel.setParent(hou.qt.mainWindow(), QtCore.Qt.Window)
    panel.show()
    return panel


if __name__ == "__main__":
    create_panel()
