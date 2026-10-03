// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import {Fixture} from "./helpers/Fixture.sol";
import {StrategyVault} from "../src/StrategyVault.sol";
import {MockYieldAdapter} from "../src/MockYieldAdapter.sol";
import {MockUSDG} from "../src/MockUSDG.sol";

contract StrategyVaultTest is Fixture {
    function test_depositMintsSharesAndForwardsToAdapter() public {
        _mintAndDeposit(alice, fixedVault, 100e6);
        assertGt(fixedVault.balanceOf(alice), 0);
        assertEq(usdg.balanceOf(address(fixedAdapter)), 100e6);
        assertEq(usdg.balanceOf(address(fixedVault)), 0);
    }

    function test_sharePriceRisesWithTime() public {
        _mintAndDeposit(alice, fixedVault, 100e6);
        uint256 shares = fixedVault.balanceOf(alice);
        vm.warp(block.timestamp + 180 days);
        assertGt(fixedVault.convertToAssets(shares), 100e6);
    }

    function test_withdrawRoundTripAfterAccrual() public {
        _mintAndDeposit(alice, fixedVault, 100e6);
        uint256 shares = fixedVault.balanceOf(alice);
        vm.warp(block.timestamp + 180 days);
        vm.prank(alice);
        fixedVault.redeem(shares, alice, alice);
        assertGe(usdg.balanceOf(alice), 104e6);
        assertEq(fixedVault.balanceOf(alice), 0);
    }

    function test_setAdapterOnlyOnce() public {
        vm.prank(admin);
        vm.expectRevert(StrategyVault.AdapterAlreadySet.selector);
        fixedVault.setAdapter(fixedAdapter);
    }

    function test_setAdapterRejectsAssetMismatch() public {
        StrategyVault v = new StrategyVault(usdg, "X", "X", admin);
        MockYieldAdapter other = new MockYieldAdapter(new MockUSDG(), address(v), 0, admin);
        vm.prank(admin);
        vm.expectRevert(StrategyVault.AdapterAssetMismatch.selector);
        v.setAdapter(other);
    }

    function test_setAdapterRejectsForeignVault() public {
        StrategyVault v = new StrategyVault(usdg, "X", "X", admin);
        vm.prank(admin);
        vm.expectRevert(StrategyVault.AdapterVaultMismatch.selector);
        v.setAdapter(fixedAdapter);
    }

    function test_setAdapterEmitsEvent() public {
        StrategyVault v = new StrategyVault(usdg, "X", "X", admin);
        MockYieldAdapter a = new MockYieldAdapter(usdg, address(v), 0, admin);
        vm.expectEmit(true, false, false, false, address(v));
        emit StrategyVault.AdapterSet(address(a));
        vm.prank(admin);
        v.setAdapter(a);
    }

    function test_depositBeforeAdapterReverts() public {
        StrategyVault v = new StrategyVault(usdg, "X", "X", admin);
        usdg.mint(alice, 1e6);
        vm.startPrank(alice);
        usdg.approve(address(v), 1e6);
        vm.expectRevert(StrategyVault.AdapterNotSet.selector);
        v.deposit(1e6, alice);
        vm.stopPrank();
    }

    function test_onlyVaultCanCallAdapter() public {
        vm.prank(alice);
        vm.expectRevert(MockYieldAdapter.OnlyVault.selector);
        fixedAdapter.deposit(1e6);
    }
}
