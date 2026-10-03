// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import {Test} from "forge-std/Test.sol";
import {Fixture} from "./helpers/Fixture.sol";
import {MockUSDG} from "../src/MockUSDG.sol";
import {AgentRouter} from "../src/AgentRouter.sol";
import {StrategyVault} from "../src/StrategyVault.sol";

contract RouterHandler is Test {
    MockUSDG public immutable usdg;
    AgentRouter public immutable router;
    StrategyVault public immutable fixedVault;
    StrategyVault public immutable floatingVault;
    address public immutable agent;
    address[] public actors;

    uint256 public moveCount;
    uint256 public depositCount;
    mapping(address => uint256) public deposited;
    mapping(address => uint256) public withdrawn;

    constructor(
        MockUSDG usdg_,
        AgentRouter router_,
        StrategyVault fixedVault_,
        StrategyVault floatingVault_,
        address agent_,
        address[] memory actors_
    ) {
        usdg = usdg_;
        router = router_;
        fixedVault = fixedVault_;
        floatingVault = floatingVault_;
        agent = agent_;
        for (uint256 i; i < actors_.length; i++) {
            address user = actors_[i];
            actors.push(user);
            vm.startPrank(user);
            usdg_.approve(address(fixedVault_), type(uint256).max);
            usdg_.approve(address(floatingVault_), type(uint256).max);
            fixedVault_.approve(address(router_), type(uint256).max);
            floatingVault_.approve(address(router_), type(uint256).max);
            router_.setPolicy(true, 5000, 0);
            vm.stopPrank();
        }
    }

    function _actor(uint256 seed) internal view returns (address) {
        return actors[seed % actors.length];
    }

    function _vault(uint256 seed) internal view returns (StrategyVault) {
        return seed % 2 == 0 ? fixedVault : floatingVault;
    }

    function _other(StrategyVault v) internal view returns (StrategyVault) {
        return v == fixedVault ? floatingVault : fixedVault;
    }

    function deposit(uint256 actorSeed, uint256 vaultSeed, uint256 amount) external {
        address user = _actor(actorSeed);
        amount = bound(amount, 1e6, 1e12);
        usdg.mint(user, amount);
        vm.prank(user);
        _vault(vaultSeed).deposit(amount, user);
        deposited[user] += amount;
        depositCount++;
    }

    function redeem(uint256 actorSeed, uint256 vaultSeed, uint256 shares) external {
        address user = _actor(actorSeed);
        StrategyVault v = _vault(vaultSeed);
        uint256 balance = v.balanceOf(user);
        if (balance == 0) return;
        shares = bound(shares, 1, balance);
        vm.prank(user);
        withdrawn[user] += v.redeem(shares, user, user);
    }

    function moveSelf(uint256 actorSeed, uint256 vaultSeed, uint256 amount) external {
        address user = _actor(actorSeed);
        StrategyVault from = _vault(vaultSeed);
        uint256 max = router.assetsOf(user, address(from));
        if (max == 0) return;
        amount = bound(amount, 1, max);
        vm.prank(user);
        router.moveSelf(address(from), address(_other(from)), amount, bytes32(0));
        moveCount++;
    }

    function agentMove(uint256 actorSeed, uint256 vaultSeed, uint256 amount) external {
        address user = _actor(actorSeed);
        StrategyVault from = _vault(vaultSeed);
        uint256 max = router.assetsOf(user, address(from));
        uint256 cap = router.userTotalAssets(user) * 5000 / 10_000;
        if (cap < max) max = cap;
        if (max == 0) return;
        amount = bound(amount, 1, max);
        vm.prank(agent);
        router.moveFor(user, address(from), address(_other(from)), amount, bytes32(0));
        moveCount++;
    }

    function warp(uint256 secs) external {
        vm.warp(block.timestamp + bound(secs, 0, 30 days));
    }
}

contract InvariantsTest is Fixture {
    RouterHandler handler;

    function setUp() public override {
        super.setUp();
        address[] memory actors = new address[](2);
        actors[0] = alice;
        actors[1] = bob;
        handler = new RouterHandler(usdg, router, fixedVault, floatingVault, agent, actors);
        targetContract(address(handler));
    }

    function invariant_adapterBalancesBackVaults() public {
        fixedAdapter.accrue();
        floatingAdapter.accrue();
        assertEq(usdg.balanceOf(address(fixedAdapter)), fixedAdapter.totalAssets());
        assertEq(usdg.balanceOf(address(floatingAdapter)), floatingAdapter.totalAssets());
        assertEq(fixedVault.totalAssets(), fixedAdapter.totalAssets());
        assertEq(floatingVault.totalAssets(), floatingAdapter.totalAssets());
    }

    /// ERC-4626 floors shares on deposit and assets on conversion, so each deposit and each move may round down by 1 wei.
    function invariant_usersNeverLoseMoreThanOneWeiPerMove() public view {
        address[2] memory users = [alice, bob];
        for (uint256 i; i < users.length; i++) {
            address u = users[i];
            assertGe(
                router.userTotalAssets(u) + handler.withdrawn(u) + handler.moveCount() + handler.depositCount(),
                handler.deposited(u)
            );
        }
    }

    function invariant_routerHoldsNothing() public view {
        assertEq(usdg.balanceOf(address(router)), 0);
    }
}
