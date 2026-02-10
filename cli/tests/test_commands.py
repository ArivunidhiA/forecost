"""Tests for LLMLab CLI commands."""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from click.testing import CliRunner

from llmlab.main import cli
from llmlab import config, security


@pytest.fixture
def runner():
    """Create a CLI test runner."""
    return CliRunner()


@pytest.fixture
def temp_config_dir(tmp_path, monkeypatch):
    """Create a temporary config directory."""
    config_dir = tmp_path / ".llmlab"
    config_dir.mkdir()
    
    monkeypatch.setattr(config, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(config, "CONFIG_FILE", config_dir / "config.json")
    
    # Also patch security key file location
    key_file = config_dir / ".key"
    
    def mock_get_or_create_key():
        if key_file.exists():
            return key_file.read_bytes()
        from cryptography.fernet import Fernet
        key = Fernet.generate_key()
        key_file.write_bytes(key)
        return key
    
    monkeypatch.setattr(security, "get_or_create_key", mock_get_or_create_key)
    
    return config_dir


class TestCLI:
    """Test CLI base functionality."""
    
    def test_cli_help(self, runner):
        """Test that CLI shows help."""
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "LLMLab" in result.output
        assert "login" in result.output
        assert "logout" in result.output
        assert "configure" in result.output
        assert "proxy-key" in result.output
        assert "stats" in result.output
    
    def test_cli_version(self, runner):
        """Test that CLI shows version."""
        result = runner.invoke(cli, ["--version"])
        assert result.exit_code == 0
        assert "0.1.0" in result.output


class TestLogout:
    """Test logout command."""
    
    def test_logout_not_logged_in(self, runner, temp_config_dir):
        """Test logout when not logged in."""
        result = runner.invoke(cli, ["logout"])
        assert result.exit_code == 0
        assert "Not logged in" in result.output
    
    def test_logout_success(self, runner, temp_config_dir):
        """Test successful logout."""
        # First, set up a logged-in state
        config.set_token("test-token")
        config.set_user({"username": "testuser"})
        
        result = runner.invoke(cli, ["logout", "-y"])
        assert result.exit_code == 0
        assert "Successfully logged out" in result.output
        assert config.get_token() is None


class TestConfigure:
    """Test configure command."""
    
    def test_configure_list_empty(self, runner, temp_config_dir):
        """Test listing keys when none configured."""
        result = runner.invoke(cli, ["configure", "--list"])
        assert result.exit_code == 0
        assert "No API keys configured" in result.output
    
    def test_configure_list_with_keys(self, runner, temp_config_dir):
        """Test listing configured keys."""
        config.set_api_key("openai", "sk-test12345678")
        
        result = runner.invoke(cli, ["configure", "--list"])
        assert result.exit_code == 0
        assert "OpenAI" in result.output
        assert "****5678" in result.output  # Masked key
        assert "sk-test" not in result.output  # Full key not shown
    
    def test_configure_openai_key(self, runner, temp_config_dir):
        """Test configuring OpenAI key."""
        result = runner.invoke(
            cli, 
            ["configure", "-p", "openai"],
            input="sk-test12345678901234567890\n"
        )
        assert result.exit_code == 0
        assert "Keys stored securely" in result.output
        
        # Verify key was stored
        stored_key = config.get_api_key("openai")
        assert stored_key == "sk-test12345678901234567890"
    
    def test_configure_skip_existing(self, runner, temp_config_dir):
        """Test skipping existing key with empty input."""
        config.set_api_key("openai", "sk-existing-key-12345")
        
        result = runner.invoke(
            cli,
            ["configure", "-p", "openai"],
            input="\n"  # Empty input keeps existing
        )
        assert result.exit_code == 0
        assert "Kept existing" in result.output
        
        # Verify key unchanged
        assert config.get_api_key("openai") == "sk-existing-key-12345"


class TestProxyKey:
    """Test proxy-key command."""
    
    def test_proxy_key_not_logged_in(self, runner, temp_config_dir):
        """Test proxy-key when not logged in."""
        result = runner.invoke(cli, ["proxy-key"])
        assert result.exit_code == 1
        assert "Not logged in" in result.output
    
    @patch("llmlab.commands.proxy_key.get_proxy_keys")
    def test_proxy_key_shell_format(self, mock_get, runner, temp_config_dir):
        """Test proxy-key with shell format."""
        config.set_token("test-token")
        mock_get.return_value = {"keys": [{"provider": "openai", "proxy_key": "llm_test_proxy_key_12345"}]}
        
        result = runner.invoke(cli, ["proxy-key"])
        assert result.exit_code == 0
        assert "export OPENAI_API_KEY=llm_test_proxy_key_12345" in result.output
    
    @patch("llmlab.commands.proxy_key.get_proxy_keys")
    def test_proxy_key_plain_format(self, mock_get, runner, temp_config_dir):
        """Test proxy-key with plain format."""
        config.set_token("test-token")
        mock_get.return_value = {"keys": [{"provider": "openai", "proxy_key": "llm_test_proxy_key_12345"}]}
        
        result = runner.invoke(cli, ["proxy-key", "--format=plain"])
        assert result.exit_code == 0
        assert result.output.strip() == "llm_test_proxy_key_12345"
    
    @patch("llmlab.commands.proxy_key.get_proxy_keys")
    def test_proxy_key_json_format(self, mock_get, runner, temp_config_dir):
        """Test proxy-key with JSON format."""
        config.set_token("test-token")
        mock_get.return_value = {"keys": [{"provider": "openai", "proxy_key": "llm_test_proxy_key_12345"}]}
        
        result = runner.invoke(cli, ["proxy-key", "--format=json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["key"] == "llm_test_proxy_key_12345"
        assert "base_url" in data


class TestStats:
    """Test stats command."""
    
    def test_stats_not_logged_in(self, runner, temp_config_dir):
        """Test stats when not logged in."""
        result = runner.invoke(cli, ["stats"])
        assert result.exit_code == 1
        assert "Not logged in" in result.output
    
    @patch("llmlab.commands.stats.get_stats")
    def test_stats_default(self, mock_get, runner, temp_config_dir):
        """Test stats with default period."""
        config.set_token("test-token")
        mock_get.return_value = {
            "by_model": [
                {"model": "gpt-4", "cost": 50.0, "calls": 100, "tokens": 500000},
                {"model": "claude-3-opus", "cost": 40.0, "calls": 80, "tokens": 400000},
            ],
            "daily": []
        }
        
        result = runner.invoke(cli, ["stats"])
        assert result.exit_code == 0
        assert "gpt-4" in result.output
        assert "claude-3-opus" in result.output
        assert "$50" in result.output
        assert "TOTAL" in result.output
    
    @patch("llmlab.commands.stats.get_stats")
    def test_stats_json(self, mock_get, runner, temp_config_dir):
        """Test stats with JSON output."""
        config.set_token("test-token")
        mock_get.return_value = {
            "by_model": [
                {"model": "gpt-4", "cost": 50.0, "calls": 100, "tokens": 500000},
            ],
            "daily": []
        }
        
        result = runner.invoke(cli, ["stats", "--json"])
        assert result.exit_code == 0
        # Output has progress bar prefix, find JSON part
        output_lines = result.output.strip().split("\n")
        json_start = next(i for i, line in enumerate(output_lines) if line.strip().startswith("{"))
        json_str = "\n".join(output_lines[json_start:])
        data = json.loads(json_str)
        assert "by_model" in data
        assert data["by_model"][0]["model"] == "gpt-4"


class TestSecurity:
    """Test security module."""
    
    def test_encrypt_decrypt(self, temp_config_dir):
        """Test encryption and decryption."""
        original = "sk-test-secret-key-12345"
        encrypted = security.encrypt_value(original)
        
        # Should not be the same as original
        assert encrypted != original
        
        # Should decrypt back to original
        decrypted = security.decrypt_value(encrypted)
        assert decrypted == original
    
    def test_mask_key(self):
        """Test key masking."""
        assert security.mask_key("sk-test12345678") == "****5678"
        assert security.mask_key("short") == "****"  # Too short, fully masked
        assert security.mask_key("12345678") == "****"  # Exactly 8 chars, fully masked
        assert security.mask_key("") == "****"
        assert security.mask_key(None) == "****"


class TestConfig:
    """Test config module."""
    
    def test_load_save_config(self, temp_config_dir):
        """Test loading and saving config."""
        test_config = {"test_key": "test_value"}
        config.save_config(test_config)
        
        loaded = config.load_config()
        assert loaded == test_config
    
    def test_token_storage(self, temp_config_dir):
        """Test token storage and retrieval."""
        config.set_token("test-jwt-token")
        assert config.get_token() == "test-jwt-token"
        assert config.is_authenticated() is True
        
        config.remove_token()
        assert config.get_token() is None
        assert config.is_authenticated() is False
    
    def test_api_key_storage(self, temp_config_dir):
        """Test API key storage and retrieval."""
        config.set_api_key("openai", "sk-test-key")
        
        assert config.get_api_key("openai") == "sk-test-key"
        assert config.get_api_key("anthropic") is None
        
        keys = config.get_api_keys()
        assert "openai" in keys
        assert keys["openai"] == "sk-test-key"
    
    def test_user_storage(self, temp_config_dir):
        """Test user info storage."""
        user = {"username": "testuser", "email": "test@example.com"}
        config.set_user(user)
        
        loaded = config.get_user()
        assert loaded == user


# =============================================================================
# EXPORT COMMAND
# =============================================================================


class TestExport:
    """Tests for the export command."""

    @patch("llmlab.commands.export.is_authenticated", return_value=True)
    @patch("llmlab.commands.export.export_logs_csv")
    def test_export_csv(self, mock_csv, mock_auth, runner, tmp_path):
        """Export CSV should call export_logs_csv and write file."""
        mock_csv.return_value = b"id,provider,model,cost_usd\n1,openai,gpt-4o,0.01\n"

        output_file = str(tmp_path / "test_export.csv")
        result = runner.invoke(cli, ["export", "-o", output_file])

        assert result.exit_code == 0
        mock_csv.assert_called_once()
        assert (tmp_path / "test_export.csv").exists()

    @patch("llmlab.commands.export.is_authenticated", return_value=True)
    @patch("llmlab.commands.export.export_logs_json")
    def test_export_json(self, mock_json, mock_auth, runner, tmp_path):
        """Export JSON should call export_logs_json and write file."""
        mock_json.return_value = b'{"logs": [], "total_logs": 0}'

        output_file = str(tmp_path / "test_export.json")
        result = runner.invoke(cli, ["export", "--json", "-o", output_file])

        assert result.exit_code == 0
        mock_json.assert_called_once()

    @patch("llmlab.commands.export.is_authenticated", return_value=True)
    @patch("llmlab.commands.export.export_logs_csv")
    def test_export_with_provider_filter(self, mock_csv, mock_auth, runner, tmp_path):
        """Export with --provider should pass filter to API."""
        mock_csv.return_value = b"id,provider,model,cost_usd\n1,openai,gpt-4o,0.01\n"

        output_file = str(tmp_path / "filtered.csv")
        result = runner.invoke(cli, ["export", "--provider", "openai", "-o", output_file])

        assert result.exit_code == 0
        mock_csv.assert_called_once_with(period="month", provider="openai", model=None)

    @patch("llmlab.commands.export.is_authenticated", return_value=False)
    def test_export_requires_auth(self, mock_auth, runner):
        """Export should require authentication."""
        result = runner.invoke(cli, ["export"])
        assert result.exit_code != 0
        assert "Not logged in" in result.output
