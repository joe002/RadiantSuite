"""
Synapse Demo - AI-Driven Scene Creation
========================================

This script demonstrates how an AI assistant (Claude Code, Cursor, Gemini CLI)
can create and manipulate Houdini scenes through the Synapse WebSocket bridge.

PREREQUISITES:
1. Houdini 21+ running
2. Synapse panel open (Windows > RadiantSuite > Synapse)
3. Server started (click "Start Server")
4. websockets library: pip install websockets

USAGE:
    python synapse_demo.py

The script will:
1. Connect to Synapse at ws://localhost:9999
2. Create a procedural scene with geometry
3. Set up basic lighting
4. Configure render settings
5. Record decisions to Engram memory
"""

import asyncio
import json
import uuid
import time
from typing import Any, Dict, Optional

try:
    import websockets
except ImportError:
    print("ERROR: websockets library required")
    print("Install with: pip install websockets")
    exit(1)


# =============================================================================
# SYNAPSE CLIENT
# =============================================================================

class SynapseClient:
    """WebSocket client for Synapse - AI to Houdini bridge."""

    def __init__(self, url: str = "ws://localhost:9999"):
        self.url = url
        self.ws = None
        self.sequence = 0
        self.protocol_version = "2.1.0"

    async def connect(self):
        """Connect to Synapse server."""
        print(f"Connecting to {self.url}...")
        self.ws = await websockets.connect(self.url)
        print("Connected to Synapse!")

        # Verify connection with ping
        response = await self.send_command("ping", {})
        if response.get("success"):
            print(f"Server ready - Protocol {response.get('data', {}).get('protocol_version', 'unknown')}")
        return self

    async def disconnect(self):
        """Disconnect from Synapse."""
        if self.ws:
            await self.ws.close()
            print("Disconnected from Synapse")

    async def send_command(self, cmd_type: str, payload: Dict[str, Any]) -> Dict:
        """Send a command and wait for response."""
        self.sequence += 1

        command = {
            "type": cmd_type,
            "id": f"cmd_{uuid.uuid4().hex[:12]}",
            "payload": payload,
            "sequence": self.sequence,
            "timestamp": time.time(),
            "protocol_version": self.protocol_version
        }

        await self.ws.send(json.dumps(command))
        response = await self.ws.recv()
        return json.loads(response)

    # -------------------------------------------------------------------------
    # Node Operations
    # -------------------------------------------------------------------------

    async def create_node(self, parent: str, node_type: str, name: str = None) -> Optional[str]:
        """Create a node and return its path."""
        payload = {
            "parent": parent,
            "type": node_type
        }
        if name:
            payload["name"] = name

        response = await self.send_command("create_node", payload)
        if response.get("success"):
            path = response.get("data", {}).get("path")
            print(f"  Created: {path}")
            return path
        else:
            print(f"  ERROR: {response.get('error')}")
            return None

    async def set_parm(self, node_path: str, parm_name: str, value: Any) -> bool:
        """Set a parameter value."""
        response = await self.send_command("set_parm", {
            "node": node_path,
            "parm": parm_name,
            "value": value
        })
        return response.get("success", False)

    async def set_parms(self, node_path: str, parms: Dict[str, Any]) -> bool:
        """Set multiple parameters at once."""
        for parm, value in parms.items():
            await self.set_parm(node_path, parm, value)
        return True

    async def connect_nodes(self, from_node: str, to_node: str,
                           from_output: int = 0, to_input: int = 0) -> bool:
        """Connect two nodes."""
        response = await self.send_command("connect_nodes", {
            "from_node": from_node,
            "to_node": to_node,
            "from_output": from_output,
            "to_input": to_input
        })
        if response.get("success"):
            print(f"  Connected: {from_node} -> {to_node}")
        return response.get("success", False)

    async def execute_python(self, code: str) -> Any:
        """Execute Python code in Houdini."""
        response = await self.send_command("execute_python", {"code": code})
        if response.get("success"):
            return response.get("data", {}).get("result")
        return None

    # -------------------------------------------------------------------------
    # Engram Memory Operations
    # -------------------------------------------------------------------------

    async def engram_add(self, content: str, memory_type: str = "context",
                         tags: list = None) -> bool:
        """Add a memory to Engram."""
        response = await self.send_command("engram_add", {
            "content": content,
            "memory_type": memory_type,
            "tags": tags or []
        })
        if response.get("success"):
            print(f"  Memory saved: {content[:50]}...")
        return response.get("success", False)

    async def engram_decide(self, decision: str, reasoning: str,
                           alternatives: list = None, tags: list = None) -> bool:
        """Record a decision to Engram."""
        response = await self.send_command("engram_decide", {
            "decision": decision,
            "reasoning": reasoning,
            "alternatives": alternatives or [],
            "tags": tags or []
        })
        if response.get("success"):
            print(f"  Decision recorded: {decision[:50]}...")
        return response.get("success", False)


# =============================================================================
# SCENE CREATION
# =============================================================================

async def create_turntable_scene(client: SynapseClient):
    """Create a character turntable scene."""

    print("\n" + "="*60)
    print("SYNAPSE DEMO: Character Turntable Scene")
    print("="*60)

    # -------------------------------------------------------------------------
    # 1. Record our intent in Engram
    # -------------------------------------------------------------------------
    print("\n[1/5] Recording context to Engram...")

    await client.engram_add(
        "Creating a character turntable scene with 3-point lighting for client review.",
        memory_type="context",
        tags=["turntable", "lighting", "demo"]
    )

    # -------------------------------------------------------------------------
    # 2. Create geometry network
    # -------------------------------------------------------------------------
    print("\n[2/5] Creating geometry...")

    # Create a geo node for our subject
    geo = await client.create_node("/obj", "geo", "character_geo")

    if geo:
        # Add a test geometry (pig head - classic Houdini test geo)
        testgeo = await client.create_node(geo, "testgeometry_pighead", "pig")

        # Add a transform to center it
        xform = await client.create_node(geo, "xform", "center")
        if xform:
            await client.set_parms(xform, {
                "ty": 0.5,  # Lift slightly
                "scale": 2.0  # Scale up
            })

        # Connect nodes
        if testgeo and xform:
            await client.connect_nodes(testgeo, xform)

    # Create ground plane
    ground = await client.create_node("/obj", "geo", "ground_plane")
    if ground:
        grid = await client.create_node(ground, "grid", "floor")
        if grid:
            await client.set_parms(grid, {
                "sizex": 20,
                "sizey": 20,
                "rows": 10,
                "cols": 10
            })

    # -------------------------------------------------------------------------
    # 3. Create lighting rig
    # -------------------------------------------------------------------------
    print("\n[3/5] Setting up 3-point lighting...")

    # Record the lighting decision
    await client.engram_decide(
        decision="Use 3-point lighting with warm key and cool fill",
        reasoning="Classic portrait setup creates dimension. Warm/cool contrast adds visual interest.",
        alternatives=["Single HDRI", "2-light flat setup", "Dramatic rim only"],
        tags=["lighting", "decision"]
    )

    # Key light (warm, camera left, elevated)
    key = await client.create_node("/obj", "hlight", "key_light")
    if key:
        await client.set_parms(key, {
            "tx": -5, "ty": 8, "tz": 5,
            "light_intensity": 1.5,
            "light_colorr": 1.0,
            "light_colorg": 0.95,
            "light_colorb": 0.85,  # Warm
        })
        print("    Key light: warm (5600K), intensity 1.5")

    # Fill light (cool, camera right, lower)
    fill = await client.create_node("/obj", "hlight", "fill_light")
    if fill:
        await client.set_parms(fill, {
            "tx": 4, "ty": 3, "tz": 4,
            "light_intensity": 0.6,
            "light_colorr": 0.85,
            "light_colorg": 0.92,
            "light_colorb": 1.0,  # Cool
        })
        print("    Fill light: cool (8000K), intensity 0.6")

    # Rim/back light
    rim = await client.create_node("/obj", "hlight", "rim_light")
    if rim:
        await client.set_parms(rim, {
            "tx": 0, "ty": 6, "tz": -6,
            "light_intensity": 1.2,
            "light_colorr": 1.0,
            "light_colorg": 1.0,
            "light_colorb": 1.0,
        })
        print("    Rim light: neutral, intensity 1.2")

    # -------------------------------------------------------------------------
    # 4. Create camera with turntable animation
    # -------------------------------------------------------------------------
    print("\n[4/5] Setting up turntable camera...")

    # Create null for turntable rotation
    turntable = await client.create_node("/obj", "null", "turntable_ctrl")
    if turntable:
        # Set rotation keyframes via Python execution
        await client.execute_python(f"""
import hou
node = hou.node("{turntable}")
ry = node.parm("ry")
ry.setKeyframe(hou.Keyframe(0, 1))
ry.setKeyframe(hou.Keyframe(360, 120))
""")
        print("    Turntable: 360 degrees over 120 frames")

    # Create camera
    cam = await client.create_node("/obj", "cam", "turntable_cam")
    if cam:
        await client.set_parms(cam, {
            "tx": 0, "ty": 2, "tz": 8,
            "rx": -10,
            "resx": 1920,
            "resy": 1080,
        })

        # Parent camera to turntable control
        if turntable:
            await client.execute_python(f"""
import hou
cam = hou.node("{cam}")
ctrl = hou.node("{turntable}")
cam.setInput(0, ctrl)
cam.parm("keeppos").set(1)
""")
        print("    Camera: 1920x1080, parented to turntable")

    # -------------------------------------------------------------------------
    # 5. Record render settings decision
    # -------------------------------------------------------------------------
    print("\n[5/5] Recording render settings...")

    await client.engram_decide(
        decision="Render at 1080p with 128 samples for preview",
        reasoning="1080p sufficient for turntable review. 128 samples balances quality vs iteration speed.",
        alternatives=["4K @ 512 samples", "720p @ 64 samples"],
        tags=["render", "decision"]
    )

    # Set frame range
    await client.execute_python("""
import hou
hou.playbar.setFrameRange(1, 120)
hou.playbar.setPlaybackRange(1, 120)
""")

    print("\n" + "="*60)
    print("SCENE COMPLETE!")
    print("="*60)
    print("""
Created:
  - character_geo (pig head test geometry)
  - ground_plane (20x20 grid)
  - key_light (warm, left)
  - fill_light (cool, right)
  - rim_light (back)
  - turntable_ctrl (360° animation)
  - turntable_cam (1080p, animated)

Frame range: 1-120 (turntable rotation)

Decisions recorded to Engram:
  - Lighting setup rationale
  - Render settings rationale
""")


# =============================================================================
# MAIN
# =============================================================================

async def main():
    print("""
┌───────────────────────────────────────────────────────────────────────┐
│                                                                       │▒
│   ███████╗██╗   ██╗███╗   ██╗ █████╗ ██████╗ ███████╗███████╗        │▒
│   ██╔════╝╚██╗ ██╔╝████╗  ██║██╔══██╗██╔══██╗██╔════╝██╔════╝        │▒
│   ███████╗ ╚████╔╝ ██╔██╗ ██║███████║██████╔╝███████╗█████╗          │▒
│   ╚════██║  ╚██╔╝  ██║╚██╗██║██╔══██║██╔═══╝ ╚════██║██╔══╝          │▒
│   ███████║   ██║   ██║ ╚████║██║  ██║██║     ███████║███████╗        │▒
│   ╚══════╝   ╚═╝   ╚═╝  ╚═══╝╚═╝  ╚═╝╚═╝     ╚══════╝╚══════╝        │▒
│                                                                       │▒
│   DEMO: AI-Driven Scene Creation                                      │▒
│                                                                       │▒
└───────────────────────────────────────────────────────────────────────┘▒
 ▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒
""")

    client = SynapseClient()

    try:
        await client.connect()
        await create_turntable_scene(client)
    except ConnectionRefusedError:
        print("""
ERROR: Could not connect to Synapse server.

Please ensure:
1. Houdini is running
2. Synapse panel is open (Windows > RadiantSuite > Synapse)
3. Server is started (click "Start Server")
4. Port is 9999 (default)
""")
    except Exception as e:
        print(f"ERROR: {e}")
    finally:
        await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
