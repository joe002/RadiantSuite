"""
Spectrum Module Tests

Programmatic verification of Spectrum (LookDev Tool) functionality.
Run independently of Houdini to verify core logic.
"""

import sys
import os
import tempfile
from pathlib import Path

# Add python directory to path
python_dir = Path(__file__).parent.parent / "python"
sys.path.insert(0, str(python_dir))


def test_determinism_config():
    """Test determinism configuration"""
    from core.determinism import (
        DeterministicConfig, set_config, get_config,
        round_float, round_vector, deterministic_uuid
    )

    # Configure with explicit precision
    config = DeterministicConfig(
        float_precision=4,
        transform_precision=4,
        strict_mode=True
    )
    set_config(config)

    # Test float rounding (uses float_precision=4)
    rounded = round_float(0.123456789)
    assert rounded == 0.1235, f"Float rounding failed: {rounded}"

    # Test vector rounding (uses transform_precision=4)
    vec = round_vector((0.123456789, 0.987654321, 0.555555555))
    assert vec == (0.1235, 0.9877, 0.5556), f"Vector rounding failed: {vec}"

    # Test UUID generation
    uuid1 = deterministic_uuid("test_content", "spectrum")
    uuid2 = deterministic_uuid("test_content", "spectrum")
    assert uuid1 == uuid2, "UUID not deterministic"

    print("  [PASS] Determinism configuration")


def test_material_models():
    """Test material data models"""
    from core.determinism import DeterministicConfig, set_config
    from spectrum.models import (
        Material, MaterialType, ShaderParameter, TextureFile,
        TextureSet, TextureChannel, Colorspace
    )

    # Ensure determinism config is set for this test
    config = DeterministicConfig(
        float_precision=4,
        transform_precision=4,
        strict_mode=True
    )
    set_config(config)

    # Test ShaderParameter
    param = ShaderParameter(
        name="roughness",
        value=0.555555,
        param_type="float",
        min_value=0.0,
        max_value=1.0,
        ui_label="Roughness"
    )
    assert param.value == 0.5556, f"Parameter value not rounded: {param.value}"

    # Test color parameter
    color_param = ShaderParameter(
        name="baseColor",
        value=(0.8, 0.123456, 0.555555),
        param_type="color3f"
    )
    assert color_param.value == (0.8, 0.1235, 0.5556), f"Color not rounded: {color_param.value}"

    # Test Material creation
    material = Material(
        name="test_metal",
        material_type=MaterialType.KARMA_PRINCIPLED,
        parameters=[param, color_param],
    )
    assert material.material_id, "Material ID not generated"
    assert material.name == "test_metal"

    # Test serialization
    data = material.to_dict()
    assert data["name"] == "test_metal"
    assert data["material_type"] == "KarmaPrincipled"

    # Test deserialization
    restored = Material.from_dict(data)
    assert restored.name == material.name
    assert restored.material_id == material.material_id

    # Test TextureFile
    texture = TextureFile(
        path="/textures/metal_roughness.exr",
        channel=TextureChannel.ROUGHNESS
    )
    assert texture.colorspace == Colorspace.LINEAR, "Roughness should be linear"

    albedo = TextureFile(
        path="/textures/metal_albedo.exr",
        channel=TextureChannel.ALBEDO
    )
    assert albedo.colorspace == Colorspace.SRGB, "Albedo should be sRGB"

    # Test TextureSet
    texture_set = TextureSet(
        name="metal_textures",
        textures=[texture, albedo],
        resolution_variant="2k"
    )
    assert texture_set.get_texture(TextureChannel.ROUGHNESS) == texture
    assert texture_set.get_texture(TextureChannel.ALBEDO) == albedo
    assert texture_set.get_texture(TextureChannel.NORMAL) is None

    print("  [PASS] Material models")


def test_texture_channel_detection():
    """Test automatic texture channel detection"""
    from spectrum.textures import detect_texture_channel
    from spectrum.models import TextureChannel

    # Test various naming conventions
    test_cases = [
        ("metal_albedo.exr", TextureChannel.ALBEDO),
        ("metal_BaseColor_2k.png", TextureChannel.ALBEDO),
        ("diffuse.tiff", TextureChannel.ALBEDO),
        ("wood_roughness.exr", TextureChannel.ROUGHNESS),
        ("steel_rgh.png", TextureChannel.ROUGHNESS),
        ("brick_metallic.exr", TextureChannel.METALLIC),
        ("floor_normal.exr", TextureChannel.NORMAL),
        ("wall_nrm_2k.png", TextureChannel.NORMAL),
        ("skin_ao.exr", TextureChannel.AMBIENT_OCCLUSION),
        ("cloth_opacity.png", TextureChannel.OPACITY),
        ("neon_emissive.exr", TextureChannel.EMISSIVE),
        ("glass_transmission.exr", TextureChannel.TRANSMISSION),
    ]

    for filename, expected_channel in test_cases:
        detected = detect_texture_channel(filename)
        assert detected == expected_channel, f"Channel detection failed for '{filename}': expected {expected_channel}, got {detected}"

    print("  [PASS] Texture channel detection")


def test_texture_udim_detection():
    """Test UDIM pattern detection"""
    from spectrum.textures import detect_udim

    # Test UDIM patterns
    is_udim, pattern = detect_udim("metal_albedo.1001.exr")
    assert is_udim, "Should detect UDIM"
    assert "<UDIM>" in pattern, f"Pattern should contain <UDIM>: {pattern}"

    is_udim, pattern = detect_udim("metal_albedo.exr")
    assert not is_udim, "Should not detect UDIM in non-UDIM filename"

    is_udim, pattern = detect_udim("texture_<UDIM>.exr")
    assert is_udim, "Should detect explicit <UDIM> token"

    print("  [PASS] UDIM detection")


def test_environment_presets():
    """Test environment preset system"""
    from spectrum.environments import (
        get_environment_manager, STUDIO_PRESETS
    )
    from spectrum.models import EnvironmentType

    mgr = get_environment_manager()

    # Verify built-in presets loaded
    assert len(mgr.get_all_presets()) >= len(STUDIO_PRESETS), "Built-in presets not loaded"

    # Test neutral grey preset
    neutral = mgr.get_preset("neutral_grey")
    assert neutral is not None, "Neutral grey preset not found"
    assert neutral.env_type == EnvironmentType.SOLID_COLOR
    assert neutral.background_color == (0.18, 0.18, 0.18)

    # Test golden hour preset
    golden = mgr.get_preset("golden_hour")
    assert golden is not None, "Golden hour preset not found"
    assert golden.env_type == EnvironmentType.PROCEDURAL_SKY
    assert golden.sun_intensity == 0.8

    # Test preset by type
    studio_presets = mgr.get_presets_by_type(EnvironmentType.SOLID_COLOR)
    assert len(studio_presets) >= 3, "Should have multiple solid color presets"

    # Test preset by tag
    outdoor_presets = mgr.get_presets_by_tag("outdoor")
    assert len(outdoor_presets) >= 2, "Should have outdoor presets"

    # Test active preset
    assert mgr.set_active("neutral_grey")
    active = mgr.get_active()
    assert active.name == "Neutral Grey"

    print("  [PASS] Environment presets")


def test_material_library():
    """Test material library management"""
    from spectrum.materials import MaterialLibrary, get_default_parameters
    from spectrum.models import MaterialType, MaterialAssignmentRule, MaterialPreset

    # Reset singleton state
    import spectrum.materials as mat_module
    mat_module._library = None

    library = MaterialLibrary()

    # Test default parameters
    karma_defaults = get_default_parameters(MaterialType.KARMA_PRINCIPLED)
    assert len(karma_defaults) > 10, "Should have many default parameters"
    assert any(p.name == "roughness" for p in karma_defaults)
    assert any(p.name == "metallic" for p in karma_defaults)

    # Test material creation
    material, proposal = library.create_material(
        name="chrome",
        material_type=MaterialType.KARMA_PRINCIPLED
    )
    assert material is not None
    assert material.name == "chrome"
    assert proposal is not None

    # Test parameter update
    library.update_material("chrome", {"roughness": 0.1, "metallic": 1.0})
    chrome = library.get_material("chrome")
    assert chrome.get_parameter("roughness").value == 0.1

    # Test material duplication
    chrome_copy = library.duplicate_material("chrome", "chrome_polished")
    assert chrome_copy is not None
    assert chrome_copy.name == "chrome_polished"
    assert chrome_copy.material_id != chrome.material_id

    # Test search
    results = library.search_materials(query="chrome")
    assert len(results) == 2

    # Test assignment rules
    rule = MaterialAssignmentRule(
        name="metal_rule",
        material_name="chrome",
        geometry_pattern="/scene/*/metal*",
        priority=10
    )
    library.add_assignment_rule(rule)

    # Test geometry resolution
    resolved = library.resolve_material_for_geometry("/scene/car/metal_body")
    assert resolved == "chrome"

    resolved = library.resolve_material_for_geometry("/scene/car/rubber_tire")
    assert resolved is None

    # Test presets
    preset = library.create_preset_from_material("chrome", "chrome_preset", category="metal")
    assert preset is not None
    assert preset.category == "metal"

    print("  [PASS] Material library")


def test_spectrum_manager():
    """Test main Spectrum manager"""
    from spectrum.manager import SpectrumManager, spectrum
    from spectrum.models import MaterialType, PreviewQuality

    # Reset singleton
    SpectrumManager.reset_instance()

    # Reset other singletons too
    import spectrum.materials as mat_module
    import spectrum.textures as tex_module
    import spectrum.environments as env_module
    mat_module._library = None
    tex_module._manager = None
    env_module._manager = None

    mgr = spectrum()

    # Test material creation
    material, proposal = mgr.create_material(
        "test_plastic",
        MaterialType.KARMA_PRINCIPLED
    )
    assert material is not None
    assert mgr.session.active_material == "test_plastic"

    # Test environment switching
    assert mgr.set_active_environment("pure_black")
    assert mgr.session.active_environment == "pure_black"

    env = mgr.get_active_environment()
    assert env.name == "Pure Black"

    # Test preview config
    config = mgr.get_preview_config("default")
    assert config is not None
    assert config.quality == PreviewQuality.MEDIUM

    # Test turntable config
    turntable = mgr.get_preview_config("turntable")
    assert turntable is not None
    assert turntable.enable_turntable == True
    assert turntable.turntable_frames == 90

    # Test preview settings
    settings = mgr.get_preview_settings()
    assert "config" in settings
    assert "environment" in settings
    assert "material" in settings

    # Test A/B comparison
    material2, _ = mgr.create_material("test_metal", MaterialType.KARMA_PRINCIPLED)
    assert mgr.enable_comparison("test_plastic", "test_metal")
    assert mgr.session.comparison_enabled
    assert mgr.session.comparison_material_a == "test_plastic"
    assert mgr.session.comparison_material_b == "test_metal"

    mgr.swap_comparison()
    assert mgr.session.comparison_material_a == "test_metal"
    assert mgr.session.comparison_material_b == "test_plastic"

    mgr.disable_comparison()
    assert not mgr.session.comparison_enabled

    print("  [PASS] Spectrum manager")


def test_synapse_commands():
    """Test Synapse command handlers"""
    from spectrum.synapse_commands import (
        SpectrumCommandHandler, SpectrumCommandType
    )
    from spectrum.manager import SpectrumManager

    # Reset singletons
    SpectrumManager.reset_instance()
    import spectrum.materials as mat_module
    import spectrum.textures as tex_module
    import spectrum.environments as env_module
    import spectrum.synapse_commands as syn_module
    mat_module._library = None
    tex_module._manager = None
    env_module._manager = None
    syn_module._handler = None

    handler = SpectrumCommandHandler()

    # Test create material
    result = handler._handle_create_material({
        "name": "gold",
        "material_type": "KarmaPrincipled",
        "reasoning": "Agent suggested gold material",
        "confidence": 0.9
    })
    assert result["material"]["name"] == "gold"
    assert "proposal_id" in result

    # Test get materials
    result = handler._handle_get_materials({})
    assert result["count"] >= 1
    assert result["active"] == "gold"

    # Test update material
    result = handler._handle_update_material({
        "name": "gold",
        "parameters": {"roughness": 0.2, "metallic": 1.0}
    })
    assert "roughness" in result["parameters"]
    assert "metallic" in result["parameters"]

    # Test environment commands
    result = handler._handle_get_environments({})
    assert result["count"] >= 8  # Built-in presets

    result = handler._handle_set_environment({"name": "golden_hour"})
    assert result["success"]
    assert result["active"] == "golden_hour"

    # Test preview settings
    result = handler._handle_get_preview_settings({})
    assert "config" in result
    assert "environment" in result

    # Test session
    result = handler._handle_get_session({})
    assert "session" in result
    assert result["session"]["active_environment"] == "golden_hour"

    # Verify all command types are defined
    assert len(SpectrumCommandType) >= 23, f"Expected at least 23 command types, got {len(SpectrumCommandType)}"

    print("  [PASS] Synapse commands")


def test_session_persistence():
    """Test session save/load"""
    from spectrum.manager import SpectrumManager, spectrum
    from spectrum.models import MaterialType

    # Reset singletons
    SpectrumManager.reset_instance()
    import spectrum.materials as mat_module
    import spectrum.textures as tex_module
    import spectrum.environments as env_module
    mat_module._library = None
    tex_module._manager = None
    env_module._manager = None

    mgr = spectrum()

    # Create test data
    mgr.create_material("persist_test", MaterialType.KARMA_PRINCIPLED)
    mgr.set_active_environment("outdoor_daylight")

    # Save session
    with tempfile.TemporaryDirectory() as tmpdir:
        session_path = Path(tmpdir) / "test_session.json"
        mgr.save_session(session_path)

        assert session_path.exists(), "Session file not created"

        # Reset and load
        SpectrumManager.reset_instance()
        mat_module._library = None
        tex_module._manager = None
        env_module._manager = None

        mgr2 = spectrum()
        assert mgr2.load_session(session_path)
        assert mgr2.session.active_material == "persist_test"
        assert mgr2.session.active_environment == "outdoor_daylight"

    print("  [PASS] Session persistence")


def test_hdri_management():
    """Test HDRI library management"""
    from spectrum.environments import EnvironmentManager
    from spectrum.models import EnvironmentType

    # Fresh manager
    mgr = EnvironmentManager()

    # Add test HDRI
    mgr.add_hdri("studio_soft", "/path/to/studio_soft.hdr")

    # Verify HDRI added to library
    hdris = mgr.get_all_hdris()
    assert any(name == "studio_soft" for name, _ in hdris)

    # Verify preset created for HDRI
    preset = mgr.get_preset("hdri_studio_soft")
    assert preset is not None
    assert preset.env_type == EnvironmentType.HDRI
    assert preset.hdri_path == "/path/to/studio_soft.hdr"

    # Test HDRI rotation adjustment
    assert mgr.adjust_hdri_rotation("hdri_studio_soft", 45.0)
    preset = mgr.get_preset("hdri_studio_soft")
    assert preset.rotation == 45.0

    # Test intensity adjustment
    assert mgr.adjust_hdri_intensity("hdri_studio_soft", 1.5)
    preset = mgr.get_preset("hdri_studio_soft")
    assert preset.intensity == 1.5

    print("  [PASS] HDRI management")


def run_all_tests():
    """Run all Spectrum tests"""
    print("\nSpectrum Module Tests")
    print("=" * 40)

    tests = [
        ("Determinism Config", test_determinism_config),
        ("Material Models", test_material_models),
        ("Texture Channel Detection", test_texture_channel_detection),
        ("UDIM Detection", test_texture_udim_detection),
        ("Environment Presets", test_environment_presets),
        ("Material Library", test_material_library),
        ("Spectrum Manager", test_spectrum_manager),
        ("Synapse Commands", test_synapse_commands),
        ("Session Persistence", test_session_persistence),
        ("HDRI Management", test_hdri_management),
    ]

    passed = 0
    failed = 0

    for name, test_func in tests:
        try:
            test_func()
            passed += 1
        except AssertionError as e:
            print(f"  [FAIL] {name}: {e}")
            failed += 1
        except Exception as e:
            print(f"  [ERROR] {name}: {type(e).__name__}: {e}")
            failed += 1

    print("=" * 40)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 40)

    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
