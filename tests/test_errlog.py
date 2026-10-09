import re

from forecost.core.errlog import log_error, redact


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


def test_durable_log_contains_only_finite_code_and_keyed_fingerprint(tmp_path, monkeypatch):
    home = tmp_path / "forecost-home"
    monkeypatch.setenv("FORECOST_HOME", str(home))
    raw = "/private/workspace/CANARY-source-file.py bearer-secret"

    log_error("hooks.policy", "HOOK_POLICY_IGNORED", fingerprint_source=raw)
    log_error("hooks.policy", "HOOK_POLICY_IGNORED", fingerprint_source=raw)

    lines = (home / "error.log").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert lines[0] == lines[1]
    assert raw not in lines[0]
    assert re.fullmatch(
        r"\[hooks\.policy\] code=HOOK_POLICY_IGNORED "
        r"fingerprint=hmac-sha256:[0-9a-f]{64}",
        lines[0],
    )


def test_legacy_free_text_and_unknown_component_are_never_persisted(tmp_path, monkeypatch):
    home = tmp_path / "forecost-home"
    monkeypatch.setenv("FORECOST_HOME", str(home))
    canary = "CANARY arbitrary exception /raw/workspace/path"

    log_error("plugin." + canary, canary)

    durable = (home / "error.log").read_text(encoding="utf-8")
    assert canary not in durable
    assert re.fullmatch(
        r"\[core\.unknown\] code=INTERNAL_ERROR "
        r"fingerprint=hmac-sha256:[0-9a-f]{64}\n",
        durable,
    )


def test_error_logger_never_follows_an_existing_log_symlink(tmp_path, monkeypatch):
    home = tmp_path / "forecost-home"
    home.mkdir()
    target = tmp_path / "unrelated.txt"
    target.write_text("must survive", encoding="utf-8")
    (home / "error.log").symlink_to(target)
    monkeypatch.setenv("FORECOST_HOME", str(home))

    log_error("test", "INTERNAL_ERROR", fingerprint_source="private")

    assert target.read_text(encoding="utf-8") == "must survive"


def test_first_post_upgrade_write_discards_legacy_free_text(tmp_path, monkeypatch):
    home = tmp_path / "forecost-home"
    home.mkdir()
    legacy_canary = "legacy exception /raw/workspace/private.py"
    (home / "error.log").write_text(f"[old] {legacy_canary}\n", encoding="utf-8")
    monkeypatch.setenv("FORECOST_HOME", str(home))

    log_error("test", "INTERNAL_ERROR", fingerprint_source="replacement")

    durable = (home / "error.log").read_text(encoding="utf-8")
    assert legacy_canary not in durable
    assert "code=INTERNAL_ERROR" in durable
