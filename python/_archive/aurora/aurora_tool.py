"""
Aurora UI Panel

PySide6 panel for Light Groups & AOV Manager in Houdini 21.
Agent-first design with human gate integration.
"""

import hou
from PySide6 import QtWidgets, QtCore, QtGui
from typing import Optional, List, Dict

from .manager import aurora, AuroraManager
from .models import LightGroup, LightRole, LightType, AOVDefinition
from .linking import LinkMode

from core.gates import human_gate, GateDecision, GateBatch
from core.audit import audit_log, AuditCategory, AuditLevel


__title__ = "Aurora"
__version__ = "1.0.0"
__product__ = "Aurora - Light Groups & AOV Manager"


# Role colors for UI (Muted Earthtones)
ROLE_COLORS = {
    LightRole.KEY: "#CC7722",       # Ochre - warm key highlight
    LightRole.FILL: "#A0927D",      # Warm gray-brown - soft fill
    LightRole.RIM: "#A0522D",       # Sienna - warm rim
    LightRole.BOUNCE: "#7D8B69",    # Sage green - natural bounce
    LightRole.KICK: "#B8860B",      # Goldenrod - subtle kick
    LightRole.PRACTICAL: "#8B7355", # Taupe - practical
    LightRole.ENVIRONMENT: "#6B8E6B",# Moss - environment
    LightRole.SPECULAR: "#D4C4B0",  # Warm white - specular
    LightRole.CUSTOM: "#705446",    # Brown gray
}


class LightGroupWidget(QtWidgets.QFrame):
    """Widget displaying a single light group"""

    group_selected = QtCore.Signal(str)
    group_deleted = QtCore.Signal(str)

    def __init__(self, group: LightGroup, parent=None):
        super().__init__(parent)
        self.group = group
        self._init_ui()

    def _init_ui(self):
        self.setFrameStyle(QtWidgets.QFrame.StyledPanel)
        self.setStyleSheet(f"""
            QFrame {{
                background: #1a1915;
                border: 2px solid {self.group.color_tag};
                border-radius: 8px;
                padding: 8px;
            }}
            QFrame:hover {{
                border-color: #C19A6B;
            }}
        """)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(4)

        # Header row
        header = QtWidgets.QHBoxLayout()

        # Color indicator
        color_dot = QtWidgets.QLabel()
        color_dot.setFixedSize(12, 12)
        color_dot.setStyleSheet(f"""
            background: {self.group.color_tag};
            border-radius: 6px;
        """)
        header.addWidget(color_dot)

        # Name and role
        name_label = QtWidgets.QLabel(self.group.name)
        name_label.setStyleSheet("font-weight: bold; font-size: 14px; color: #FFF;")
        header.addWidget(name_label)

        role_label = QtWidgets.QLabel(f"[{self.group.role.value}]")
        role_label.setStyleSheet(f"color: {ROLE_COLORS.get(self.group.role, '#888')};")
        header.addWidget(role_label)

        header.addStretch()

        # Light count
        count_label = QtWidgets.QLabel(f"{len(self.group.members)} lights")
        count_label.setStyleSheet("color: #888;")
        header.addWidget(count_label)

        # Enable toggle
        enable_cb = QtWidgets.QCheckBox()
        enable_cb.setChecked(self.group.enabled)
        enable_cb.toggled.connect(self._on_enable_toggle)
        enable_cb.setToolTip("Enable/disable group")
        header.addWidget(enable_cb)

        layout.addLayout(header)

        # Light list (collapsed by default)
        self.light_list = QtWidgets.QListWidget()
        self.light_list.setMaximumHeight(80)
        self.light_list.setStyleSheet("""
            QListWidget {
                background: #0d0c0a;
                border: 1px solid #3d3830;
                font-size: 11px;
            }
            QListWidget::item {
                padding: 2px;
                color: #AAA;
            }
        """)
        self.light_list.setVisible(False)

        for member in self.group.members:
            item = QtWidgets.QListWidgetItem(member.prim_path.split("/")[-1])
            item.setToolTip(member.prim_path)
            if not member.enabled:
                item.setForeground(QtGui.QColor("#555"))
            self.light_list.addItem(item)

        layout.addWidget(self.light_list)

        # AOV indicators
        aov_row = QtWidgets.QHBoxLayout()
        aov_row.setSpacing(4)

        if self.group.generate_diffuse:
            aov_row.addWidget(self._aov_badge("D", "Diffuse"))
        if self.group.generate_specular:
            aov_row.addWidget(self._aov_badge("S", "Specular"))
        if self.group.generate_transmission:
            aov_row.addWidget(self._aov_badge("T", "Transmission"))
        if self.group.generate_shadow:
            aov_row.addWidget(self._aov_badge("Sh", "Shadow"))

        aov_row.addStretch()

        # Expand/collapse button
        expand_btn = QtWidgets.QPushButton("...")
        expand_btn.setFixedSize(24, 20)
        expand_btn.setStyleSheet("font-size: 10px;")
        expand_btn.clicked.connect(self._toggle_expand)
        aov_row.addWidget(expand_btn)

        # Delete button
        delete_btn = QtWidgets.QPushButton("x")
        delete_btn.setFixedSize(20, 20)
        delete_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #8B4513;
                font-weight: bold;
                border: none;
            }
            QPushButton:hover {
                color: #A0522D;
            }
        """)
        delete_btn.clicked.connect(lambda: self.group_deleted.emit(self.group.name))
        aov_row.addWidget(delete_btn)

        layout.addLayout(aov_row)

        # Click handler
        self.mousePressEvent = lambda e: self.group_selected.emit(self.group.name)

    def _aov_badge(self, text: str, tooltip: str) -> QtWidgets.QLabel:
        badge = QtWidgets.QLabel(text)
        badge.setStyleSheet("""
            background: #3d3830;
            color: #C19A6B;
            padding: 2px 6px;
            border-radius: 3px;
            font-size: 10px;
            font-weight: bold;
        """)
        badge.setToolTip(tooltip)
        return badge

    def _toggle_expand(self):
        self.light_list.setVisible(not self.light_list.isVisible())

    def _on_enable_toggle(self, enabled: bool):
        self.group.enabled = enabled
        aurora().session.light_groups[self.group.name] = self.group


class AOVListWidget(QtWidgets.QWidget):
    """Widget displaying AOV configuration"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Bundle selector
        bundle_row = QtWidgets.QHBoxLayout()
        bundle_row.addWidget(QtWidgets.QLabel("Bundle:"))

        self.bundle_combo = QtWidgets.QComboBox()
        self.bundle_combo.currentTextChanged.connect(self._on_bundle_change)
        bundle_row.addWidget(self.bundle_combo)

        layout.addLayout(bundle_row)

        # AOV tree
        self.aov_tree = QtWidgets.QTreeWidget()
        self.aov_tree.setHeaderLabels(["Name", "Type", "Source/LPE"])
        self.aov_tree.setColumnWidth(0, 150)
        self.aov_tree.setColumnWidth(1, 70)
        self.aov_tree.setStyleSheet("""
            QTreeWidget {
                background: #0d0c0a;
                border: 1px solid #3d3830;
            }
            QTreeWidget::item {
                padding: 4px;
            }
            QTreeWidget::item:selected {
                background: #2d261e;
            }
        """)

        layout.addWidget(self.aov_tree)

        self.refresh()

    def refresh(self):
        mgr = aurora()

        # Update bundle combo
        self.bundle_combo.blockSignals(True)
        self.bundle_combo.clear()
        for bundle in mgr.get_available_bundles():
            self.bundle_combo.addItem(bundle)
        self.bundle_combo.setCurrentText(mgr.session.active_bundle)
        self.bundle_combo.blockSignals(False)

        # Update AOV tree
        self.aov_tree.clear()
        aovs = mgr.get_all_aovs()

        # Group by category
        bundle_aovs = []
        group_aovs = {}
        custom_aovs = []

        for aov in aovs:
            if aov.light_group:
                if aov.light_group not in group_aovs:
                    group_aovs[aov.light_group] = []
                group_aovs[aov.light_group].append(aov)
            elif aov in mgr.session.custom_aovs:
                custom_aovs.append(aov)
            else:
                bundle_aovs.append(aov)

        # Bundle AOVs
        if bundle_aovs:
            bundle_item = QtWidgets.QTreeWidgetItem(["Bundle AOVs", "", ""])
            bundle_item.setExpanded(True)
            for aov in bundle_aovs:
                child = QtWidgets.QTreeWidgetItem([
                    aov.name,
                    aov.aov_type.value,
                    aov.lpe or aov.source or "-"
                ])
                bundle_item.addChild(child)
            self.aov_tree.addTopLevelItem(bundle_item)

        # Light group AOVs
        for group_name, aov_list in group_aovs.items():
            group_item = QtWidgets.QTreeWidgetItem([f"Group: {group_name}", "", ""])
            group_item.setExpanded(True)
            for aov in aov_list:
                child = QtWidgets.QTreeWidgetItem([
                    aov.name,
                    aov.aov_type.value,
                    aov.lpe[:40] + "..." if len(aov.lpe) > 40 else aov.lpe
                ])
                group_item.addChild(child)
            self.aov_tree.addTopLevelItem(group_item)

        # Custom AOVs
        if custom_aovs:
            custom_item = QtWidgets.QTreeWidgetItem(["Custom AOVs", "", ""])
            custom_item.setExpanded(True)
            for aov in custom_aovs:
                child = QtWidgets.QTreeWidgetItem([
                    aov.name,
                    aov.aov_type.value,
                    aov.lpe or aov.source or "-"
                ])
                custom_item.addChild(child)
            self.aov_tree.addTopLevelItem(custom_item)

    def _on_bundle_change(self, bundle_name: str):
        aurora().set_active_bundle(bundle_name)
        self.refresh()


class GatePendingWidget(QtWidgets.QWidget):
    """Widget showing pending gate approvals"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Header
        header = QtWidgets.QHBoxLayout()
        header.addWidget(QtWidgets.QLabel("Pending Approvals"))

        self.count_label = QtWidgets.QLabel("0")
        self.count_label.setStyleSheet("color: #CC7722; font-weight: bold;")
        header.addWidget(self.count_label)

        header.addStretch()

        refresh_btn = QtWidgets.QPushButton("Refresh")
        refresh_btn.clicked.connect(self.refresh)
        header.addWidget(refresh_btn)

        layout.addLayout(header)

        # Pending list
        self.pending_list = QtWidgets.QListWidget()
        self.pending_list.setStyleSheet("""
            QListWidget {
                background: #0d0c0a;
                border: 1px solid #3d3830;
            }
            QListWidget::item {
                padding: 8px;
                border-bottom: 1px solid #2d261e;
            }
            QListWidget::item:selected {
                background: #2d261e;
            }
        """)
        layout.addWidget(self.pending_list)

        # Actions
        actions = QtWidgets.QHBoxLayout()

        self.approve_btn = QtWidgets.QPushButton("Approve Selected")
        self.approve_btn.setStyleSheet("""
            QPushButton {
                background: #7D8B69;
                color: #FFF;
                padding: 8px 16px;
                font-weight: bold;
            }
        """)
        self.approve_btn.clicked.connect(self._approve_selected)
        actions.addWidget(self.approve_btn)

        self.reject_btn = QtWidgets.QPushButton("Reject Selected")
        self.reject_btn.setStyleSheet("""
            QPushButton {
                background: #8B4513;
                color: #FFF;
                padding: 8px 16px;
                font-weight: bold;
            }
        """)
        self.reject_btn.clicked.connect(self._reject_selected)
        actions.addWidget(self.reject_btn)

        self.approve_all_btn = QtWidgets.QPushButton("Approve All")
        self.approve_all_btn.clicked.connect(self._approve_all)
        actions.addWidget(self.approve_all_btn)

        layout.addLayout(actions)

        self.refresh()

    def refresh(self):
        self.pending_list.clear()
        proposals = human_gate().get_pending()
        self.count_label.setText(str(len(proposals)))

        for proposal in proposals:
            item = QtWidgets.QListWidgetItem()
            item.setData(QtCore.Qt.UserRole, proposal.proposal_id)

            text = f"[{proposal.level.value.upper()}] {proposal.operation}\n"
            text += f"{proposal.description}\n"
            text += f"Confidence: {proposal.confidence:.0%}"
            item.setText(text)

            self.pending_list.addItem(item)

    def _approve_selected(self):
        items = self.pending_list.selectedItems()
        for item in items:
            proposal_id = item.data(QtCore.Qt.UserRole)
            human_gate().decide(proposal_id, GateDecision.APPROVED, "aurora_user")
        self.refresh()

    def _reject_selected(self):
        items = self.pending_list.selectedItems()
        for item in items:
            proposal_id = item.data(QtCore.Qt.UserRole)
            human_gate().decide(proposal_id, GateDecision.REJECTED, "aurora_user")
        self.refresh()

    def _approve_all(self):
        sequence_id = aurora().sequence_id
        if sequence_id:
            human_gate().approve_all(sequence_id, "aurora_user", "Batch approved from Aurora UI")
        self.refresh()


class AuroraPanel(QtWidgets.QWidget):
    """Main Aurora panel"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._mgr = aurora()
        self._init_ui()
        self._connect_signals()

    def _init_ui(self):
        self.setWindowTitle(__product__)
        self.setMinimumSize(400, 600)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(5)

        # Header
        header_widget = QtWidgets.QWidget()
        header_widget.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        header_layout = QtWidgets.QVBoxLayout(header_widget)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(2)

        header = QtWidgets.QLabel("AURORA")
        header.setStyleSheet("font-size: 84px; font-weight: bold; color: #C19A6B; padding: 10px 20px;")
        header.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        header_layout.addWidget(header)

        subtitle = QtWidgets.QLabel("Light Groups & AOV Manager")
        subtitle.setStyleSheet("color: #888; font-size: 25px; padding-left: 20px;")
        subtitle.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        header_layout.addWidget(subtitle)

        version_label = QtWidgets.QLabel(f"v{__version__} | Agent-First Design")
        version_label.setStyleSheet("color: #666; font-size: 10px; padding-left: 20px;")
        version_label.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        header_layout.addWidget(version_label)

        layout.addWidget(header_widget)

        # Sequence selector
        seq_row = QtWidgets.QHBoxLayout()
        seq_row.addWidget(QtWidgets.QLabel("Sequence:"))

        self.sequence_input = QtWidgets.QLineEdit()
        self.sequence_input.setPlaceholderText("shot_010")
        self.sequence_input.setText(self._mgr.sequence_id)
        self.sequence_input.editingFinished.connect(self._on_sequence_change)
        seq_row.addWidget(self.sequence_input)

        layout.addLayout(seq_row)

        # Tab widget
        tabs = QtWidgets.QTabWidget()
        tabs.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #3d3830;
                background: #1a1915;
            }
            QTabBar::tab {
                background: #0d0c0a;
                padding: 8px 16px;
                border: 1px solid #3d3830;
            }
            QTabBar::tab:selected {
                background: #1a1915;
                border-bottom: 2px solid #C19A6B;
            }
        """)

        # Light Groups tab
        groups_tab = QtWidgets.QWidget()
        groups_layout = QtWidgets.QVBoxLayout(groups_tab)

        # Toolbar
        toolbar = QtWidgets.QHBoxLayout()

        add_group_btn = QtWidgets.QPushButton("+ Add Group")
        add_group_btn.setStyleSheet("""
            QPushButton {
                background: #C19A6B;
                color: #000;
                padding: 8px 16px;
                font-weight: bold;
                border-radius: 4px;
            }
        """)
        add_group_btn.clicked.connect(self._add_group)
        toolbar.addWidget(add_group_btn)

        auto_group_btn = QtWidgets.QPushButton("Auto-Group Scene")
        auto_group_btn.clicked.connect(self._auto_group)
        toolbar.addWidget(auto_group_btn)

        toolbar.addStretch()

        scan_btn = QtWidgets.QPushButton("Scan Stage")
        scan_btn.clicked.connect(self._scan_stage)
        toolbar.addWidget(scan_btn)

        groups_layout.addLayout(toolbar)

        # Groups scroll area
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        self.groups_container = QtWidgets.QWidget()
        self.groups_layout = QtWidgets.QVBoxLayout(self.groups_container)
        self.groups_layout.setAlignment(QtCore.Qt.AlignTop)
        self.groups_layout.setSpacing(8)

        scroll.setWidget(self.groups_container)
        groups_layout.addWidget(scroll)

        tabs.addTab(groups_tab, "Light Groups")

        # AOVs tab
        self.aov_widget = AOVListWidget()
        tabs.addTab(self.aov_widget, "AOVs")

        # Gates tab
        self.gate_widget = GatePendingWidget()
        tabs.addTab(self.gate_widget, "Approvals")

        layout.addWidget(tabs)

        # Status bar
        self.status_label = QtWidgets.QLabel("Ready")
        self.status_label.setStyleSheet("color: #888; font-size: 11px; padding: 5px;")
        layout.addWidget(self.status_label)

        self._refresh_groups()

    def _connect_signals(self):
        self._mgr.on_change(self._on_manager_change)

    def _on_manager_change(self):
        self._refresh_groups()
        self.aov_widget.refresh()
        self.gate_widget.refresh()

    def _on_sequence_change(self):
        seq = self.sequence_input.text()
        if seq:
            self._mgr.set_sequence(seq)
            self._status(f"Sequence set to: {seq}")

    def _refresh_groups(self):
        # Clear existing widgets
        while self.groups_layout.count():
            item = self.groups_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Add group widgets
        for group in self._mgr.get_light_groups():
            widget = LightGroupWidget(group)
            widget.group_selected.connect(self._on_group_selected)
            widget.group_deleted.connect(self._on_group_deleted)
            self.groups_layout.addWidget(widget)

        # Spacer
        self.groups_layout.addStretch()

    def _add_group(self):
        dialog = AddGroupDialog(self)
        if dialog.exec() == QtWidgets.QDialog.Accepted:
            name, role = dialog.get_values()
            group, proposal = self._mgr.create_light_group(
                name=name,
                role=role,
                agent_reasoning="Created from Aurora UI",
                confidence=1.0,
            )
            self._status(f"Created group: {name}")
            self._refresh_groups()

    def _auto_group(self):
        lights = self._mgr.session.scene_lights
        if not lights:
            self._status("No lights in scene cache. Run 'Scan Stage' first.")
            return

        # Build type map
        type_map = {p: "RectLight" for p in lights}  # Default

        groups, proposal = self._mgr.auto_group_lights(
            lights, type_map, gate_level=GateLevel.REVIEW
        )

        self._status(f"Auto-generated {len(groups)} groups (pending approval)")
        self._refresh_groups()
        self.gate_widget.refresh()

    def _scan_stage(self):
        """Scan USD stage for lights and geometry"""
        try:
            # Find the active LOP network
            stage_net = hou.node("/stage")
            if not stage_net:
                self._status("No /stage network found")
                return

            # Get the last LOP node
            lop_node = None
            for child in stage_net.children():
                if child.type().category().name() == "Lop":
                    lop_node = child

            if not lop_node:
                self._status("No LOP nodes in /stage")
                return

            stage = lop_node.stage()
            if not stage:
                self._status("No stage available")
                return

            # Collect lights and geometry
            lights = []
            geometry = []

            for prim in stage.Traverse():
                type_name = prim.GetTypeName()
                path = str(prim.GetPath())

                if "Light" in type_name:
                    lights.append(path)
                elif type_name in ("Mesh", "BasisCurves", "Points", "Sphere", "Cube"):
                    geometry.append(path)

            self._mgr.update_scene_cache(lights, geometry)
            self._status(f"Found {len(lights)} lights, {len(geometry)} geometry prims")

        except Exception as e:
            self._status(f"Scan error: {e}")

    def _on_group_selected(self, name: str):
        self._status(f"Selected: {name}")

    def _on_group_deleted(self, name: str):
        reply = QtWidgets.QMessageBox.question(
            self,
            "Delete Group",
            f"Delete light group '{name}'?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
        )

        if reply == QtWidgets.QMessageBox.Yes:
            self._mgr.delete_light_group(name)
            self._status(f"Deleted group: {name}")
            self._refresh_groups()

    def _status(self, msg: str):
        self.status_label.setText(msg)


class AddGroupDialog(QtWidgets.QDialog):
    """Dialog for adding a new light group"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add Light Group")
        self.setMinimumWidth(300)
        self._init_ui()

    def _init_ui(self):
        layout = QtWidgets.QFormLayout(self)

        self.name_input = QtWidgets.QLineEdit()
        self.name_input.setPlaceholderText("key_lights")
        layout.addRow("Name:", self.name_input)

        self.role_combo = QtWidgets.QComboBox()
        for role in LightRole:
            self.role_combo.addItem(role.value, role)
        layout.addRow("Role:", self.role_combo)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def get_values(self):
        return (
            self.name_input.text(),
            self.role_combo.currentData()
        )


def create_panel():
    """Create Aurora panel for Houdini"""
    panel = AuroraPanel()
    panel.setParent(hou.qt.mainWindow(), QtCore.Qt.Window)
    panel.show()
    return panel


if __name__ == "__main__":
    create_panel()
