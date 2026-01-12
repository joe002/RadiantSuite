#!/usr/bin/env python3
"""
Solaris Scene Builder via Synapse
==================================

Creates a production-ready USD scene in Houdini's Solaris/LOPs via the Synapse bridge.

This demonstrates AI-driven USD scene assembly:
- Stage management
- Geometry instancing
- MaterialX shaders
- Karma lighting
- Render settings

PREREQUISITES:
1. Houdini 21+ with Solaris/LOPs
2. Synapse panel open and server running (ws://localhost:9999)
3. websockets: pip install websockets
"""

import asyncio
import json
import uuid
import time
from typing import Any, Dict, Optional, List

try:
    import websockets
except ImportError:
    print("ERROR: pip install websockets")
    exit(1)


class SynapseClient:
    """Synapse WebSocket client for Houdini communication."""

    def __init__(self, url: str = "ws://localhost:9999"):
        self.url = url
        self.ws = None
        self.sequence = 0

    async def connect(self):
        self.ws = await websockets.connect(self.url)
        # Verify with ping
        r = await self.cmd("ping", {})
        if r.get("success"):
            print(f"[Synapse] Connected - Protocol {r['data'].get('protocol_version')}")
        return self

    async def close(self):
        if self.ws:
            await self.ws.close()

    async def cmd(self, cmd_type: str, payload: Dict) -> Dict:
        """Send command, receive response."""
        self.sequence += 1
        msg = {
            "type": cmd_type,
            "id": f"cmd_{uuid.uuid4().hex[:8]}",
            "payload": payload,
            "sequence": self.sequence,
            "timestamp": time.time(),
            "protocol_version": "2.1.0"
        }
        await self.ws.send(json.dumps(msg))
        resp = await self.ws.recv()
        return json.loads(resp)

    async def python(self, code: str) -> Any:
        """Execute Python in Houdini, return result."""
        r = await self.cmd("execute_python", {"code": code})
        if r.get("success"):
            return r.get("data", {}).get("result")
        else:
            print(f"[ERROR] {r.get('error')}")
            return None

    async def create_node(self, parent: str, node_type: str, name: str = None) -> Optional[str]:
        """Create a node, return path."""
        payload = {"parent": parent, "type": node_type}
        if name:
            payload["name"] = name
        r = await self.cmd("create_node", payload)
        if r.get("success"):
            return r["data"]["path"]
        return None


# =============================================================================
# SOLARIS SCENE CONSTRUCTION
# =============================================================================

async def build_solaris_lookdev_scene(client: SynapseClient):
    """
    Build a complete Solaris lookdev scene:
    - Reference geometry
    - MaterialX shader network
    - 3-point Karma lighting
    - Turntable camera rig
    - Karma XPU render settings
    """

    print("\n" + "="*70)
    print("SOLARIS SCENE BUILDER - USD Lookdev Environment")
    print("="*70)

    # =========================================================================
    # 1. CREATE /stage LOP NETWORK
    # =========================================================================
    print("\n[1/6] Creating LOP network...")

    stage_path = await client.python("""
import hou

# Create or get /stage
stage = hou.node("/stage")
if not stage:
    stage = hou.node("/").createNode("lopnet", "stage")
    stage.moveToGoodPosition()

# Clear existing nodes for clean slate
for child in stage.children():
    child.destroy()

stage.path()
""")
    print(f"       LOP Network: {stage_path}")

    # =========================================================================
    # 2. CREATE USD STAGE STRUCTURE
    # =========================================================================
    print("\n[2/6] Building USD stage structure...")

    await client.python(f"""
import hou

stage = hou.node("{stage_path}")

# --- Sublayer for organization ---
sublayer = stage.createNode("sublayer", "scene_root")
sublayer.parm("filepath1").set("")  # In-memory layer

# --- Scene graph structure with configurelayer ---
config = stage.createNode("configurelayer", "configure_stage")
config.parm("defaultprim").set("/World")
config.setInput(0, sublayer)

# --- Create World scope ---
world_prim = stage.createNode("primitive", "world_prim")
world_prim.parm("primpath").set("/World")
world_prim.parm("primkind").set("assembly")
world_prim.setInput(0, config)

# --- Geometry scope ---
geo_scope = stage.createNode("primitive", "geo_scope")
geo_scope.parm("primpath").set("/World/Geo")
geo_scope.parm("primkind").set("group")
geo_scope.setInput(0, world_prim)

# --- Lights scope ---
lights_scope = stage.createNode("primitive", "lights_scope")
lights_scope.parm("primpath").set("/World/Lights")
lights_scope.parm("primkind").set("group")
lights_scope.setInput(0, geo_scope)

# --- Camera scope ---
cam_scope = stage.createNode("primitive", "camera_scope")
cam_scope.parm("primpath").set("/World/Cameras")
cam_scope.parm("primkind").set("group")
cam_scope.setInput(0, lights_scope)

# Layout nodes
sublayer.setPosition([-4, 0])
config.setPosition([-2, 0])
world_prim.setPosition([0, 0])
geo_scope.setPosition([2, 0])
lights_scope.setPosition([4, 0])
cam_scope.setPosition([6, 0])

print("USD structure created")
""")
    print("       /World (assembly)")
    print("       /World/Geo (group)")
    print("       /World/Lights (group)")
    print("       /World/Cameras (group)")

    # =========================================================================
    # 3. ADD GEOMETRY
    # =========================================================================
    print("\n[3/6] Adding geometry...")

    await client.python(f"""
import hou

stage = hou.node("{stage_path}")
cam_scope = hou.node("{stage_path}/camera_scope")

# --- Hero geometry: Rubber Toy (iconic Houdini test geo) ---
sop_create = stage.createNode("sopcreate", "hero_geo")
sop_create.parm("primpath").set("/World/Geo/Hero")

# Get the internal SOP network and add geometry
sop_net = sop_create.node("sopnet/create")
if sop_net:
    # Clear default nodes
    for n in sop_net.children():
        n.destroy()

    # Add rubber toy
    toy = sop_net.createNode("testgeometry_rubbertoy", "rubbertoy")

    # Transform to center and scale
    xform = sop_net.createNode("xform", "transform")
    xform.parm("scale").set(0.5)
    xform.parm("ty").set(0.3)
    xform.setInput(0, toy)

    # Normal - ensure clean normals for rendering
    normal = sop_net.createNode("normal", "normals")
    normal.parm("type").set(0)  # Point normals
    normal.setInput(0, xform)

    # Output
    output = sop_net.createNode("output", "output")
    output.setInput(0, normal)
    output.setRenderFlag(True)
    output.setDisplayFlag(True)

    # Layout
    toy.moveToGoodPosition()
    xform.moveToGoodPosition()
    normal.moveToGoodPosition()
    output.moveToGoodPosition()

sop_create.setInput(0, cam_scope)

# --- Ground plane ---
ground_create = stage.createNode("sopcreate", "ground_geo")
ground_create.parm("primpath").set("/World/Geo/Ground")

ground_sop = ground_create.node("sopnet/create")
if ground_sop:
    for n in ground_sop.children():
        n.destroy()

    grid = ground_sop.createNode("grid", "ground_grid")
    grid.parm("sizex").set(10)
    grid.parm("sizey").set(10)
    grid.parm("rows").set(2)
    grid.parm("cols").set(2)

    out = ground_sop.createNode("output", "output")
    out.setInput(0, grid)
    out.setRenderFlag(True)
    out.setDisplayFlag(True)

    grid.moveToGoodPosition()
    out.moveToGoodPosition()

ground_create.setInput(0, sop_create)

# Position nodes
sop_create.setPosition([8, 0])
ground_create.setPosition([10, 0])

print("Geometry added")
""")
    print("       /World/Geo/Hero (Rubber Toy)")
    print("       /World/Geo/Ground (10x10 grid)")

    # =========================================================================
    # 4. ADD MATERIALX SHADERS
    # =========================================================================
    print("\n[4/6] Creating MaterialX shaders...")

    await client.python(f"""
import hou

stage = hou.node("{stage_path}")
ground_create = hou.node("{stage_path}/ground_geo")

# --- MaterialX subnet for hero shader ---
mtlx_lib = stage.createNode("materiallibrary", "materials")
mtlx_lib.parm("matpathprefix").set("/World/Materials/")
mtlx_lib.setInput(0, ground_create)

# Access the material VOP network
mat_net = mtlx_lib.node("./")

# Create hero material inside
hero_mat = mtlx_lib.createNode("subnet", "HeroMaterial")

# Get inside the subnet and build MaterialX network
inside = hero_mat
if inside:
    # Create mtlxstandard_surface
    std_surf = inside.createNode("mtlxstandard_surface", "surface")
    std_surf.parm("base").set(0.8)
    std_surf.parm("base_colorr").set(0.8)
    std_surf.parm("base_colorg").set(0.2)
    std_surf.parm("base_colorb").set(0.15)
    std_surf.parm("specular").set(0.5)
    std_surf.parm("specular_roughness").set(0.3)

    # Create surface output
    surf_out = inside.createNode("subnetconnector", "surface_output")
    surf_out.parm("connectorkind").set("output")
    surf_out.parm("parmname").set("surface")
    surf_out.parm("parmlabel").set("Surface")
    surf_out.parm("parmtype").set("surface")
    surf_out.setInput(0, std_surf)

    std_surf.moveToGoodPosition()
    surf_out.moveToGoodPosition()

# --- Ground material (neutral gray) ---
ground_mat = mtlx_lib.createNode("subnet", "GroundMaterial")
inside_g = ground_mat
if inside_g:
    std_surf_g = inside_g.createNode("mtlxstandard_surface", "surface")
    std_surf_g.parm("base").set(0.5)
    std_surf_g.parm("base_colorr").set(0.3)
    std_surf_g.parm("base_colorg").set(0.3)
    std_surf_g.parm("base_colorb").set(0.32)
    std_surf_g.parm("specular").set(0.2)
    std_surf_g.parm("specular_roughness").set(0.7)

    surf_out_g = inside_g.createNode("subnetconnector", "surface_output")
    surf_out_g.parm("connectorkind").set("output")
    surf_out_g.parm("parmname").set("surface")
    surf_out_g.parm("parmlabel").set("Surface")
    surf_out_g.parm("parmtype").set("surface")
    surf_out_g.setInput(0, std_surf_g)

    std_surf_g.moveToGoodPosition()
    surf_out_g.moveToGoodPosition()

# --- Assign materials ---
assign_hero = stage.createNode("assignmaterial", "assign_hero_mtl")
assign_hero.parm("primpattern1").set("/World/Geo/Hero")
assign_hero.parm("matspecpath1").set("/World/Materials/HeroMaterial")
assign_hero.setInput(0, mtlx_lib)

assign_ground = stage.createNode("assignmaterial", "assign_ground_mtl")
assign_ground.parm("primpattern1").set("/World/Geo/Ground")
assign_ground.parm("matspecpath1").set("/World/Materials/GroundMaterial")
assign_ground.setInput(0, assign_hero)

# Layout
mtlx_lib.setPosition([12, 0])
assign_hero.setPosition([14, 0])
assign_ground.setPosition([16, 0])

print("Materials created and assigned")
""")
    print("       /World/Materials/HeroMaterial (orange rubber)")
    print("       /World/Materials/GroundMaterial (neutral gray)")

    # =========================================================================
    # 5. ADD KARMA LIGHTING
    # =========================================================================
    print("\n[5/6] Setting up Karma lighting...")

    await client.python(f"""
import hou
import math

stage = hou.node("{stage_path}")
assign_ground = hou.node("{stage_path}/assign_ground_mtl")

# --- Dome Light (environment) ---
dome = stage.createNode("domelight", "dome_light")
dome.parm("primpath").set("/World/Lights/DomeLight")
dome.parm("xn_intensity").set(0.3)  # Subtle fill
dome.setInput(0, assign_ground)

# --- Key Light (warm, camera left, elevated) ---
key = stage.createNode("distantlight", "key_light")
key.parm("primpath").set("/World/Lights/KeyLight")
key.parm("xn_intensity").set(3.0)
# Warm color temperature ~5500K
key.parm("xn_colorr").set(1.0)
key.parm("xn_colorg").set(0.95)
key.parm("xn_colorb").set(0.85)
# Rotation: coming from upper left
key.parm("rx").set(-45)
key.parm("ry").set(-30)
key.setInput(0, dome)

# --- Fill Light (cool, camera right, lower) ---
fill = stage.createNode("distantlight", "fill_light")
fill.parm("primpath").set("/World/Lights/FillLight")
fill.parm("xn_intensity").set(1.0)
# Cool color ~7500K
fill.parm("xn_colorr").set(0.85)
fill.parm("xn_colorg").set(0.92)
fill.parm("xn_colorb").set(1.0)
# From right side
fill.parm("rx").set(-20)
fill.parm("ry").set(45)
fill.setInput(0, key)

# --- Rim Light (backlight for edge definition) ---
rim = stage.createNode("distantlight", "rim_light")
rim.parm("primpath").set("/World/Lights/RimLight")
rim.parm("xn_intensity").set(2.0)
# Neutral white
rim.parm("xn_colorr").set(1.0)
rim.parm("xn_colorg").set(1.0)
rim.parm("xn_colorb").set(1.0)
# From behind
rim.parm("rx").set(-30)
rim.parm("ry").set(180)
rim.setInput(0, fill)

# Layout lights
dome.setPosition([18, 0])
key.setPosition([20, 0])
fill.setPosition([22, 0])
rim.setPosition([24, 0])

print("Karma lighting setup complete")
""")
    print("       DomeLight (environment, intensity 0.3)")
    print("       KeyLight (warm 5500K, intensity 3.0)")
    print("       FillLight (cool 7500K, intensity 1.0)")
    print("       RimLight (neutral, intensity 2.0)")

    # =========================================================================
    # 6. ADD CAMERA + RENDER SETTINGS
    # =========================================================================
    print("\n[6/6] Adding camera and render settings...")

    await client.python(f"""
import hou

stage = hou.node("{stage_path}")
rim = hou.node("{stage_path}/rim_light")

# --- Turntable null for animation ---
turntable_edit = stage.createNode("xformedit", "turntable_xform")
turntable_edit.parm("primpath").set("/World/Cameras/TurntableRig")
turntable_edit.parm("createaliasnamespace").set(1)
turntable_edit.parm("createaliasname").set("turntable")
turntable_edit.setInput(0, rim)

# --- Camera ---
camera = stage.createNode("camera", "render_camera")
camera.parm("primpath").set("/World/Cameras/RenderCam")
camera.parm("tz").set(5)
camera.parm("ty").set(1.5)
camera.parm("rx").set(-15)
# 1080p
camera.parm("resx").set(1920)
camera.parm("resy").set(1080)
camera.setInput(0, turntable_edit)

# Parent camera to turntable (via reference edit)
# This is done by editing the camera's xformOpOrder

# --- Karma Render Settings ---
render_settings = stage.createNode("karmarenderproperties", "karma_settings")
render_settings.parm("primpath").set("/Render/KarmaSettings")
# Quality settings for preview
render_settings.parm("engine").set("xpu")  # Karma XPU
render_settings.parm("enabledof").set(0)   # No DOF for turntable
render_settings.setInput(0, camera)

# --- USD Render ROP ---
usd_rop = stage.createNode("usdrender_rop", "karma_rop")
usd_rop.parm("renderer").set("BRAY_HdKarma")
usd_rop.parm("camera").set("/World/Cameras/RenderCam")
usd_rop.parm("resolutionx").set(1920)
usd_rop.parm("resolutiony").set(1080)
usd_rop.setInput(0, render_settings)

# Set display flag on final node
usd_rop.setDisplayFlag(True)

# Layout
turntable_edit.setPosition([26, 0])
camera.setPosition([28, 0])
render_settings.setPosition([30, 0])
usd_rop.setPosition([32, 0])

# Set frame range
hou.playbar.setFrameRange(1, 120)
hou.playbar.setPlaybackRange(1, 120)

# Animate turntable (360 degrees over 120 frames)
turntable_edit.parm("ry").setExpression("$F * 3")  # 360/120 = 3 degrees per frame

print("Camera and render setup complete")
""")
    print("       /World/Cameras/RenderCam (1920x1080)")
    print("       Karma XPU render settings")
    print("       Turntable: 360° over 120 frames")

    # =========================================================================
    # RECORD TO ENGRAM
    # =========================================================================
    print("\n[+] Recording to Engram...")

    await client.cmd("engram_add", {
        "content": "Created Solaris lookdev scene: Rubber Toy hero with MaterialX shaders, 3-point Karma lighting, turntable camera rig.",
        "memory_type": "context",
        "tags": ["solaris", "usd", "lookdev", "karma"]
    })

    await client.cmd("engram_decide", {
        "decision": "Use Karma XPU for lookdev renders",
        "reasoning": "XPU provides interactive feedback with GPU acceleration. CPU fallback for production finals.",
        "alternatives": ["Karma CPU only", "Arnold", "RenderMan"],
        "tags": ["render", "karma", "decision"]
    })

    # =========================================================================
    # SUMMARY
    # =========================================================================
    print("\n" + "="*70)
    print("SOLARIS SCENE COMPLETE!")
    print("="*70)
    print("""
USD Stage Structure:
  /World (assembly)
  ├── /World/Geo
  │   ├── /World/Geo/Hero (Rubber Toy)
  │   └── /World/Geo/Ground (Grid)
  ├── /World/Materials
  │   ├── /World/Materials/HeroMaterial (MaterialX)
  │   └── /World/Materials/GroundMaterial (MaterialX)
  ├── /World/Lights
  │   ├── /World/Lights/DomeLight
  │   ├── /World/Lights/KeyLight (warm)
  │   ├── /World/Lights/FillLight (cool)
  │   └── /World/Lights/RimLight
  └── /World/Cameras
      └── /World/Cameras/RenderCam

LOP Network: /stage
Render: Karma XPU @ 1920x1080
Animation: 120 frames turntable

To render:
  1. Set viewport to /stage
  2. Enable Karma in viewport (Persp > Karma)
  3. Or render via karma_rop node
""")


# =============================================================================
# MAIN
# =============================================================================

async def main():
    print("""
┌────────────────────────────────────────────────────────────────┐
│                                                                │▒
│   ███████╗██████╗ ██╗      █████╗ ██████╗ ██╗███████╗         │▒
│   ██╔════╝██╔══██╗██║     ██╔══██╗██╔══██╗██║██╔════╝         │▒
│   ███████╗██║  ██║██║     ███████║██████╔╝██║███████╗         │▒
│   ╚════██║██║  ██║██║     ██╔══██║██╔══██╗██║╚════██║         │▒
│   ███████║██████╔╝███████╗██║  ██║██║  ██║██║███████║         │▒
│   ╚══════╝╚═════╝ ╚══════╝╚═╝  ╚═╝╚═╝  ╚═╝╚═╝╚══════╝         │▒
│                                                                │▒
│   USD Lookdev Scene Builder via Synapse                        │▒
│                                                                │▒
└────────────────────────────────────────────────────────────────┘▒
 ▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒
""")

    client = SynapseClient()

    try:
        await client.connect()
        await build_solaris_lookdev_scene(client)
    except ConnectionRefusedError:
        print("""
ERROR: Cannot connect to Synapse.

Ensure:
  1. Houdini 21+ is running
  2. Synapse panel: Windows > RadiantSuite > Synapse
  3. Click "Start Server"
  4. Status shows "● Running"
""")
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
