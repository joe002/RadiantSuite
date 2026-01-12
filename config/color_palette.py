"""
RadiantSuite Color Palette - Muted Earthtones

A unified color palette for all RadiantSuite tools.
Designed for professional VFX work with warm, natural tones.
"""

# =============================================================================
# TOOL PRIMARY COLORS
# =============================================================================

AURORA_COLOR = "#C19A6B"      # Camel - Light Groups & AOV Manager
LUMEN_COLOR = "#CC7722"       # Ochre - Lighting Rig Manager
SPECTRUM_COLOR = "#D4A574"    # Warm Camel - LookDev Tool
PRISM_COLOR = "#B4846C"       # Rose Taupe - GOBO Manager
SAGE_COLOR = "#7D8B69"        # Sage Green - AI Assistant
UMBRA_COLOR = "#9A8B99"       # Mauve Gray - GOBO Presets
SYNAPSE_COLOR = "#8B7355"     # Taupe Bronze - WebSocket Bridge


# =============================================================================
# UI BACKGROUND COLORS
# =============================================================================

BG_DARK = "#0d0c0a"           # Warm black
BG_PANEL = "#1a1915"          # Warm dark brown
BG_SELECTED = "#2d261e"       # Selection highlight
BG_HOVER = "#3d3830"          # Hover state


# =============================================================================
# STATUS COLORS
# =============================================================================

STATUS_SUCCESS = "#7D8B69"    # Sage green - success
STATUS_ERROR = "#8B4513"      # Saddle brown - error/danger
STATUS_INFO = "#C19A6B"       # Camel - info/neutral


# =============================================================================
# AURORA LIGHT ROLE COLORS
# =============================================================================

ROLE_KEY = "#CC7722"          # Ochre - Key light
ROLE_FILL = "#A0927D"         # Warm gray-brown - Fill
ROLE_RIM = "#A0522D"          # Sienna - Rim
ROLE_BOUNCE = "#7D8B69"       # Sage green - Bounce
ROLE_KICK = "#B8860B"         # Goldenrod - Kick
ROLE_PRACTICAL = "#8B7355"    # Taupe - Practical
ROLE_ENVIRONMENT = "#6B8E6B"  # Moss - Environment
ROLE_SPECULAR = "#D4C4B0"     # Warm white - Specular
ROLE_CUSTOM = "#705446"       # Brown gray - Custom


# =============================================================================
# SPECTRUM MATERIAL TYPE COLORS
# =============================================================================

MAT_USD_PREVIEW = "#8B7355"   # Taupe
MAT_KARMA = "#A0522D"         # Sienna
MAT_MATERIALX = "#7D8B69"     # Sage
MAT_ARNOLD = "#CC7722"        # Ochre
MAT_RENDERMAN = "#6B4423"     # Sepia
MAT_CUSTOM = "#705446"        # Brown gray


# =============================================================================
# CSS/QT STYLESHEET SNIPPETS
# =============================================================================

STYLESHEET_SNIPPETS = {
    "dark_panel": """
        background: #1a1915;
        border: 1px solid #3d3830;
        border-radius: 8px;
    """,
    "button_primary": """
        QPushButton {
            background-color: #C19A6B;
            color: #000;
            padding: 8px 16px;
            font-weight: bold;
            border-radius: 4px;
        }
        QPushButton:hover { background-color: #D1AA7B; }
        QPushButton:disabled { background-color: #555; color: #888; }
    """,
    "button_danger": """
        QPushButton {
            background-color: #8B4513;
            color: white;
            padding: 8px 16px;
            font-weight: bold;
            border-radius: 4px;
        }
        QPushButton:hover { background-color: #A0522D; }
    """,
    "tabs": """
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
    """,
    "list_widget": """
        QListWidget {
            background: #0d0c0a;
            border: 1px solid #3d3830;
        }
        QListWidget::item {
            padding: 4px;
        }
        QListWidget::item:selected {
            background: #2d261e;
        }
    """,
}
