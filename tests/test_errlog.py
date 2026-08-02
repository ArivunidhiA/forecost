from forecost.core.errlog import redact


def test_redact_covers_modern_provider_and_github_tokens():
    secrets = [
        "sk-proj-abcdefghijklmnopqrstuvwxyz123456",
        "sk-ant-api03-abcdefghijklmnopqrstuvwxyz123456",
        "github_pat_abcdefghijklmnopqrstuvwxyz_1234567890",
        "gho_abcdefghijklmnopqrstuvwxyz1234567890",
        "hf_abcdefghijklmnopqrstuvwxyz123456",
        "AIzaabcdefghijklmnopqrstuvwxyz1234567890",
    ]
    for secret in secrets:
        assert secret not in redact(f"provider returned token={secret}")


def test_redact_covers_authorization_bearer_values():
    secret = "eyJhbGciOiJIUzI1NiJ9.payload.signature"  # noqa: S105 - synthetic canary
    result = redact(f"Authorization: Bearer {secret}")
    assert secret not in result
    assert "[REDACTED]" in result
