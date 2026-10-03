import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from web3 import Web3

from desk.config import Settings
from desk.schemas import ExecutionReport, Move, Skip

logger = logging.getLogger(__name__)

CONTRACT_NAMES = ("MockUSDG", "StrategyVault", "AgentRouter", "MockYieldAdapter")


class ExecutorProtocol(Protocol):
    def execute(self, target_fixed_bps: int, report_hash: str) -> ExecutionReport: ...


class NoopExecutor:
    def list_delegated_users(self) -> list[str]:
        return []

    def execute(self, target_fixed_bps: int, report_hash: str) -> ExecutionReport:
        return ExecutionReport(moves=[], skipped=[], gas_used=0)


@dataclass(frozen=True)
class Policy:
    enabled: bool
    max_move_bps: int
    cooldown: int
    last_move: int


def plan_move(
    fixed_assets: int,
    floating_assets: int,
    policy: Policy,
    target_fixed_bps: int,
    now: int,
    allowance_ok: bool,
    *,
    user: str = "",
    fixed_vault: str = "",
    floating_vault: str = "",
) -> Move | Skip:
    total = fixed_assets + floating_assets
    if total == 0:
        return Skip(user=user, reason="no_balance")
    if not policy.enabled:
        return Skip(user=user, reason="policy_disabled")
    if policy.last_move != 0 and now < policy.last_move + policy.cooldown:
        return Skip(user=user, reason="cooldown")
    if not allowance_ok:
        return Skip(user=user, reason="no_allowance")

    delta = total * target_fixed_bps // 10_000 - fixed_assets
    cap = total * policy.max_move_bps // 10_000
    assets = min(abs(delta), cap)
    if assets == 0:
        return Skip(user=user, reason="below_min")
    if delta > 0:
        return Move(user=user, from_vault=floating_vault, to_vault=fixed_vault, assets=assets)
    return Move(user=user, from_vault=fixed_vault, to_vault=floating_vault, assets=assets)


def _hex(value: bytes) -> str:
    return "0x" + value.hex().removeprefix("0x")


class Executor:
    GAS_BUFFER_NUM = 12
    GAS_BUFFER_DEN = 10

    def __init__(
        self,
        w3: Web3,
        deployments: dict,
        abis: dict,
        agent_key: str,
        max_gas_per_run: int = 3_000_000,
    ):
        self._w3 = w3
        self._deployments = deployments
        self._key = agent_key
        self._agent = w3.eth.account.from_key(agent_key).address
        self._max_gas = max_gas_per_run
        self._router = w3.eth.contract(
            address=Web3.to_checksum_address(deployments["router"]), abi=abis["AgentRouter"]
        )
        self._vault_abi = abis["StrategyVault"]
        self._fixed = Web3.to_checksum_address(deployments["fixedVault"])
        self._floating = Web3.to_checksum_address(deployments["floatingVault"])

    @classmethod
    def from_settings(cls, settings: Settings) -> "Executor":
        if settings.agent_private_key is None:
            raise RuntimeError("AGENT_PRIVATE_KEY is required to execute moves")
        path = Path(settings.deployments_path)
        deployments = json.loads(path.read_text(encoding="utf-8"))
        abis = {
            name: json.loads((path.parent / "abi" / f"{name}.json").read_text(encoding="utf-8"))
            for name in CONTRACT_NAMES
        }
        w3 = Web3(Web3.HTTPProvider(settings.rpc_url))
        return cls(
            w3,
            deployments,
            abis,
            settings.agent_private_key.get_secret_value(),
            settings.max_gas_per_run,
        )

    def _vault(self, address: str):
        return self._w3.eth.contract(address=address, abi=self._vault_abi)

    def list_delegated_users(self, from_block: int | None = None) -> list[str]:
        start = self._deployments.get("deployedAtBlock", 0) if from_block is None else from_block
        logs = self._router.events.PolicySet().get_logs(from_block=start)
        latest: dict[str, bool] = {}
        for log in sorted(logs, key=lambda e: (e["blockNumber"], e["logIndex"])):
            latest[log["args"]["user"]] = log["args"]["enabled"]
        return [user for user, enabled in latest.items() if enabled]

    def user_state(self, user: str) -> tuple[int, int, Policy, bool]:
        router_address = self._router.address
        fixed_assets = self._router.functions.assetsOf(user, self._fixed).call()
        floating_assets = self._router.functions.assetsOf(user, self._floating).call()
        enabled, max_bps, cooldown, last_move = self._router.functions.policies(user).call()
        allowance_ok = True
        for address in (self._fixed, self._floating):
            vault = self._vault(address)
            if vault.functions.allowance(user, router_address).call() < vault.functions.balanceOf(user).call():
                allowance_ok = False
        return fixed_assets, floating_assets, Policy(enabled, max_bps, cooldown, last_move), allowance_ok

    def execute(self, target_fixed_bps: int, report_hash: str) -> ExecutionReport:
        w3 = self._w3
        now = w3.eth.get_block("latest")["timestamp"]
        digest = bytes.fromhex(report_hash.removeprefix("0x"))
        moves: list[Move] = []
        skipped: list[Skip] = []
        gas_used = 0
        cap_hit = False

        for user in self.list_delegated_users():
            try:
                fixed_assets, floating_assets, policy, allowance_ok = self.user_state(user)
                plan = plan_move(
                    fixed_assets,
                    floating_assets,
                    policy,
                    target_fixed_bps,
                    now,
                    allowance_ok,
                    user=user,
                    fixed_vault=self._fixed,
                    floating_vault=self._floating,
                )
            except Exception:
                logger.exception("could not plan move for %s", user)
                skipped.append(Skip(user=user, reason="tx_failed"))
                continue
            if isinstance(plan, Skip):
                skipped.append(plan)
                continue
            if cap_hit:
                skipped.append(Skip(user=user, reason="gas_cap"))
                continue
            tx_hash = None
            try:
                call = self._router.functions.moveFor(
                    user, plan.from_vault, plan.to_vault, plan.assets, digest
                )
                estimate = call.estimate_gas({"from": self._agent})
                if gas_used + estimate > self._max_gas:
                    cap_hit = True
                    skipped.append(Skip(user=user, reason="gas_cap"))
                    continue
                tx = call.build_transaction(
                    {
                        "from": self._agent,
                        "nonce": w3.eth.get_transaction_count(self._agent, "pending"),
                        "gas": estimate * self.GAS_BUFFER_NUM // self.GAS_BUFFER_DEN,
                    }
                )
                signed = w3.eth.account.sign_transaction(tx, self._key)
                tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
                receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)
            except Exception:
                logger.exception(
                    "moveFor failed for %s (tx %s)", user, _hex(tx_hash) if tx_hash else "not sent"
                )
                skipped.append(Skip(user=user, reason="tx_failed"))
                continue
            gas_used += receipt["gasUsed"]
            if receipt["status"] != 1:
                skipped.append(Skip(user=user, reason="tx_failed"))
                continue
            moves.append(plan.model_copy(update={"tx_hash": _hex(tx_hash)}))

        return ExecutionReport(moves=moves, skipped=skipped, gas_used=gas_used)
