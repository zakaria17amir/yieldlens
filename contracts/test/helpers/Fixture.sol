// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import {Test} from "forge-std/Test.sol";
import {MockUSDG} from "../../src/MockUSDG.sol";
import {MockYieldAdapter} from "../../src/MockYieldAdapter.sol";
import {StrategyVault} from "../../src/StrategyVault.sol";

abstract contract Fixture is Test {
    MockUSDG internal usdg;
    StrategyVault internal fixedVault;
    StrategyVault internal floatingVault;
    MockYieldAdapter internal fixedAdapter;
    MockYieldAdapter internal floatingAdapter;

    address internal admin = makeAddr("admin");
    address internal agent = makeAddr("agent");
    address internal alice = makeAddr("alice");
    address internal bob = makeAddr("bob");

    function setUp() public virtual {
        usdg = new MockUSDG();
        fixedVault = new StrategyVault(usdg, "YieldLens Fixed USDG", "ylFIX", admin);
        floatingVault = new StrategyVault(usdg, "YieldLens Floating USDG", "ylFLT", admin);
        fixedAdapter = new MockYieldAdapter(usdg, address(fixedVault), 1000, admin);
        floatingAdapter = new MockYieldAdapter(usdg, address(floatingVault), 2000, admin);
        vm.startPrank(admin);
        fixedVault.setAdapter(fixedAdapter);
        floatingVault.setAdapter(floatingAdapter);
        vm.stopPrank();
    }

    function _mintAndDeposit(address user, StrategyVault v, uint256 assets) internal {
        usdg.mint(user, assets);
        vm.startPrank(user);
        usdg.approve(address(v), assets);
        v.deposit(assets, user);
        vm.stopPrank();
    }
}
