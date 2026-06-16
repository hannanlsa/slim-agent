"""问题驱动学习 (Q4) 自测 + 版本管理 (Q3) 端到端验证"""
import os
import shutil
import sys
import json
import tempfile

# 隔离 POOL_DIR 避免污染真实数据
TEST_POOL = tempfile.mkdtemp(prefix="slim_test_")
os.environ["SLIM_AGENT_POOL_DIR"] = TEST_POOL

from slim_agent.versioned_reflection import core as rp, init_pool
from slim_agent.problem_solving import (
    learn_problem, learn_manual, learn_from_error, record_evolution,
    list_learnings, get_learning, rollback_learning, diff_learning,
    search_learnings,
    SOURCE_AGENT, SOURCE_ERROR, SOURCE_MANUAL, SOURCE_EVOLUTION,
)


def test_q3_versioned_reflection():
    """Q3 端到端测试"""
    print("\n=== Q3 versioned_reflection ===")
    init_pool()

    # T1: create
    e = rp.create_entry(title="Test Entry", content="Alpha\nBeta\nGamma", source="test", reason="init")
    assert e.version == 1 and e.content == "Alpha\nBeta\nGamma"
    print("✅ T1: create v1")

    # T2: update
    e2 = rp.update_entry("test-entry", content="Alpha\nMODIFIED\nGamma", reason="change")
    assert e2.version == 2
    print("✅ T2: update v2")

    # T3: update
    e3 = rp.update_entry("test-entry", content="Alpha\nMODIFIED\nGamma\nDelta", reason="add")
    assert e3.version == 3
    print("✅ T3: update v3")

    # T4: rollback v1 → v4
    rb1 = rp.rollback("test-entry", to_version=1)
    assert rb1.version == 4 and rb1.content == "Alpha\nBeta\nGamma"
    print("✅ T4: rollback v1→v4")

    # T5: update → v5
    e5 = rp.update_entry("test-entry", content="Alpha\nMODIFIED\nGamma\nDelta\nEpsilon", reason="more")
    assert e5.version == 5
    print("✅ T5: update v5")

    # T6: rollback v2 → v6
    rb2 = rp.rollback("test-entry", to_version=2)
    assert rb2.version == 6 and rb2.content == "Alpha\nMODIFIED\nGamma"
    print("✅ T6: rollback v2→v6")

    # T7: 6 patches, version chain intact
    patches = rp._history_patches("test-entry")
    assert len(patches) == 6
    print(f"✅ T7: {len(patches)} patches")

    # T8: diff
    diff = rp.diff_entry("test-entry", 1)
    assert len(diff) > 0
    print("✅ T8: diff")

    # T9: index valid
    idx = json.load(open(rp.INDEX_PATH))
    assert idx["test-entry"]["version"] == 6
    print("✅ T9: index")

    # T10: disk matches
    fm, body = rp._parse_frontmatter(open(rp._entry_path("test-entry")).read())
    assert body == "Alpha\nMODIFIED\nGamma" and fm["version"] == 6
    print("✅ T10: disk matches")

    # T11: bump_trigger
    rp.bump_trigger("test-entry")
    g = rp.get_entry("test-entry")
    assert g.trigger_count == 1
    print("✅ T11: bump_trigger")

    # T12: rebuild index
    os.remove(rp.INDEX_PATH)
    idx2 = rp._read_index()
    assert "test-entry" in idx2 and idx2["test-entry"]["version"] == 6
    print("✅ T12: rebuild index")

    # T13: rollback no-op
    rb_same = rp.rollback("test-entry", to_version=6)
    assert rb_same.version == 6
    print("✅ T13: rollback no-op")

    # T14: invalid rollback
    assert rp.rollback("test-entry", to_version=99) is None
    print("✅ T14: invalid rollback")

    # T15: list
    entries = rp.list_entries(source="test")
    assert len(entries) >= 1
    print(f"✅ T15: list ({len(entries)} entries)")

    # T16: patches no粘连
    for p in patches:
        pc = open(p).read()
        # Verify unified diff header is correct
        assert "@@" in pc
    print("✅ T16: patch format valid")


def test_q4_problem_solving():
    """Q4 端到端测试"""
    print("\n=== Q4 problem_solving ===")

    # T1: learn_problem
    r = learn_problem(
        "为什么 reflection_pool rollback 后 update 会产生重复版本号",
        reason="Q3 bug fix 过程中的真实发现"
    )
    assert r["slug"] and r["version"] == 1
    print(f"✅ T1: learn_problem → {r['slug']} v{r['version']}")

    # T2: learn_manual
    r2 = learn_manual(
        "OpenClaw token 集中管理规范",
        reason="主人 8/14 指令"
    )
    assert r2["slug"]
    e = rp.get_entry(r2["slug"])
    assert e.source == SOURCE_MANUAL
    print(f"✅ T2: learn_manual → {r2['slug']}")

    # T3: learn_from_error
    r3 = learn_from_error(
        "TypeError",
        "Object of type datetime is not JSON serializable",
        context="pool_index.json 写入时",
        lesson="YAML 1.1 自动把 ISO 时间戳解析为 datetime 对象，json.dump() 需 .isoformat() 转换",
        related_skill="reflection_pool"
    )
    assert r3["slug"] and r3["related_skill"] == "reflection_pool"
    print(f"✅ T3: learn_from_error → {r3['slug']}")

    # T4: list filter (仅 Q4 创建的 3 个，不含 Q3 的 test entry)
    all_l = list_learnings()
    # Filter 到 problem_solving 创建的 4 个 source 类型
    q4_entries = [e for e in all_l if e.get("source") in (SOURCE_AGENT, SOURCE_ERROR, SOURCE_MANUAL, SOURCE_EVOLUTION)]
    agent_l = list_learnings(source=SOURCE_AGENT)
    manual_l = list_learnings(source=SOURCE_MANUAL)
    error_l = list_learnings(source=SOURCE_ERROR)
    assert len(q4_entries) == 3
    assert len(agent_l) == 1
    assert len(manual_l) == 1
    assert len(error_l) == 1
    print(f"✅ T4: list filter q4={len(q4_entries)} agent={len(agent_l)} manual={len(manual_l)} error={len(error_l)}")

    # T5: record_evolution
    tracker = os.path.expanduser("~/.qclaw/workspace/evolution-tracker.jsonl")
    if os.path.exists(tracker):
        before_count = sum(1 for _ in open(tracker))
    else:
        before_count = 0

    r5 = record_evolution(
        "versioned_reflection 增量 diff",
        before="覆盖式写入（无 patch）",
        after="增量 diff + rollback + rebuild_index",
        evidence="Q3 修复：5 bug, 16/16 tests pass"
    )
    assert r5["slug"]

    after_count = sum(1 for _ in open(tracker))
    assert after_count == before_count + 1
    print(f"✅ T5: record_evolution → {r5['slug']} (tracker +1)")

    # T6: search_learnings
    results = search_learnings("JSON")
    assert len(results) >= 1
    print(f"✅ T6: search_learnings found {len(results)} entries")

    # T7: get_learning
    g = get_learning(r["slug"])
    assert g is not None and g["title"]
    print(f"✅ T7: get_learning → {g['title'][:50]}")

    # T8: rollback_learning
    original_content = get_learning(r["slug"])["content"]
    rp.update_entry(r["slug"], content=original_content + "\n\n## Updated\nadd more", reason="extend")
    rb = rollback_learning(r["slug"], to_version=1)
    assert rb is not None and rb["version"] >= 2
    print(f"✅ T8: rollback_learning → v{rb['version']}")

    # T9: diff_learning (需要 2 个版本才能 diff)
    from slim_agent.versioned_reflection import core as rp_vr
    original_content = get_learning(r["slug"])["content"]
    rp.update_entry(r["slug"], content=original_content + "\n\n## Updated\nfor diff", reason="diff setup")
    d = diff_learning(r["slug"], against_version=1)
    assert d is not None and len(d) > 0
    print(f"✅ T9: diff_learning ({len(d)} bytes)")


def cleanup():
    if os.path.exists(TEST_POOL):
        shutil.rmtree(TEST_POOL, ignore_errors=True)


if __name__ == "__main__":
    try:
        test_q3_versioned_reflection()
        print()
        test_q4_problem_solving()
        print("\n✅ ALL TESTS PASSED")
        sys.exit(0)
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"\n❌ FAILED: {e}")
        sys.exit(1)
    finally:
        cleanup()
