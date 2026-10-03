# Lane A — Contracts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Two ERC-4626 USDG vaults with mock yield adapters and an `AgentRouter` that lets agents move opted-in users between the vaults inside user-set limits, deployed to Arbitrum Sepolia.

**Architecture:** `StrategyVault` (OZ ERC4626) forwards assets to one `IYieldAdapter`. `MockYieldAdapter` accrues simulated yield by minting `MockUSDG`. `AgentRouter` holds per-user `Policy`, knows exactly two vaults, and performs withdraw-then-deposit on behalf of users with the user as receiver.

**Tech Stack:** Solidity ^0.8.24, Foundry, OpenZeppelin Contracts v5.1.0.

**Spec:** `docs/superpowers/specs/2026-10-03-yieldlens-agentic-design.md` §4. Shared interfaces: `2026-10-03-00-overview.md`.

## Global Constraints

See overview. Additionally: custom errors, not revert strings; `forge fmt` clean; `forge test` must pass with `-vvv` silent on failures; no `console.log` left in `src/`.

## Review Focus

Covered in overview items 1 and 3; tests pinned in Task A4.

---

## File structure

```
contracts/
  foundry.toml
  remappings.txt
  src/
    MockUSDG.sol
    interfaces/IYieldAdapter.sol
    MockYieldAdapter.sol
    StrategyVault.sol
    AgentRouter.sol
  test/
    MockYieldAdapter.t.sol
    StrategyVault.t.sol
    AgentRouter.t.sol
    AgentRouter.fuzz.t.sol
    Invariants.t.sol
    helpers/Fixture.sol         // deploys the full system for tests
  script/
    Deploy.s.sol
  deployments/
    arbitrum-sepolia.json       // written by Deploy.s.sol
    abi/                        // written by export-abis.sh
  export-abis.sh
```

---

### Task A0: Repo scaffold (merge to `main` before other lanes branch)

**Files:**
- Create: `.gitignore`, `README.md` (title + one-paragraph summary + lane table), `.github/workflows/contracts.yml`, `.editorconfig`
- Create: `contracts/` via `forge init --no-git --no-commit contracts` then delete the sample `Counter` files

- [ ] **Step 1:** `forge init --no-git contracts`; remove `src/Counter.sol`, `test/Counter.t.sol`, `script/Counter.s.sol`.
- [ ] **Step 2:** `cd contracts && forge install OpenZeppelin/openzeppelin-contracts@v5.1.0 --no-git`; write `remappings.txt` with `@openzeppelin/=lib/openzeppelin-contracts/`.
- [ ] **Step 3:** `foundry.toml`: `solc = "0.8.24"`, `optimizer = true`, `optimizer_runs = 200`, `fs_permissions = [{ access = "read-write", path = "./deployments" }]`, `[rpc_endpoints] arbitrum_sepolia = "${ARBITRUM_SEPOLIA_RPC_URL}"`, `[fuzz] runs = 512`, `[invariant] runs = 64, depth = 32`.
- [ ] **Step 4:** `.gitignore`: `contracts/out contracts/cache contracts/lib/**/.git .env **/__pycache__ agents/.venv api/.venv api/data/runs/*.json !api/data/runs/.gitkeep web/node_modules web/dist`.
- [ ] **Step 5:** `.github/workflows/contracts.yml`: on push/PR touching `contracts/**`; `foundry-rs/foundry-toolchain@v1`; run `forge fmt --check`, `forge build`, `forge test`.
- [ ] **Step 6:** Verify: `cd contracts && forge build` → `Compiler run successful`.
- [ ] **Step 7:** Commit `chore: scaffold monorepo and foundry project`.

---

### Task A1: MockUSDG, IYieldAdapter, MockYieldAdapter

**Files:**
- Create: `contracts/src/MockUSDG.sol`, `contracts/src/interfaces/IYieldAdapter.sol`, `contracts/src/MockYieldAdapter.sol`
- Test: `contracts/test/MockYieldAdapter.t.sol`

**Interfaces:**
- Produces:
  ```solidity
  contract MockUSDG is ERC20 { constructor() ERC20("Global Dollar", "USDG"); function decimals() public pure override returns (uint8) { return 6; } function mint(address to, uint256 amount) external; }
  interface IYieldAdapter { function asset() external view returns (address); function totalAssets() external view returns (uint256); function deposit(uint256 assets) external; function withdraw(uint256 assets, address to) external; }
  contract MockYieldAdapter is IYieldAdapter, Ownable {
      error OnlyVault();
      constructor(MockUSDG asset_, address vault_, uint256 aprBps_, address owner_);
      function vault() external view returns (address);
      function aprBps() external view returns (uint256);
      function setAprBps(uint256 newAprBps) external onlyOwner;   // revert InvalidBps if > 10000
      function principal() external view returns (uint256);
      function accrue() public;   // mints pending yield into this contract, adds to principal, sets lastAccrual
  }
  ```
- `totalAssets()` = `principal + principal * aprBps * (block.timestamp - lastAccrual) / (10_000 * 365 days)`.
- `deposit`/`withdraw` are `onlyVault`; both call `accrue()` first. `withdraw(assets, to)` transfers USDG to `to`.

- [ ] **Step 1: Write failing tests** in `MockYieldAdapter.t.sol`:
  - `test_decimalsIs6()` — `usdg.decimals() == 6`.
  - `test_depositOnlyVault()` — non-vault caller reverts `OnlyVault`.
  - `test_accruesLinearly()` — vault deposits 1_000_000e6 at 1000 bps; `vm.warp(+365 days)`; `totalAssets() == 1_100_000e6` (allow ±1).
  - `test_withdrawPaysAccrued()` — after warp, vault withdraws `totalAssets()` to itself; vault USDG balance equals that amount; adapter `principal() == 0`.
  - `test_setAprBpsRejectsOver10000()`.
- [ ] **Step 2:** `forge test --match-contract MockYieldAdapterTest` → FAIL (compile errors).
- [ ] **Step 3:** Implement the three files per the interface above.
- [ ] **Step 4:** `forge test --match-contract MockYieldAdapterTest -vv` → all PASS.
- [ ] **Step 5:** Commit `feat(contracts): mock USDG and yield adapter`.

---

### Task A2: StrategyVault

**Files:**
- Create: `contracts/src/StrategyVault.sol`
- Create: `contracts/test/helpers/Fixture.sol`
- Test: `contracts/test/StrategyVault.t.sol`

**Interfaces:**
- Consumes: A1.
- Produces:
  ```solidity
  contract StrategyVault is ERC4626, Ownable {
      error AdapterAlreadySet(); error AdapterNotSet();
      constructor(IERC20 asset_, string memory name_, string memory symbol_, address owner_);
      function adapter() external view returns (IYieldAdapter);
      function setAdapter(IYieldAdapter adapter_) external onlyOwner;   // once; adapter.asset() must equal asset()
      function totalAssets() public view override returns (uint256);   // adapter.totalAssets(), 0 if unset
      function _decimalsOffset() internal pure override returns (uint8) { return 3; }
  }
  ```
- `_deposit` override: `super._deposit(...)`, then `SafeERC20.forceApprove(asset, adapter, assets)` and `adapter.deposit(assets)`.
- `_withdraw` override: `adapter.withdraw(assets, address(this))`, then `super._withdraw(...)`. Revert `AdapterNotSet` if adapter unset in either.
- `Fixture.sol`: abstract contract that deploys `usdg`, `fixedVault` (name "YieldLens Fixed USDG", symbol "ylFIX"), `floatingVault` ("YieldLens Floating USDG", "ylFLT"), two adapters (fixed 1000 bps, floating 2000 bps), `router` (Task A3; stub until then), with `admin`, `agent`, `alice`, `bob` addresses, and a helper `_mintAndDeposit(address user, StrategyVault v, uint256 assets)` that mints, approves, deposits as `user`, and approves the router on shares.

- [ ] **Step 1: Write failing tests** in `StrategyVault.t.sol`:
  - `test_depositMintsSharesAndForwardsToAdapter()` — alice deposits 100e6; `vault.balanceOf(alice) > 0`; `usdg.balanceOf(address(adapter)) == 100e6`; `usdg.balanceOf(address(vault)) == 0`.
  - `test_sharePriceRisesWithTime()` — deposit; `vm.warp(+180 days)`; `convertToAssets(shares) > 100e6`.
  - `test_withdrawRoundTripAfterAccrual()` — redeem all shares after warp; alice receives `>= 104e6` at 1000 bps (≈ +4.93%).
  - `test_setAdapterOnlyOnce()` — second `setAdapter` reverts `AdapterAlreadySet`.
  - `test_depositBeforeAdapterReverts()` — fresh vault without adapter reverts `AdapterNotSet`.
  - `test_onlyVaultCanCallAdapter()` — alice calling `adapter.deposit` reverts `OnlyVault`.
- [ ] **Step 2:** `forge test --match-contract StrategyVaultTest` → FAIL.
- [ ] **Step 3:** Implement `StrategyVault.sol` and `Fixture.sol`.
- [ ] **Step 4:** `forge test --match-contract StrategyVaultTest -vv` → PASS.
- [ ] **Step 5:** Commit `feat(contracts): ERC-4626 strategy vault over yield adapter`.

---

### Task A3: AgentRouter — policy, vault pair, moveSelf

**Files:**
- Create: `contracts/src/AgentRouter.sol`
- Modify: `contracts/test/helpers/Fixture.sol` (deploy router, grant `AGENT_ROLE` to `agent`, `setVaults`)
- Test: `contracts/test/AgentRouter.t.sol`

**Interfaces:**
- Produces (see overview for the full external surface):
  ```solidity
  contract AgentRouter is AccessControl, Pausable, ReentrancyGuard {
      bytes32 public constant AGENT_ROLE = keccak256("AGENT_ROLE");
      error NotAllowedVault(address vault); error SameVault(); error InvalidBps(); error ZeroAssets();
      error PolicyDisabled(address user); error CooldownActive(uint64 availableAt); error ExceedsCap(uint256 assets, uint256 cap);
      constructor(address admin);
      function setVaults(address fixedVault_, address floatingVault_) external onlyRole(DEFAULT_ADMIN_ROLE); // both must share asset(); emits VaultsSet
      function pause() external onlyRole(DEFAULT_ADMIN_ROLE); function unpause() external onlyRole(DEFAULT_ADMIN_ROLE);
      function assetsOf(address user, address vault) public view returns (uint256); // IERC4626(vault).convertToAssets(balanceOf(user))
      function userTotalAssets(address user) public view returns (uint256);        // assetsOf in both vaults
      function _move(address user, address from, address to, uint256 assets, bytes32 reportHash, bool byAgent) internal;
  }
  ```
- `_move`: validates `from`/`to` are the two vaults and differ, `assets > 0`; if `assets >= assetsOf(user, from)` then `IERC4626(from).redeem(balanceOf(user), address(this), user)` else `IERC4626(from).withdraw(assets, address(this), user)`; `received = usdg.balanceOf(this)` delta; `forceApprove(to, received)`; `IERC4626(to).deposit(received, user)`; emit `Moved(user, from, to, received, reportHash, byAgent)`.
- `setPolicy` reverts `InvalidBps` if `maxMoveBps > 10_000`; sets fields, keeps `lastMove`; emits `PolicySet`.
- `moveSelf` is `nonReentrant whenNotPaused`, calls `_move(msg.sender, …, false)`; no policy checks.

- [ ] **Step 1: Write failing tests** in `AgentRouter.t.sol`:
  - `test_setPolicyStoresAndEmits()` — alice sets `(true, 2500, 1 hours)`; `policies(alice)` matches; `PolicySet` emitted.
  - `test_setPolicyRejectsBpsOver10000()`.
  - `test_moveSelfMovesBetweenVaults()` — alice has 100e6 in floating; `moveSelf(floating, fixed, 40e6, hash)`; `assetsOf(alice, fixed)` within 1 wei of 40e6; `assetsOf(alice, floating)` within 1 wei of 60e6; `Moved(..., byAgent=false)` emitted.
  - `test_moveSelfFullBalanceUsesRedeem()` — move `assetsOf(alice, floating)` exactly; `floating.balanceOf(alice) == 0`; no revert.
  - `test_moveSelfRejectsUnknownVault()` — reverts `NotAllowedVault`.
  - `test_moveSelfRejectsSameVault()` — reverts `SameVault`.
  - `test_moveSelfWhenPausedReverts()` — `EnforcedPause`.
  - `test_setVaultsRequiresAdmin()`.
- [ ] **Step 2:** `forge test --match-contract AgentRouterTest` → FAIL.
- [ ] **Step 3:** Implement `AgentRouter.sol` (policy, vaults, `_move`, `moveSelf`; leave `moveFor` for A4) and update `Fixture.sol`.
- [ ] **Step 4:** `forge test --match-contract AgentRouterTest -vv` → PASS.
- [ ] **Step 5:** Commit `feat(contracts): AgentRouter with user policy and self moves`.

---

### Task A4: AgentRouter — moveFor guardrails and fuzz

**Files:**
- Modify: `contracts/src/AgentRouter.sol`
- Test: `contracts/test/AgentRouter.t.sol` (append), `contracts/test/AgentRouter.fuzz.t.sol`

**Interfaces:**
- Produces: `moveFor(address user, address fromVault, address toVault, uint256 assets, bytes32 reportHash) external onlyRole(AGENT_ROLE) whenNotPaused nonReentrant`.
- Check order inside `moveFor`: policy enabled → cooldown (`block.timestamp >= lastMove + cooldown`, else `CooldownActive(lastMove + cooldown)`) → cap (`assets <= userTotalAssets(user) * maxMoveBps / 10_000`, else `ExceedsCap`) → `_move(..., true)` → `policies[user].lastMove = uint64(block.timestamp)`.

- [ ] **Step 1: Write failing tests** appended to `AgentRouter.t.sol`:
  - `test_moveForRequiresAgentRole()` — alice calling reverts `AccessControlUnauthorizedAccount`.
  - `test_moveForPolicyDisabledReverts()`.
  - `test_moveForAtExactCapSucceeds()` — 100e6 total, cap 2500 → 25e6 succeeds.
  - `test_moveForOverCapReverts()` — 25e6 + 1 reverts `ExceedsCap`.
  - `test_moveForCooldownBlocksSecondMove()` — second call before `cooldown` reverts `CooldownActive`; after `vm.warp(lastMove + cooldown)` succeeds.
  - `test_moveForZeroBalanceUserReverts()` — bob (no deposits, policy enabled) → `ExceedsCap(assets, 0)`. *(Review Focus 1)*
  - `test_moveForFullPositionWithCap10000()` — cap 10000, move everything; no revert; `from.balanceOf(alice) == 0`. *(Review Focus 3)*
  - `test_moveForEmitsByAgentTrue()`.
  - `test_revokedAgentCannotMove()` — admin `revokeRole`, then `moveFor` reverts.
  - `test_moveForWhenPausedReverts()`.
- [ ] **Step 2: Write fuzz tests** in `AgentRouter.fuzz.t.sol`:
  - `testFuzz_neverExceedsCap(uint96 balance, uint16 bps, uint96 assets)` — bound `bps ≤ 10000`, `balance ≥ 1e6`; deposit `balance`; if `assets > balance*bps/10000` expect revert else expect success.
  - `testFuzz_cooldownRespected(uint32 cooldown, uint32 elapsed)` — after a first move, second move succeeds iff `elapsed >= cooldown`.
- [ ] **Step 3:** `forge test --match-path 'test/AgentRouter*'` → FAIL on new tests.
- [ ] **Step 4:** Implement `moveFor`.
- [ ] **Step 5:** `forge test --match-path 'test/AgentRouter*' -vv` → PASS.
- [ ] **Step 6:** Commit `feat(contracts): agent moves with cap, cooldown and role guardrails`.

---

### Task A5: Invariants, deploy script, ABI export, deployments JSON

**Files:**
- Test: `contracts/test/Invariants.t.sol`
- Create: `contracts/script/Deploy.s.sol`, `contracts/export-abis.sh`, `contracts/deployments/abi/.gitkeep`
- Modify: `README.md` (deploy instructions, addresses table placeholder)

**Interfaces:**
- Produces: `contracts/deployments/arbitrum-sepolia.json` and `contracts/deployments/abi/*.json` in the exact shape from the overview.

- [ ] **Step 1: Write invariant test** `Invariants.t.sol` with a handler that randomly `deposit`s, `redeem`s, `moveSelf`s, `moveFor`s (as agent) and warps time:
  - `invariant_adapterBalancesBackVaults()` — for each vault: `usdg.balanceOf(adapter) == adapter.totalAssets()` after calling `adapter.accrue()`; and `vault.totalAssets() == adapter.totalAssets()`.
  - `invariant_usersNeverLoseMoreThanOneWeiPerMove()` — handler tracks per-user `sum(deposits) - sum(withdrawn)` vs current `userTotalAssets`; difference `≥ -moveCount` (yield only increases it).
- [ ] **Step 2:** `forge test --match-contract Invariants -vv` → PASS (fix contracts if not).
- [ ] **Step 3:** `Deploy.s.sol`: reads `DEPLOYER_PRIVATE_KEY`, `AGENT_ADDRESS`; deploys `MockUSDG`, both vaults (owner = deployer), adapters (fixed 1000 bps, floating 2000 bps), `setAdapter`, `AgentRouter(deployer)`, `setVaults`, `grantRole(AGENT_ROLE, AGENT_ADDRESS)`; mints 1_000_000e6 USDG to deployer; writes JSON via `vm.serializeAddress`/`vm.writeJson` to `deployments/arbitrum-sepolia.json` including `deployedAtBlock = block.number`.
- [ ] **Step 4:** Dry run: `forge script script/Deploy.s.sol --rpc-url arbitrum_sepolia` (no broadcast) → succeeds and writes the file locally with simulated addresses; delete that file.
- [ ] **Step 5:** `export-abis.sh`: for each of `MockUSDG StrategyVault AgentRouter MockYieldAdapter`, `forge inspect <C> abi --json > deployments/abi/<C>.json`. Run it; commit ABIs.
- [ ] **Step 6:** Human step: deployer runs `forge script … --broadcast --verify` with `ARBISCAN_API_KEY`, commits `arbitrum-sepolia.json`. Record addresses in README.
- [ ] **Step 7:** Commit `feat(contracts): invariants, deploy script, ABI export`.

---

### Task A6: Security review gate

- [ ] **Step 1:** Run `forge test --gas-report` and `slither . --filter-paths lib` (if slither installed; otherwise note skipped). Fix any high/medium findings.
- [ ] **Step 2:** Request an independent security-focused review of `contracts/src/*` against: reentrancy in `_move` (external calls to vaults), approval residue (`forceApprove` back to 0 after deposit), rounding direction in `assetsOf`, role management, pause coverage.
- [ ] **Step 3:** Address findings; commit `fix(contracts): address security review`.
