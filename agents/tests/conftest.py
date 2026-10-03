import json
import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest
import pytest_asyncio
from web3 import Web3

from desk.tools import http

ANVIL_URL = "http://127.0.0.1:8546"
DEPLOYER_KEY = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
AGENT_KEY = "0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d"
CONTRACT_NAMES = ("MockUSDG", "StrategyVault", "AgentRouter", "MockYieldAdapter")


@pytest_asyncio.fixture(autouse=True)
async def _close_http_client():
    yield
    await http.aclose()


def _contracts_dir() -> Path:
    return Path(os.environ.get("CONTRACTS_DIR", "../contracts")).resolve()


@pytest.fixture(scope="session")
def anvil():
    contracts = _contracts_dir()
    forge = shutil.which("forge")
    anvil_bin = shutil.which("anvil")
    if forge is None or anvil_bin is None or not (contracts / "script" / "Deploy.s.sol").exists():
        pytest.fail("anvil tests need forge and anvil on PATH and CONTRACTS_DIR pointing at the contracts")

    w3 = Web3(Web3.HTTPProvider(ANVIL_URL))
    process = None
    if not w3.is_connected():
        process = subprocess.Popen(
            [anvil_bin, "--port", "8546"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
    try:
        for _ in range(50):
            if w3.is_connected():
                break
            time.sleep(0.2)
        else:
            pytest.fail("anvil did not start")

        accounts = w3.eth.accounts
        env = {**os.environ, "DEPLOYER_PRIVATE_KEY": DEPLOYER_KEY, "AGENT_ADDRESS": accounts[1]}
        deployments_file = contracts / "deployments" / "arbitrum-sepolia.json"
        try:
            try:
                subprocess.run(
                    [forge, "script", "script/Deploy.s.sol", "--rpc-url", ANVIL_URL, "--broadcast"],
                    cwd=contracts,
                    env=env,
                    check=True,
                    capture_output=True,
                    text=True,
                )
            except subprocess.CalledProcessError as exc:
                print(exc.stderr)
                raise
            deployments = json.loads(deployments_file.read_text(encoding="utf-8"))
            abis = {
                name: json.loads(
                    (contracts / "deployments" / "abi" / f"{name}.json").read_text(encoding="utf-8")
                )
                for name in CONTRACT_NAMES
            }
        finally:
            deployments_file.unlink(missing_ok=True)
            shutil.rmtree(contracts / "broadcast", ignore_errors=True)

        yield {
            "w3": w3,
            "deployments": deployments,
            "abis": abis,
            "deployer": accounts[0],
            "agent": accounts[1],
            "users": accounts[2:10],
            "agent_key": AGENT_KEY,
        }
    finally:
        if process is not None:
            process.terminate()


@pytest.fixture
def chain(anvil):
    w3 = anvil["w3"]
    snapshot = w3.provider.make_request("evm_snapshot", [])["result"]
    yield anvil
    w3.provider.make_request("evm_revert", [snapshot])
