// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import {Test} from "forge-std/Test.sol";
import {MockUSDG} from "../src/MockUSDG.sol";
import {MockYieldAdapter} from "../src/MockYieldAdapter.sol";

contract MockYieldAdapterTest is Test {
    MockUSDG usdg;
    MockYieldAdapter adapter;
    address vault = makeAddr("vault");
    address owner = makeAddr("owner");

    function setUp() public {
        usdg = new MockUSDG();
        adapter = new MockYieldAdapter(usdg, vault, 1000, owner);
    }

    function _vaultDeposit(uint256 assets) internal {
        usdg.mint(vault, assets);
        vm.startPrank(vault);
        usdg.approve(address(adapter), assets);
        adapter.deposit(assets);
        vm.stopPrank();
    }

    function test_decimalsIs6() public view {
        assertEq(usdg.decimals(), 6);
    }

    function test_depositOnlyVault() public {
        vm.expectRevert(MockYieldAdapter.OnlyVault.selector);
        adapter.deposit(1);
        vm.expectRevert(MockYieldAdapter.OnlyVault.selector);
        adapter.withdraw(1, address(this));
    }

    function test_accruesLinearly() public {
        _vaultDeposit(1_000_000e6);
        vm.warp(block.timestamp + 365 days);
        assertApproxEqAbs(adapter.totalAssets(), 1_100_000e6, 1);
    }

    function test_withdrawPaysAccrued() public {
        _vaultDeposit(1_000_000e6);
        vm.warp(block.timestamp + 365 days);
        uint256 total = adapter.totalAssets();
        vm.prank(vault);
        adapter.withdraw(total, vault);
        assertEq(usdg.balanceOf(vault), total);
        assertEq(adapter.principal(), 0);
    }

    function test_setAprBpsRejectsOver10000() public {
        vm.startPrank(owner);
        vm.expectRevert(MockYieldAdapter.InvalidBps.selector);
        adapter.setAprBps(10_001);
        adapter.setAprBps(10_000);
        vm.stopPrank();
        assertEq(adapter.aprBps(), 10_000);
    }
}
