from desk.config import Settings


def test_rpc_url_accepts_both_env_names(monkeypatch):
    monkeypatch.setenv("RPC_URL", "http://a")
    assert Settings(_env_file=None).rpc_url == "http://a"
    monkeypatch.setenv("ARBITRUM_SEPOLIA_RPC_URL", "http://b")
    assert Settings(_env_file=None).rpc_url == "http://b"


def test_rpc_url_by_name_and_default(monkeypatch):
    monkeypatch.delenv("RPC_URL", raising=False)
    monkeypatch.delenv("ARBITRUM_SEPOLIA_RPC_URL", raising=False)
    assert Settings(_env_file=None).rpc_url == "http://127.0.0.1:8545"
    assert Settings(rpc_url="http://c", _env_file=None).rpc_url == "http://c"


def test_env_file_loading(tmp_path, monkeypatch):
    monkeypatch.delenv("RPC_URL", raising=False)
    monkeypatch.delenv("ARBITRUM_SEPOLIA_RPC_URL", raising=False)
    monkeypatch.delenv("AGENT_PRIVATE_KEY", raising=False)
    env = tmp_path / ".env"
    env.write_text("ARBITRUM_SEPOLIA_RPC_URL=http://from-env-file\nAGENT_PRIVATE_KEY=0xabc\nUNRELATED=1\n")
    settings = Settings(_env_file=env)
    assert settings.rpc_url == "http://from-env-file"
    assert settings.agent_private_key.get_secret_value() == "0xabc"
