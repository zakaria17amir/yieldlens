// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import {Vm} from "forge-std/Vm.sol";
import {Fixture} from "./helpers/Fixture.sol";
import {AgentRouter} from "../src/AgentRouter.sol";

contract AgentRouterFuzzTest is Fixture {
    function testFuzz_neverExceedsCap(uint96 balance, uint16 bps, uint96 assets) public {
        uint256 bal = bound(balance, 1e6, 1e13);
        uint16 capBps = uint16(bound(bps, 0, 10_000));
        uint256 amount = bound(assets, 1, bal);
        _mintAndDeposit(alice, floatingVault, bal);
        vm.prank(alice);
        router.setPolicy(true, capBps, 0);
        uint256 cap = router.userTotalAssets(alice) * capBps / 10_000;

        if (amount > cap) {
            vm.expectRevert(abi.encodeWithSelector(AgentRouter.ExceedsCap.selector, amount, cap));
            vm.prank(agent);
            router.moveFor(alice, address(floatingVault), address(fixedVault), amount, bytes32(0));
            return;
        }
        vm.recordLogs();
        vm.prank(agent);
        router.moveFor(alice, address(floatingVault), address(fixedVault), amount, bytes32(0));
        Vm.Log[] memory logs = vm.getRecordedLogs();
        uint256 received;
        for (uint256 i; i < logs.length; i++) {
            if (logs[i].emitter == address(router) && logs[i].topics[0] == AgentRouter.Moved.selector) {
                (received,,) = abi.decode(logs[i].data, (uint256, bytes32, bool));
            }
        }
        assertGt(received, 0);
        assertLe(received, cap);
        assertEq(usdg.balanceOf(address(router)), 0);
    }

    function testFuzz_cooldownRespected(uint32 cooldown, uint32 elapsed) public {
        uint32 cd = cooldown;
        _mintAndDeposit(alice, floatingVault, 100e6);
        vm.prank(alice);
        router.setPolicy(true, 10_000, cd);

        vm.prank(agent);
        router.moveFor(alice, address(floatingVault), address(fixedVault), 10e6, bytes32(0));
        vm.warp(block.timestamp + elapsed);

        vm.prank(agent);
        if (elapsed < cd) {
            vm.expectRevert(
                abi.encodeWithSelector(AgentRouter.CooldownActive.selector, uint64(block.timestamp - elapsed + cd))
            );
        }
        router.moveFor(alice, address(floatingVault), address(fixedVault), 10e6, bytes32(0));
    }
}
