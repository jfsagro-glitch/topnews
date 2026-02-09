from core.services.ai_gate import AITickGate


def test_ai_gate_degrade_order():
    gate = AITickGate(max_calls=2)
    gate.begin_tick("t1")

    assert gate.can_call("summary")
    gate.record_call("summary")
    assert gate.can_call("cleanup")
    gate.record_call("cleanup")

    assert not gate.can_call("summary")
    assert "summary" in gate.get_state()["disabled"]

    assert not gate.can_call("cleanup")
    assert "cleanup" in gate.get_state()["disabled"]

    assert not gate.can_call("hashtags_ai")
    assert "hashtags_ai" in gate.get_state()["disabled"]
