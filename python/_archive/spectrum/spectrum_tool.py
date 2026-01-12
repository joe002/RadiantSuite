"""
Spectrum UI Panel

PySide6 panel for LookDev workflow in Houdini 21.
Material management, environments, and preview controls.
"""

import hou
from PySide6 import QtWidgets, QtCore, QtGui
from typing import Optional, List, Dict

from .manager import spectrum, SpectrumManager
from .models import Material, MaterialType, EnvironmentPreset, EnvironmentType


__title__ = "Spectrum"
__version__ = "1.0.0"
__product__ = "Spectrum - LookDev Tool"


# Material type colors (Muted Earthtones)
MATERIAL_TYPE_COLORS = {
    MaterialType.USD_PREVIEW_SURFACE: "#8B7355",  # Taupe
    MaterialType.KARMA_PRINCIPLED: "#A0522D",     # Sienna
    MaterialType.MATERIALX_STANDARD: "#7D8B69",   # Sage
    MaterialType.ARNOLD_STANDARD: "#CC7722",      # Ochre
    MaterialType.RENDERMAN_PXR: "#6B4423",        # Sepia
    MaterialType.CUSTOM: "#705446",               # Brown gray
}


class MaterialWidget(QtWidgets.QFrame):
    """Widget displaying a single material"""

    material_selected = QtCore.Signal(str)
    material_deleted = QtCore.Signal(str)

    def __init__(self, material: Material, is_active: bool = False, parent=None):
        super().__init__(parent)
        self.material = material
        self.is_active = is_active
        self._init_ui()

    def _init_ui(self):
        color = MATERIAL_TYPE_COLORS.get(self.material.material_type, "#705446")
        border_color = "#D4A574" if self.is_active else color

        self.setFrameStyle(QtWidgets.QFrame.StyledPanel)
        self.setStyleSheet(f"""
            QFrame {{
                background: #1a1915;
                border: 2px solid {border_color};
                border-radius: 8px;
                padding: 8px;
            }}
            QFrame:hover {{
                border-color: #D4A574;
            }}
        """)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(4)

        # Header row
        header = QtWidgets.QHBoxLayout()

        # Color indicator
        color_dot = QtWidgets.QLabel()
        color_dot.setFixedSize(12, 12)
        color_dot.setStyleSheet(f"background: {color}; border-radius: 6px;")
        header.addWidget(color_dot)

        # Name
        name_label = QtWidgets.QLabel(self.material.name)
        name_label.setStyleSheet("font-weight: bold; font-size: 14px; color: #FFF;")
        header.addWidget(name_label)

        header.addStretch()

        # Type badge
        type_label = QtWidgets.QLabel(self.material.material_type.value)
        type_label.setStyleSheet(f"""
            background: {color};
            color: #FFF;
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 10px;
        """)
        header.addWidget(type_label)

        layout.addLayout(header)

        # Parameter summary
        param_count = len(self.material.parameters)
        has_textures = self.material.texture_set is not None

        info_text = f"{param_count} params"
        if has_textures:
            tex_count = len(self.material.texture_set.textures)
            info_text += f" | {tex_count} textures"

        info_label = QtWidgets.QLabel(info_text)
        info_label.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(info_label)

        # Tags
        if self.material.tags:
            tags_label = QtWidgets.QLabel(" ".join([f"#{t}" for t in self.material.tags[:3]]))
            tags_label.setStyleSheet("color: #666; font-size: 10px;")
            layout.addWidget(tags_label)

        # Click handler
        self.mousePressEvent = lambda e: self.material_selected.emit(self.material.name)


class EnvironmentWidget(QtWidgets.QFrame):
    """Widget for environment preset selection"""

    environment_selected = QtCore.Signal(str)

    def __init__(self, preset: EnvironmentPreset, is_active: bool = False, parent=None):
        super().__init__(parent)
        self.preset = preset
        self.is_active = is_active
        self._init_ui()

    def _init_ui(self):
        border_color = "#D4A574" if self.is_active else "#3d3830"

        self.setFrameStyle(QtWidgets.QFrame.StyledPanel)
        self.setStyleSheet(f"""
            QFrame {{
                background: #1a1915;
                border: 2px solid {border_color};
                border-radius: 6px;
                padding: 6px;
            }}
            QFrame:hover {{
                border-color: #D4A574;
            }}
        """)
        self.setFixedWidth(120)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(2)
        layout.setContentsMargins(4, 4, 4, 4)

        # Preview color based on type
        preview = QtWidgets.QWidget()
        preview.setFixedHeight(50)

        if self.preset.env_type == EnvironmentType.HDRI:
            preview.setStyleSheet("background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #6B5D4A, stop:1 #2D261E); border-radius: 4px;")
        elif self.preset.env_type == EnvironmentType.PROCEDURAL_SKY:
            preview.setStyleSheet("background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #B4A68E, stop:1 #7D7059); border-radius: 4px;")
        else:
            r, g, b = self.preset.background_color
            preview.setStyleSheet(f"background: rgb({int(r*255)}, {int(g*255)}, {int(b*255)}); border-radius: 4px;")

        layout.addWidget(preview)

        # Name
        name = QtWidgets.QLabel(self.preset.name)
        name.setStyleSheet("color: #FFF; font-size: 11px;")
        name.setAlignment(QtCore.Qt.AlignCenter)
        name.setWordWrap(True)
        layout.addWidget(name)

        # Click handler
        self.mousePressEvent = lambda e: self.environment_selected.emit(self.preset.name)


class ParameterEditor(QtWidgets.QWidget):
    """Editor for material parameters"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._material: Optional[Material] = None
        self._init_ui()

    def _init_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.scroll = QtWidgets.QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet("QScrollArea { border: none; }")

        self.params_widget = QtWidgets.QWidget()
        self.params_layout = QtWidgets.QFormLayout(self.params_widget)
        self.params_layout.setSpacing(8)

        self.scroll.setWidget(self.params_widget)
        layout.addWidget(self.scroll)

    def set_material(self, material: Optional[Material]) -> None:
        """Set material to edit"""
        self._material = material
        self._refresh()

    def _refresh(self) -> None:
        # Clear existing
        while self.params_layout.rowCount() > 0:
            self.params_layout.removeRow(0)

        if not self._material:
            return

        # Group parameters
        groups: Dict[str, List] = {}
        for param in self._material.parameters:
            group = param.ui_group or "General"
            if group not in groups:
                groups[group] = []
            groups[group].append(param)

        for group_name, params in groups.items():
            # Group header
            header = QtWidgets.QLabel(group_name)
            header.setStyleSheet("font-weight: bold; color: #D4A574; margin-top: 10px;")
            self.params_layout.addRow(header)

            for param in params:
                widget = self._create_param_widget(param)
                label = param.ui_label or param.name
                self.params_layout.addRow(f"{label}:", widget)

    def _create_param_widget(self, param):
        """Create appropriate widget for parameter type"""
        if param.param_type == "float":
            widget = QtWidgets.QDoubleSpinBox()
            widget.setRange(
                param.min_value if param.min_value is not None else -9999,
                param.max_value if param.max_value is not None else 9999
            )
            widget.setSingleStep(0.01)
            widget.setValue(param.value)
            widget.setDecimals(4)
            widget.valueChanged.connect(lambda v, p=param: self._on_param_changed(p, v))
            return widget

        elif param.param_type in ("color3f", "float3"):
            widget = QtWidgets.QWidget()
            layout = QtWidgets.QHBoxLayout(widget)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(2)

            for i, (label, val) in enumerate(zip(["R", "G", "B"], param.value)):
                spin = QtWidgets.QDoubleSpinBox()
                spin.setRange(0, 2)
                spin.setSingleStep(0.01)
                spin.setValue(val)
                spin.setDecimals(3)
                spin.setPrefix(f"{label}: ")
                spin.valueChanged.connect(lambda v, p=param, idx=i: self._on_color_changed(p, idx, v))
                layout.addWidget(spin)

            return widget

        elif param.param_type == "bool":
            widget = QtWidgets.QCheckBox()
            widget.setChecked(param.value)
            widget.stateChanged.connect(lambda s, p=param: self._on_param_changed(p, s == QtCore.Qt.Checked))
            return widget

        else:
            widget = QtWidgets.QLineEdit(str(param.value))
            widget.editingFinished.connect(lambda p=param, w=widget: self._on_param_changed(p, w.text()))
            return widget

    def _on_param_changed(self, param, value):
        if self._material:
            self._material.set_parameter(param.name, value)

    def _on_color_changed(self, param, idx, value):
        if self._material:
            current = list(param.value)
            current[idx] = value
            self._material.set_parameter(param.name, tuple(current))


class SpectrumPanel(QtWidgets.QWidget):
    """Main Spectrum panel"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._mgr = spectrum()
        self._init_ui()
        self._connect_signals()

    def _init_ui(self):
        self.setWindowTitle(__product__)
        self.setMinimumSize(500, 700)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(5)

        # Header
        header_widget = QtWidgets.QWidget()
        header_widget.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        header_layout = QtWidgets.QVBoxLayout(header_widget)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(2)

        header = QtWidgets.QLabel("SPECTRUM")
        header.setStyleSheet("font-size: 84px; font-weight: bold; color: #D4A574; padding: 10px 20px;")
        header.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        header_layout.addWidget(header)

        subtitle = QtWidgets.QLabel("LookDev Tool")
        subtitle.setStyleSheet("color: #888; font-size: 25px; padding-left: 20px;")
        subtitle.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        header_layout.addWidget(subtitle)

        version_label = QtWidgets.QLabel(f"v{__version__} | Material Management")
        version_label.setStyleSheet("color: #666; font-size: 10px; padding-left: 20px;")
        version_label.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        header_layout.addWidget(version_label)

        layout.addWidget(header_widget)

        # Splitter for main content
        splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)

        # Left panel - Materials
        left_panel = QtWidgets.QWidget()
        left_layout = QtWidgets.QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)

        # Materials header with search
        mat_header = QtWidgets.QVBoxLayout()
        mat_header.setContentsMargins(0, 0, 0, 0)
        mat_header.setSpacing(4)

        # Title row
        title_row = QtWidgets.QHBoxLayout()
        mat_label = QtWidgets.QLabel("Materials")
        mat_label.setStyleSheet("font-weight: bold; color: #D4A574;")
        title_row.addWidget(mat_label)
        title_row.addStretch()

        # Refresh button
        refresh_btn = QtWidgets.QPushButton("↻")
        refresh_btn.setFixedSize(24, 24)
        refresh_btn.setToolTip("Refresh material list")
        refresh_btn.clicked.connect(self._refresh_materials)
        title_row.addWidget(refresh_btn)

        mat_header.addLayout(title_row)

        # Search filter
        self.search_input = QtWidgets.QLineEdit()
        self.search_input.setPlaceholderText("Filter materials...")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.setStyleSheet("""
            QLineEdit {
                background: #0d0c0a;
                border: 1px solid #3d3830;
                padding: 6px;
                color: #E8E0D8;
                border-radius: 4px;
            }
            QLineEdit:focus { border-color: #D4A574; }
        """)
        self.search_input.textChanged.connect(self._filter_materials)
        mat_header.addWidget(self.search_input)

        # Action buttons row
        action_row = QtWidgets.QHBoxLayout()
        action_row.setSpacing(4)

        add_mat_btn = QtWidgets.QPushButton("+ New")
        add_mat_btn.setStyleSheet("""
            QPushButton { background: #D4A574; color: #000; padding: 6px 12px; font-weight: bold; border-radius: 4px; }
            QPushButton:hover { background: #E4B584; }
        """)
        add_mat_btn.clicked.connect(self._add_material)
        action_row.addWidget(add_mat_btn)

        dup_btn = QtWidgets.QPushButton("Duplicate")
        dup_btn.setStyleSheet("""
            QPushButton { background: #3d3830; color: #E8E0D8; padding: 6px 12px; border-radius: 4px; }
            QPushButton:hover { background: #4d4840; }
        """)
        dup_btn.clicked.connect(self._duplicate_material)
        action_row.addWidget(dup_btn)

        del_btn = QtWidgets.QPushButton("Delete")
        del_btn.setStyleSheet("""
            QPushButton { background: #3d3830; color: #8B4513; padding: 6px 12px; border-radius: 4px; }
            QPushButton:hover { background: #4d4840; }
        """)
        del_btn.clicked.connect(self._delete_material)
        action_row.addWidget(del_btn)

        mat_header.addLayout(action_row)

        left_layout.addLayout(mat_header)

        # Materials scroll - RadiantSuite standard
        self.materials_scroll = QtWidgets.QScrollArea()
        self.materials_scroll.setWidgetResizable(True)
        self.materials_scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        self.materials_container = QtWidgets.QWidget()
        self.materials_layout = QtWidgets.QVBoxLayout(self.materials_container)
        self.materials_layout.setAlignment(QtCore.Qt.AlignTop)
        self.materials_layout.setSpacing(8)

        self.materials_scroll.setWidget(self.materials_container)
        left_layout.addWidget(self.materials_scroll)

        splitter.addWidget(left_panel)

        # Right panel - Editor
        right_panel = QtWidgets.QWidget()
        right_layout = QtWidgets.QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)

        # Tabs - RadiantSuite standard styling
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
                border-bottom: 2px solid #D4A574;
            }
        """)

        # Parameters tab
        self.param_editor = ParameterEditor()
        tabs.addTab(self.param_editor, "Parameters")

        # Environments tab
        env_tab = QtWidgets.QWidget()
        env_layout = QtWidgets.QVBoxLayout(env_tab)

        self.env_grid = QtWidgets.QWidget()
        self.env_grid_layout = QtWidgets.QGridLayout(self.env_grid)
        self.env_grid_layout.setSpacing(8)

        env_scroll = QtWidgets.QScrollArea()
        env_scroll.setWidgetResizable(True)
        env_scroll.setWidget(self.env_grid)
        env_layout.addWidget(env_scroll)

        # HDRI controls - RadiantSuite standard
        hdri_controls = QtWidgets.QGroupBox("HDRI Controls")
        hdri_layout = QtWidgets.QFormLayout(hdri_controls)

        self.rotation_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.rotation_slider.setRange(0, 360)
        self.rotation_slider.valueChanged.connect(self._on_rotation_changed)
        hdri_layout.addRow("Rotation:", self.rotation_slider)

        self.intensity_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.intensity_slider.setRange(0, 200)
        self.intensity_slider.setValue(100)
        self.intensity_slider.valueChanged.connect(self._on_intensity_changed)
        hdri_layout.addRow("Intensity:", self.intensity_slider)

        env_layout.addWidget(hdri_controls)

        tabs.addTab(env_tab, "Environment")

        # Comparison tab - RadiantSuite standard
        comp_tab = QtWidgets.QWidget()
        comp_layout = QtWidgets.QVBoxLayout(comp_tab)

        self.comp_enabled = QtWidgets.QCheckBox("Enable A/B Comparison")
        self.comp_enabled.toggled.connect(self._toggle_comparison)
        comp_layout.addWidget(self.comp_enabled)

        comp_row = QtWidgets.QHBoxLayout()
        comp_row.addWidget(QtWidgets.QLabel("A:"))
        self.mat_a_combo = QtWidgets.QComboBox()
        comp_row.addWidget(self.mat_a_combo)
        comp_row.addWidget(QtWidgets.QLabel("B:"))
        self.mat_b_combo = QtWidgets.QComboBox()
        comp_row.addWidget(self.mat_b_combo)

        swap_btn = QtWidgets.QPushButton("Swap")
        swap_btn.clicked.connect(self._swap_comparison)
        comp_row.addWidget(swap_btn)

        comp_layout.addLayout(comp_row)
        comp_layout.addStretch()

        tabs.addTab(comp_tab, "Compare")

        right_layout.addWidget(tabs)

        splitter.addWidget(right_panel)
        splitter.setSizes([300, 400])

        layout.addWidget(splitter)

        # Apply to Selection workflow - critical for artists
        apply_group = QtWidgets.QGroupBox("Apply to Scene")
        apply_group.setStyleSheet("""
            QGroupBox { font-weight: bold; color: #D4A574; border: 1px solid #3d3830; border-radius: 6px; margin-top: 8px; padding-top: 8px; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; }
        """)
        apply_layout = QtWidgets.QHBoxLayout(apply_group)
        apply_layout.setContentsMargins(8, 16, 8, 8)

        apply_btn = QtWidgets.QPushButton("Apply to Selected Geometry")
        apply_btn.setStyleSheet("""
            QPushButton { background: #D4A574; color: #000; padding: 10px 20px; font-weight: bold; border-radius: 5px; }
            QPushButton:hover { background: #E4B584; }
            QPushButton:disabled { background: #555; color: #888; }
        """)
        apply_btn.clicked.connect(self._apply_to_selection)
        apply_layout.addWidget(apply_btn)

        assign_mode = QtWidgets.QComboBox()
        assign_mode.addItems(["Replace", "Add", "Override"])
        assign_mode.setStyleSheet("padding: 8px;")
        assign_mode.setToolTip("Material assignment mode")
        self.assign_mode = assign_mode
        apply_layout.addWidget(assign_mode)

        layout.addWidget(apply_group)

        # Status bar - RadiantSuite standard
        self.status_label = QtWidgets.QLabel("Ready")
        self.status_label.setStyleSheet("color: #888; font-size: 11px; padding: 5px;")
        layout.addWidget(self.status_label)

        # Initial refresh
        self._refresh_materials()
        self._refresh_environments()

    def _connect_signals(self):
        self._mgr.on_change(self._on_manager_change)

    def _on_manager_change(self):
        self._refresh_materials()
        self._refresh_environments()
        self._refresh_comparison_combos()

    def _refresh_materials(self):
        # Clear existing
        while self.materials_layout.count():
            item = self.materials_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        active = self._mgr.session.active_material

        for material in self._mgr.materials.get_all_materials():
            widget = MaterialWidget(material, material.name == active)
            widget.material_selected.connect(self._on_material_selected)
            self.materials_layout.addWidget(widget)

        self.materials_layout.addStretch()

        # Update parameter editor
        if active:
            self.param_editor.set_material(self._mgr.materials.get_material(active))
        else:
            self.param_editor.set_material(None)

    def _refresh_environments(self):
        # Clear grid
        while self.env_grid_layout.count():
            item = self.env_grid_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        active = self._mgr.session.active_environment
        presets = self._mgr.environments.get_all_presets()

        row = 0
        col = 0
        for preset in presets:
            widget = EnvironmentWidget(preset, preset.name == active)
            widget.environment_selected.connect(self._on_environment_selected)
            self.env_grid_layout.addWidget(widget, row, col)
            col += 1
            if col >= 4:
                col = 0
                row += 1

    def _refresh_comparison_combos(self):
        materials = [m.name for m in self._mgr.materials.get_all_materials()]

        self.mat_a_combo.clear()
        self.mat_b_combo.clear()

        self.mat_a_combo.addItems(materials)
        self.mat_b_combo.addItems(materials)

    def _add_material(self):
        name, ok = QtWidgets.QInputDialog.getText(
            self, "New Material", "Material name:"
        )
        if ok and name:
            self._mgr.create_material(name)
            self._status(f"Created material: {name}")

    def _on_material_selected(self, name: str):
        self._mgr.set_active_material(name)
        self._status(f"Selected: {name}")
        self._refresh_materials()

    def _on_environment_selected(self, name: str):
        self._mgr.set_active_environment(name)
        self._status(f"Environment: {name}")
        self._refresh_environments()

    def _on_rotation_changed(self, value: int):
        self._mgr.rotate_hdri(float(value))

    def _on_intensity_changed(self, value: int):
        self._mgr.adjust_environment_intensity(value / 100.0)

    def _toggle_comparison(self, enabled: bool):
        if enabled:
            mat_a = self.mat_a_combo.currentText()
            mat_b = self.mat_b_combo.currentText()
            if mat_a and mat_b:
                self._mgr.enable_comparison(mat_a, mat_b)
        else:
            self._mgr.disable_comparison()

    def _swap_comparison(self):
        self._mgr.swap_comparison()
        # Update combos
        self.mat_a_combo.setCurrentText(self._mgr.session.comparison_material_a)
        self.mat_b_combo.setCurrentText(self._mgr.session.comparison_material_b)

    def _filter_materials(self, filter_text: str):
        """Filter visible materials by name"""
        filter_lower = filter_text.lower()
        for i in range(self.materials_layout.count()):
            item = self.materials_layout.itemAt(i)
            if item and item.widget():
                widget = item.widget()
                if hasattr(widget, 'material'):
                    visible = filter_lower in widget.material.name.lower()
                    widget.setVisible(visible)

    def _duplicate_material(self):
        """Duplicate the currently selected material"""
        active = self._mgr.session.active_material
        if not active:
            self._status("Select a material to duplicate")
            return

        source = self._mgr.materials.get_material(active)
        if not source:
            return

        name, ok = QtWidgets.QInputDialog.getText(
            self, "Duplicate Material", "New name:",
            text=f"{active}_copy"
        )
        if ok and name:
            self._mgr.duplicate_material(active, name)
            self._status(f"Duplicated: {active} → {name}")

    def _delete_material(self):
        """Delete the currently selected material"""
        active = self._mgr.session.active_material
        if not active:
            self._status("Select a material to delete")
            return

        reply = QtWidgets.QMessageBox.question(
            self, "Delete Material",
            f"Delete '{active}'?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
        )

        if reply == QtWidgets.QMessageBox.Yes:
            self._mgr.delete_material(active)
            self._status(f"Deleted: {active}")

    def _apply_to_selection(self):
        """Apply current material to selected geometry in Solaris"""
        active = self._mgr.session.active_material
        if not active:
            self._status("Select a material first")
            return

        selected = hou.selectedNodes()
        lop_nodes = [n for n in selected if n.type().category().name() == "Lop"]

        if not lop_nodes:
            self._status("Select a LOP node with geometry")
            return

        mode = self.assign_mode.currentText().lower()

        try:
            count = self._mgr.apply_material_to_selection(active, lop_nodes, mode)
            self._status(f"Applied '{active}' to {count} prim(s)")
        except Exception as e:
            self._status(f"Error: {e}")

    def _status(self, msg: str):
        self.status_label.setText(msg)


def create_panel():
    """Create Spectrum panel for Houdini"""
    panel = SpectrumPanel()
    panel.setParent(hou.qt.mainWindow(), QtCore.Qt.Window)
    panel.show()
    return panel


if __name__ == "__main__":
    create_panel()
