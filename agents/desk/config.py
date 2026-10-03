from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    anthropic_api_key: SecretStr | None = None
    openai_api_key: SecretStr | None = None
    llm_provider: Literal["anthropic", "openai"] = "anthropic"
    model_small: str = "claude-3-5-haiku-latest"
    model_large: str = "claude-sonnet-4-5"

    gmx_apy_url: str = "https://arbitrum-api.gmxinfra.io/apy"
    pendle_api_url: str = "https://api-v2.pendle.finance/core"
    pendle_chain_id: int = 42161
    pendle_market_address: str | None = None
    gmx_market_name: str = "GM: ETH/USD [WETH-USDC]"

    max_age_hours: int = 12
    min_days_to_expiry: int = 14
    min_change_bps: int = 500
    history_days: int = 90

    rpc_url: str = "http://127.0.0.1:8545"
    agent_private_key: SecretStr | None = None
    deployments_path: str = "../contracts/deployments/arbitrum-sepolia.json"
    runs_dir: str = "../api/data/runs"
    max_gas_per_run: int = 3_000_000
