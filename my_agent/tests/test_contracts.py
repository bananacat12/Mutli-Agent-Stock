from my_agent.orchestration.contracts import AgentRequest, normalize_tool_result


def test_agent_request_has_request_id():
    request = AgentRequest(
        trace_id="trace",
        task_id="task",
        conversation_id="conv",
        agent_name="price_agent",
        payload={"symbol": "TSLA"},
    )

    assert request.request_id
    assert request.agent_name == "price_agent"


def test_normalize_legacy_error_result():
    result = normalize_tool_result({"status": "error", "error_message": "failed"})

    assert result.status == "error"
    assert result.error == "failed"


def test_normalize_success_degraded_to_partial():
    result = normalize_tool_result({"status": "success_degraded", "mean_score": 0.1})

    assert result.status == "partial"
    assert result.data["mean_score"] == 0.1
