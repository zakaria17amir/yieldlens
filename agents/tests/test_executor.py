import pytest
from web3 import Web3

from desk.executor import Executor, Policy, plan_move
from desk.schemas import Move, Skip

FIXED = "0xFIXED"
FLOATING = "0xFLOATING"
HASH = "0x" + "ab" * 32


def _plan(fixed, floating, policy, target, now=1000, allowance_ok=True):
    return plan_move(
        fixed,
        floating,
        policy,
        target,
        now,
        allowance_ok,
        user="0xuser",
        fixed_vault=FIXED,
        floating_vault=FLOATING,
    )


ENABLED = Policy(enabled=True, max_move_bps=10_000, cooldown=0, last_move=0)


def test_plan_zero_balance_skips_no_balance():
    assert _plan(0, 0, ENABLED, 5000) == Skip(user="0xuser", reason="no_balance")


def test_plan_missing_allowance_skips():
    assert _plan(0, 100, ENABLED, 5000, allowance_ok=False).reason == "no_allowance"


def test_plan_disabled_policy_skips():
    policy = Policy(False, 10_000, 0, 0)
    assert _plan(0, 100, policy, 5000).reason == "policy_disabled"


def test_plan_clips_to_cap():
    policy = Policy(True, 2500, 0, 0)
    plan = _plan(1000, 9000, policy, 10_000)
    assert plan == Move(user="0xuser", from_vault=FLOATING, to_vault=FIXED, assets=2500)


def test_plan_direction_toward_floating():
    plan = _plan(8000, 2000, ENABLED, 5000)
    assert plan == Move(user="0xuser", from_vault=FIXED, to_vault=FLOATING, assets=3000)


def test_plan_cooldown_skips():
    policy = Policy(True, 10_000, 3600, 1000)
    assert _plan(0, 100, policy, 5000, now=2000).reason == "cooldown"
    assert isinstance(_plan(0, 100, policy, 5000, now=4600), Move)


def test_plan_first_move_ignores_cooldown():
    policy = Policy(True, 10_000, 2**32 - 1, 0)
    assert isinstance(_plan(0, 100, policy, 5000, now=10), Move)


def test_plan_at_target_is_below_min():
    assert _plan(5000, 5000, ENABLED, 5000).reason == "below_min"


def _send(w3, fn, sender):
    receipt = w3.eth.wait_for_transaction_receipt(fn.transact({"from": sender}))
    assert receipt["status"] == 1
    return receipt


class _World:
    def __init__(self, env):
        self.w3 = env["w3"]
        self.env = env
        d, abis = env["deployments"], env["abis"]
        self.usdg = self.w3.eth.contract(address=d["usdg"], abi=abis["MockUSDG"])
        self.fixed = self.w3.eth.contract(address=d["fixedVault"], abi=abis["StrategyVault"])
        self.floating = self.w3.eth.contract(address=d["floatingVault"], abi=abis["StrategyVault"])
        self.router = self.w3.eth.contract(address=d["router"], abi=abis["AgentRouter"])

    def executor(self, max_gas: int = 3_000_000) -> Executor:
        return Executor(
            self.w3, self.env["deployments"], self.env["abis"], self.env["agent_key"], max_gas
        )

    def fund(self, user, assets=100e6, *, approve_router=True, policy=(True, 5000, 0)):
        assets = int(assets)
        _send(self.w3, self.usdg.functions.mint(user, assets), self.env["deployer"])
        _send(self.w3, self.usdg.functions.approve(self.floating.address, assets), user)
        _send(self.w3, self.floating.functions.deposit(assets, user), user)
        if approve_router:
            _send(self.w3, self.floating.functions.approve(self.router.address, 2**256 - 1), user)
            _send(self.w3, self.fixed.functions.approve(self.router.address, 2**256 - 1), user)
        _send(self.w3, self.router.functions.setPolicy(*policy), user)

    def agent_nonce(self) -> int:
        return self.w3.eth.get_transaction_count(self.env["agent"])


@pytest.fixture
def world(chain):
    return _World(chain)


@pytest.mark.anvil
def test_execute_moves_delegated_user(world):
    alice = world.env["users"][0]
    world.fund(alice)
    report = world.executor().execute(10_000, HASH)
    assert [m.user for m in report.moves] == [alice]
    assert report.moves[0].tx_hash and report.moves[0].tx_hash.startswith("0x")
    assert report.skipped == []
    assert report.gas_used > 0
    assets_fixed = world.router.functions.assetsOf(alice, world.fixed.address).call()
    assert abs(assets_fixed - 50_000_000) <= 1


@pytest.mark.anvil
def test_execute_skips_user_without_allowance(world):
    bob = world.env["users"][1]
    world.fund(bob, approve_router=False)
    nonce = world.agent_nonce()
    report = world.executor().execute(10_000, HASH)
    assert report.moves == []
    assert [(s.user, s.reason) for s in report.skipped] == [(bob, "no_allowance")]
    assert world.agent_nonce() == nonce


@pytest.mark.anvil
def test_execute_skips_zero_balance_user_without_sending(world):
    carol = world.env["users"][2]
    _send(world.w3, world.router.functions.setPolicy(True, 10_000, 0), carol)
    nonce = world.agent_nonce()
    report = world.executor().execute(10_000, HASH)
    assert [(s.user, s.reason) for s in report.skipped] == [(carol, "no_balance")]
    assert world.agent_nonce() == nonce


@pytest.mark.anvil
def test_list_delegated_users_latest_event_wins(world):
    alice, bob = world.env["users"][0], world.env["users"][1]
    _send(world.w3, world.router.functions.setPolicy(True, 5000, 0), alice)
    _send(world.w3, world.router.functions.setPolicy(True, 5000, 0), bob)
    _send(world.w3, world.router.functions.setPolicy(False, 5000, 0), bob)
    assert world.executor().list_delegated_users() == [Web3.to_checksum_address(alice)]


@pytest.mark.anvil
def test_execute_reports_tx_failed_on_revert(world):
    alice = world.env["users"][0]
    world.fund(alice)
    role = world.router.functions.AGENT_ROLE().call()
    _send(world.w3, world.router.functions.revokeRole(role, world.env["agent"]), world.env["deployer"])
    report = world.executor().execute(10_000, HASH)
    assert report.moves == []
    assert [(s.user, s.reason) for s in report.skipped] == [(alice, "tx_failed")]


@pytest.mark.anvil
def test_execute_stops_at_gas_cap(world):
    users = world.env["users"][:2]
    for user in users:
        world.fund(user)
    nonce = world.agent_nonce()
    report = world.executor(max_gas=1).execute(10_000, HASH)
    assert report.moves == []
    assert sorted(s.user for s in report.skipped) == sorted(users)
    assert {s.reason for s in report.skipped} == {"gas_cap"}
    assert world.agent_nonce() == nonce
