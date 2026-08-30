from app.tools.redact import redact_mapping


def test_redact_openrouter_and_langsmith_keys():
    payload = redact_mapping(
        {
            "openrouter_api_key": "sk-or-v1-secretsecretsecret",
            "note": "Bearer abcdef and lsv2_pt_deadbeef_123",
        }
    )
    assert payload["openrouter_api_key"] == "[redacted]"
    assert "sk-or-v1" not in payload["note"]
    assert "lsv2_pt" not in payload["note"]
