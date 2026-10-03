// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import {Test} from "forge-std/Test.sol";
import {MockUSDG} from "../../src/MockUSDG.sol";
import {MockYieldAdapter} from "../../src/MockYieldAdapter.sol";
import {StrategyVault} from "../../src/StrategyVault.sol";
import {AgentRouter} from "../../src/AgentRouter.sol";

abstract contract Fixture is Test {
    MockUSDG internal usdg;
    StrategyVault internal fixedVault;
    StrategyVault internal floatingVault;
    MockYieldAdapter internal fixedAdapter;
    MockYieldAdapter internal floatingAdapter;
    AgentRouter internal router;

    address internal admin = makeAddr("admin");
    address internal agent = makeAddr("agent");
    address internal alice = makeAddr("alice");
    address internal bob = makeAddr("bob");

    function setUp() public virtual {
        vm.warp(1_700_000_000);
        usdg = new MockUSDG();
        fixedVault = new StrategyVault(usdg, "YieldLens Fixed USDG", "ylFIX", admin);
        floatingVault = new StrategyVault(usdg, "YieldLens Floating USDG", "ylFLT", admin);
        fixedAdapter = new MockYieldAdapter(usdg, address(fixedVault), 1000, admin);
        floatingAdapter = new MockYieldAdapter(usdg, address(floatingVault), 2000, admin);
        router = new AgentRouter(admin);
        usdg.setMinter(address(fixedAdapter), true);
        usdg.setMinter(address(floatingAdapter), true);
        vm.startPrank(admin);
        fixedVault.setAdapter(fixedAdapter);
        floatingVault.setAdapter(floatingAdapter);
        router.setVaults(address(fixedVault), address(floatingVault));
        router.grantRole(router.AGENT_ROLE(), agent);
        vm.stopPrank();
    }

    function _mintAndDeposit(address user, StrategyVault v, uint256 assets) internal {
        usdg.mint(user, assets);
        vm.startPrank(user);
        usdg.approve(address(v), assets);
        v.deposit(assets, user);
        fixedVault.approve(address(router), type(uint256).max);
        floatingVault.approve(address(router), type(uint256).max);
        vm.stopPrank();
    }
}
