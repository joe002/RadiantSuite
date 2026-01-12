"""
Aurora Programmatic Tests

Run without Houdini to verify core logic.
"""

import sys
import os

# Add package to path
package_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
python_dir = os.path.join(package_root, "python")
sys.path.insert(0, python_dir)

def test_determinism():
    """Test determinism layer"""
    print("\n=== Testing Determinism Layer ===")

    from core.determinism import (
        round_float, round_vector, deterministic_uuid,
        deterministic_sort, DeterministicRandom, DeterministicConfig, set_config
    )

    # Configure strict mode
    config = DeterministicConfig(strict_mode=True, float_precision=6)
    set_config(config)

    # Test float rounding
    assert round_float(0.123456789) == 0.123457, "Float rounding failed"
    assert round_float(0.5555555) == 0.555556, "Half-up rounding failed"
    print("  [PASS] Float rounding")

    # Test vector rounding (uses transform_precision=4 by default)
    vec = round_vector((0.123456789, 0.987654321, 0.555555555))
    assert vec == (0.1235, 0.9877, 0.5556), f"Vector rounding failed: {vec}"
    print("  [PASS] Vector rounding")

    # Test deterministic UUID - same input = same output
    uuid1 = deterministic_uuid("test_content", "test")
    uuid2 = deterministic_uuid("test_content", "test")
    assert uuid1 == uuid2, "UUID not deterministic"
    print(f"  [PASS] Deterministic UUID: {uuid1}")

    # Test deterministic sort
    items = ["zebra", "apple", "mango"]
    sorted_items = deterministic_sort(items)
    assert sorted_items == ["apple", "mango", "zebra"], "Sort not deterministic"
    print("  [PASS] Deterministic sort")

    # Test deterministic random
    rng1 = DeterministicRandom(seed=42)
    rng2 = DeterministicRandom(seed=42)
    vals1 = [rng1.random() for _ in range(5)]
    vals2 = [rng2.random() for _ in range(5)]
    assert vals1 == vals2, "Random not deterministic"
    print(f"  [PASS] Deterministic random: {vals1[:3]}...")

    print("  All determinism tests passed!")
    return True


def test_audit():
    """Test audit logging"""
    print("\n=== Testing Audit Logging ===")

    from core.audit import AuditLog, AuditLevel, AuditCategory

    # Reset singleton for clean test
    AuditLog.reset_instance()

    # Get fresh instance
    log = AuditLog.get_instance()

    # Log some entries
    entry1 = log.log(
        operation="test_op_1",
        message="First test entry",
        level=AuditLevel.INFO,
        category=AuditCategory.LIGHTING,
        tool="test",
    )
    print(f"  Entry 1 hash: {entry1.entry_hash[:16]}...")

    entry2 = log.log(
        operation="test_op_2",
        message="Second test entry",
        level=AuditLevel.AGENT_ACTION,
        category=AuditCategory.AOV,
        agent_id="test_agent",
    )
    print(f"  Entry 2 hash: {entry2.entry_hash[:16]}...")

    # Verify hash chain
    assert entry2.previous_hash == entry1.entry_hash, "Hash chain broken"
    print("  [PASS] Hash chain integrity")

    # Verify chain
    is_valid, invalid_idx = log.verify_chain()
    assert is_valid, f"Chain verification failed at index {invalid_idx}"
    print("  [PASS] Chain verification")

    # Query entries
    entries = log.get_entries(category=AuditCategory.LIGHTING)
    assert len(entries) >= 1, "Query failed"
    print(f"  [PASS] Query returned {len(entries)} entries")

    print("  All audit tests passed!")
    return True


def test_gates():
    """Test human gate system"""
    print("\n=== Testing Human Gates ===")

    from core.gates import HumanGate, GateLevel, GateDecision
    from core.audit import AuditCategory

    # Reset singleton
    HumanGate.reset_instance()

    gate = HumanGate.get_instance()

    # Create proposals
    proposal1 = gate.propose(
        operation="create_light_group",
        description="Create key_lights group",
        sequence_id="shot_010",
        category=AuditCategory.LIGHTING,
        level=GateLevel.REVIEW,
        proposed_changes={"name": "key_lights", "lights": []},
        reasoning="Following three-point lighting",
        confidence=0.85,
    )
    print(f"  Proposal 1: {proposal1.proposal_id[:16]}... [{proposal1.decision.value}]")

    proposal2 = gate.propose(
        operation="create_aov",
        description="Add custom AOV",
        sequence_id="shot_010",
        category=AuditCategory.AOV,
        level=GateLevel.INFORM,  # Auto-approved
    )
    print(f"  Proposal 2: {proposal2.proposal_id[:16]}... [{proposal2.decision.value}]")

    # INFORM level should auto-approve
    assert proposal2.decision == GateDecision.APPROVED, "INFORM not auto-approved"
    print("  [PASS] INFORM auto-approval")

    # Get pending
    pending = gate.get_pending("shot_010")
    assert len(pending) == 1, f"Expected 1 pending, got {len(pending)}"
    print(f"  [PASS] Pending count: {len(pending)}")

    # Approve proposal
    approved = gate.decide(
        proposal1.proposal_id,
        GateDecision.APPROVED,
        user_id="test_user",
        notes="Looks good"
    )
    assert approved.decision == GateDecision.APPROVED, "Approval failed"
    print("  [PASS] Manual approval")

    # Batch operations
    batch = gate.get_batch("shot_010")
    assert batch is not None, "Batch not found"
    summary = batch.summary()
    print(f"  [PASS] Batch summary: {summary}")

    print("  All gate tests passed!")
    return True


def test_aurora_models():
    """Test Aurora data models"""
    print("\n=== Testing Aurora Models ===")

    from aurora.models import (
        LightGroup, LightGroupMember, LightType, LightRole,
        AOVDefinition, AOVBundle, AOVType, LightLinkRule
    )

    # Create light group
    group = LightGroup(
        name="key_lights",
        role=LightRole.KEY,
        color_tag="#FFD700",
        description="Main key lighting",
    )

    # Add members
    group.add_light("/World/Lights/key_main", LightType.RECT)
    group.add_light("/World/Lights/key_fill", LightType.DISK)

    assert len(group.members) == 2, "Member count wrong"
    print(f"  [PASS] Light group created: {group.name} with {len(group.members)} lights")

    # Test LPE selector
    lpe_selector = group.get_lpe_light_selector()
    assert lpe_selector == "'lightgroup:key_lights'", f"LPE selector wrong: {lpe_selector}"
    print(f"  [PASS] LPE selector: {lpe_selector}")

    # Serialization round-trip
    group_dict = group.to_dict()
    group_restored = LightGroup.from_dict(group_dict)
    assert group_restored.name == group.name, "Serialization failed"
    assert len(group_restored.members) == len(group.members), "Members lost in serialization"
    print("  [PASS] Serialization round-trip")

    # AOV definition
    aov = AOVDefinition(
        name="key_lights_diffuse",
        lpe="C<RD>'lightgroup:key_lights'",
        light_group="key_lights",
    )
    assert aov.aov_id, "AOV ID not generated"
    print(f"  [PASS] AOV definition: {aov.name}")

    # Bundle
    bundle = AOVBundle(
        name="test_bundle",
        aovs=[aov],
        workflow="comp",
    )
    assert bundle.bundle_id, "Bundle ID not generated"
    print(f"  [PASS] AOV bundle: {bundle.name}")

    # Link rule
    rule = LightLinkRule(
        name="exclude_bg_from_key",
        light_pattern="/World/Lights/key_*",
        geometry_pattern="/World/Geo/background/*",
        include=False,
    )
    assert rule.rule_id, "Rule ID not generated"
    print(f"  [PASS] Link rule: {rule.name}")

    print("  All model tests passed!")
    return True


def test_lpe_generation():
    """Test LPE generation system"""
    print("\n=== Testing LPE Generation ===")

    from aurora.lpe import LPEGenerator, LPEPreset, STANDARD_AOVS, get_lpe_generator
    from aurora.models import LightGroup, LightRole, LightType

    gen = get_lpe_generator()

    # Test preset lookup
    diffuse_lpe = gen.get_preset("diffuse")
    assert diffuse_lpe == "C<RD>L", f"Wrong diffuse LPE: {diffuse_lpe}"
    print(f"  [PASS] Preset lookup: diffuse = {diffuse_lpe}")

    # Create test group
    group = LightGroup(name="key_lights", role=LightRole.KEY)
    group.add_light("/World/Lights/key_main", LightType.RECT)

    # Generate light group LPE
    group_lpe = gen.light_group_lpe("C<RD>L", group)
    expected = "C<RD>'lightgroup:key_lights'"
    assert group_lpe == expected, f"Wrong group LPE: {group_lpe}"
    print(f"  [PASS] Group LPE: {group_lpe}")

    # Generate group AOV
    aov = gen.generate_group_aov(group, "diffuse")
    assert aov.name == "key_lights_diffuse", f"Wrong AOV name: {aov.name}"
    assert "'lightgroup:key_lights'" in aov.lpe, f"Wrong AOV LPE: {aov.lpe}"
    print(f"  [PASS] Group AOV: {aov.name} = {aov.lpe}")

    # Generate all group AOVs
    all_aovs = gen.generate_group_aovs(group)
    assert len(all_aovs) > 0, "No AOVs generated"
    print(f"  [PASS] Generated {len(all_aovs)} AOVs for group")

    # Test bundles
    basic_bundle = gen.create_comp_basic_bundle([group])
    assert len(basic_bundle.aovs) > 5, f"Too few AOVs in basic bundle: {len(basic_bundle.aovs)}"
    print(f"  [PASS] Basic bundle: {len(basic_bundle.aovs)} AOVs")

    # Test auto-grouping suggestions
    light_paths = [
        "/World/Lights/key_main",
        "/World/Lights/fill_soft",
        "/World/Lights/rim_left",
        "/World/Lights/rim_right",
        "/World/Lights/practical_lamp",
        "/World/Lights/dome_env",
    ]
    suggestions = gen.suggest_groups_from_lights(light_paths)
    assert LightRole.KEY in suggestions, "KEY not suggested"
    assert LightRole.FILL in suggestions, "FILL not suggested"
    assert LightRole.RIM in suggestions, "RIM not suggested"
    print(f"  [PASS] Auto-grouping: {list(suggestions.keys())}")

    print("  All LPE tests passed!")
    return True


def test_light_linking():
    """Test light linking system"""
    print("\n=== Testing Light Linking ===")

    from aurora.linking import LightLinker, LinkMode, get_light_linker
    from aurora.models import LightGroup, LightRole, LightType

    linker = get_light_linker()
    linker.clear()  # Reset

    # Add rules
    rule1 = linker.create_rule(
        name="exclude_bg_from_key",
        light_pattern="/World/Lights/key_*",
        geometry_pattern="/World/Geo/background/*",
        include=False,
    )
    print(f"  [PASS] Created rule: {rule1.name}")

    rule2 = linker.create_rule(
        name="character_only_rim",
        light_pattern="/World/Lights/rim_*",
        geometry_pattern="/World/Geo/character/*",
        include=True,
        priority=10,
    )
    print(f"  [PASS] Created rule: {rule2.name}")

    # Test resolution
    lights = [
        "/World/Lights/key_main",
        "/World/Lights/rim_left",
    ]
    geometry = [
        "/World/Geo/character/body",
        "/World/Geo/background/wall",
    ]

    relationships = linker.resolve(lights, geometry)
    print(f"  [PASS] Resolved {len(relationships)} relationships")

    # Generate collections
    collections = linker.generate_collections(lights, geometry)
    assert len(collections) == 2, f"Wrong collection count: {len(collections)}"
    print(f"  [PASS] Generated {len(collections)} USD collections")

    # Test with light group
    group = LightGroup(name="rim_lights", role=LightRole.RIM)
    group.add_light("/World/Lights/rim_left", LightType.RECT)
    group.add_light("/World/Lights/rim_right", LightType.RECT)

    group_rules = linker.link_group_to_geometry(
        group,
        "/World/Geo/character/*",
    )
    assert len(group_rules) == 2, f"Wrong group rule count: {len(group_rules)}"
    print(f"  [PASS] Created {len(group_rules)} rules for light group")

    # Serialization
    linker_dict = linker.to_dict()
    assert "rules" in linker_dict, "Missing rules in serialization"
    print("  [PASS] Linker serialization")

    print("  All linking tests passed!")
    return True


def test_aurora_manager():
    """Test Aurora manager"""
    print("\n=== Testing Aurora Manager ===")

    from aurora.manager import AuroraManager
    from aurora.models import LightType, LightRole
    from core.gates import GateLevel, GateDecision, HumanGate

    # Reset singletons
    AuroraManager.reset_instance()
    HumanGate.reset_instance()

    mgr = AuroraManager.get_instance()

    # Set sequence
    mgr.set_sequence("shot_010")
    assert mgr.sequence_id == "shot_010", "Sequence not set"
    print(f"  [PASS] Sequence set: {mgr.sequence_id}")

    # Create light group with gate
    lights = [
        ("/World/Lights/key_main", LightType.RECT),
        ("/World/Lights/key_fill", LightType.DISK),
    ]

    group, proposal = mgr.create_light_group(
        name="key_lights",
        role=LightRole.KEY,
        lights=lights,
        gate_level=GateLevel.INFORM,  # Auto-approve for test
        agent_reasoning="Test creation",
        confidence=0.9,
    )

    assert group.name == "key_lights", "Group not created"
    assert len(group.members) == 2, "Members not added"
    print(f"  [PASS] Created group: {group.name} with proposal {proposal.proposal_id[:16]}...")

    # Get groups
    groups = mgr.get_light_groups()
    assert len(groups) >= 1, "No groups returned"
    print(f"  [PASS] Get groups: {len(groups)} groups")

    # Set bundle
    mgr.set_active_bundle("comp_full")
    assert mgr.session.active_bundle == "comp_full", "Bundle not set"
    print(f"  [PASS] Active bundle: {mgr.session.active_bundle}")

    # Get all AOVs
    aovs = mgr.get_all_aovs()
    assert len(aovs) > 10, f"Too few AOVs: {len(aovs)}"
    print(f"  [PASS] Total AOVs: {len(aovs)}")

    # Count light group AOVs
    group_aovs = [a for a in aovs if a.light_group == "key_lights"]
    print(f"  [PASS] Light group AOVs: {len(group_aovs)}")

    # Test linker access
    linker = mgr.linker
    assert linker is not None, "No linker"
    print("  [PASS] Linker access")

    # Session serialization
    session_dict = mgr.session.to_dict()
    assert "light_groups" in session_dict, "Missing light_groups"
    assert "key_lights" in session_dict["light_groups"], "Group missing from session"
    print("  [PASS] Session serialization")

    print("  All manager tests passed!")
    return True


def run_all_tests():
    """Run all tests"""
    print("=" * 60)
    print("AURORA PROGRAMMATIC TEST SUITE")
    print("=" * 60)

    tests = [
        ("Determinism", test_determinism),
        ("Audit Logging", test_audit),
        ("Human Gates", test_gates),
        ("Aurora Models", test_aurora_models),
        ("LPE Generation", test_lpe_generation),
        ("Light Linking", test_light_linking),
        ("Aurora Manager", test_aurora_manager),
    ]

    results = []
    for name, test_fn in tests:
        try:
            success = test_fn()
            results.append((name, success, None))
        except Exception as e:
            import traceback
            results.append((name, False, str(e)))
            traceback.print_exc()

    print("\n" + "=" * 60)
    print("TEST RESULTS")
    print("=" * 60)

    passed = 0
    failed = 0
    for name, success, error in results:
        status = "PASS" if success else "FAIL"
        print(f"  [{status}] {name}")
        if error:
            print(f"         Error: {error}")
        if success:
            passed += 1
        else:
            failed += 1

    print(f"\nTotal: {passed} passed, {failed} failed")
    print("=" * 60)

    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
