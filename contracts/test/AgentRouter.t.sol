// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import {Pausable} from "@openzeppelin/contracts/utils/Pausable.sol";
import {IAccessControl} from "@openzeppelin/contracts/access/IAccessControl.sol";
import {Fixture} from "./helpers/Fixture.sol";
import {AgentRouter} from "../src/AgentRouter.sol";
import {StrategyVault} from "../src/StrategyVault.sol";
import {MockUSDG} from "../src/MockUSDG.sol";

contract AgentRouterTest is Fixture {
    event PolicySet(address indexed user, bool enabled, uint16 maxMoveBps, uint32 cooldown);
    event Moved(
        address indexed user,
        address indexed fromVault,
        address indexed toVault,
        uint256 assets,
        bytes32 reportHash,
        bool byAgent
    );

    bytes32 constant HASH = keccak256("report");

    function test_setPolicyStoresAndEmits() public {
        vm.expectEmit(true, false, false, true, address(router));
        emit PolicySet(alice, true, 2500, 1 hours);
        vm.prank(alice);
        router.setPolicy(true, 2500, 1 hours);
        (bool enabled, uint16 maxMoveBps, uint32 cooldown, uint64 lastMove) = router.policies(alice);
        assertTrue(enabled);
        assertEq(maxMoveBps, 2500);
        assertEq(cooldown, 1 hours);
        assertEq(lastMove, 0);
    }

    function test_setPolicyRejectsBpsOver10000() public {
        vm.prank(alice);
        vm.expectRevert(AgentRouter.InvalidBps.selector);
        router.setPolicy(true, 10_001, 0);
    }

    function test_moveSelfMovesBetweenVaults() public {
        _mintAndDeposit(alice, floatingVault, 100e6);
        vm.expectEmit(true, true, true, true, address(router));
        emit Moved(alice, address(floatingVault), address(fixedVault), 40e6, HASH, false);
        vm.prank(alice);
        router.moveSelf(address(floatingVault), address(fixedVault), 40e6, HASH);
        assertApproxEqAbs(router.assetsOf(alice, address(fixedVault)), 40e6, 1);
        assertApproxEqAbs(router.assetsOf(alice, address(floatingVault)), 60e6, 1);
        assertEq(usdg.balanceOf(address(router)), 0);
    }

    function test_moveSelfFullBalanceUsesRedeem() public {
        _mintAndDeposit(alice, floatingVault, 100e6);
        uint256 all = router.assetsOf(alice, address(floatingVault));
        vm.prank(alice);
        router.moveSelf(address(floatingVault), address(fixedVault), all, HASH);
        assertEq(floatingVault.balanceOf(alice), 0);
    }

    function test_moveSelfRejectsUnknownVault() public {
        _mintAndDeposit(alice, floatingVault, 100e6);
        vm.startPrank(alice);
        vm.expectRevert(abi.encodeWithSelector(AgentRouter.NotAllowedVault.selector, address(0xdead)));
        router.moveSelf(address(0xdead), address(fixedVault), 1e6, HASH);
        vm.expectRevert(abi.encodeWithSelector(AgentRouter.NotAllowedVault.selector, address(0xdead)));
        router.moveSelf(address(floatingVault), address(0xdead), 1e6, HASH);
        vm.stopPrank();
    }

    function test_moveSelfRejectsSameVault() public {
        vm.prank(alice);
        vm.expectRevert(AgentRouter.SameVault.selector);
        router.moveSelf(address(fixedVault), address(fixedVault), 1e6, HASH);
    }

    function test_moveSelfRejectsZeroAssets() public {
        vm.prank(alice);
        vm.expectRevert(AgentRouter.ZeroAssets.selector);
        router.moveSelf(address(fixedVault), address(floatingVault), 0, HASH);
    }

    function test_moveSelfBeforeVaultsSetReverts() public {
        AgentRouter fresh = new AgentRouter(admin);
        vm.prank(alice);
        vm.expectRevert(abi.encodeWithSelector(AgentRouter.NotAllowedVault.selector, address(0)));
        fresh.moveSelf(address(0), address(0), 1e6, HASH);
    }

    function test_moveSelfWhenPausedReverts() public {
        _mintAndDeposit(alice, floatingVault, 100e6);
        vm.prank(admin);
        router.pause();
        vm.prank(alice);
        vm.expectRevert(Pausable.EnforcedPause.selector);
        router.moveSelf(address(floatingVault), address(fixedVault), 1e6, HASH);
    }

    function test_setVaultsRequiresAdmin() public {
        bytes32 adminRole = router.DEFAULT_ADMIN_ROLE();
        vm.prank(alice);
        vm.expectRevert(
            abi.encodeWithSelector(IAccessControl.AccessControlUnauthorizedAccount.selector, alice, adminRole)
        );
        router.setVaults(address(fixedVault), address(floatingVault));
    }

    function test_setVaultsRejectsZeroAndMismatch() public {
        StrategyVault other = new StrategyVault(new MockUSDG(), "X", "X", admin);
        vm.startPrank(admin);
        vm.expectRevert(AgentRouter.ZeroAddress.selector);
        router.setVaults(address(0), address(floatingVault));
        vm.expectRevert(AgentRouter.AssetMismatch.selector);
        router.setVaults(address(fixedVault), address(other));
        vm.stopPrank();
    }

    function _delegate(address user, uint16 bps, uint32 cooldown) internal {
        vm.prank(user);
        router.setPolicy(true, bps, cooldown);
    }

    function _agentMove(address user, uint256 assets) internal {
        vm.prank(agent);
        router.moveFor(user, address(floatingVault), address(fixedVault), assets, HASH);
    }

    function test_moveForRequiresAgentRole() public {
        bytes32 agentRole = router.AGENT_ROLE();
        vm.prank(alice);
        vm.expectRevert(
            abi.encodeWithSelector(IAccessControl.AccessControlUnauthorizedAccount.selector, alice, agentRole)
        );
        router.moveFor(alice, address(floatingVault), address(fixedVault), 1e6, HASH);
    }

    function test_moveForPolicyDisabledReverts() public {
        _mintAndDeposit(alice, floatingVault, 100e6);
        vm.expectRevert(abi.encodeWithSelector(AgentRouter.PolicyDisabled.selector, alice));
        _agentMove(alice, 1e6);
    }

    function test_moveForAtExactCapSucceeds() public {
        _mintAndDeposit(alice, floatingVault, 100e6);
        _delegate(alice, 2500, 0);
        _agentMove(alice, 25e6);
        assertApproxEqAbs(router.assetsOf(alice, address(fixedVault)), 25e6, 1);
    }

    function test_moveForOverCapReverts() public {
        _mintAndDeposit(alice, floatingVault, 100e6);
        _delegate(alice, 2500, 0);
        uint256 cap = router.userTotalAssets(alice) * 2500 / 10_000;
        vm.expectRevert(abi.encodeWithSelector(AgentRouter.ExceedsCap.selector, cap + 1, cap));
        _agentMove(alice, cap + 1);
    }

    function test_moveForCooldownBlocksSecondMove() public {
        _mintAndDeposit(alice, floatingVault, 100e6);
        _delegate(alice, 10_000, 1 hours);
        _agentMove(alice, 10e6);
        (,,, uint64 lastMove) = router.policies(alice);
        assertEq(lastMove, block.timestamp);
        vm.expectRevert(abi.encodeWithSelector(AgentRouter.CooldownActive.selector, lastMove + 1 hours));
        _agentMove(alice, 10e6);
        vm.warp(lastMove + 1 hours);
        _agentMove(alice, 10e6);
    }

    function test_moveForZeroBalanceUserReverts() public {
        _delegate(bob, 10_000, 0);
        vm.expectRevert(abi.encodeWithSelector(AgentRouter.ExceedsCap.selector, 1e6, 0));
        _agentMove(bob, 1e6);
    }

    function test_moveForFullPositionWithCap10000() public {
        _mintAndDeposit(alice, floatingVault, 100e6);
        _delegate(alice, 10_000, 0);
        _agentMove(alice, router.assetsOf(alice, address(floatingVault)));
        assertEq(floatingVault.balanceOf(alice), 0);
    }

    function test_moveForEmitsByAgentTrue() public {
        _mintAndDeposit(alice, floatingVault, 100e6);
        _delegate(alice, 10_000, 0);
        vm.expectEmit(true, true, true, true, address(router));
        emit Moved(alice, address(floatingVault), address(fixedVault), 10e6, HASH, true);
        _agentMove(alice, 10e6);
    }

    function test_revokedAgentCannotMove() public {
        _mintAndDeposit(alice, floatingVault, 100e6);
        _delegate(alice, 10_000, 0);
        bytes32 agentRole = router.AGENT_ROLE();
        vm.prank(admin);
        router.revokeRole(agentRole, agent);
        vm.expectRevert(
            abi.encodeWithSelector(IAccessControl.AccessControlUnauthorizedAccount.selector, agent, agentRole)
        );
        _agentMove(alice, 1e6);
    }

    function test_moveForWhenPausedReverts() public {
        _mintAndDeposit(alice, floatingVault, 100e6);
        _delegate(alice, 10_000, 0);
        vm.prank(admin);
        router.pause();
        vm.expectRevert(Pausable.EnforcedPause.selector);
        _agentMove(alice, 1e6);
    }

    function test_moveForFromEmptyVaultReverts() public {
        _mintAndDeposit(alice, fixedVault, 100e6);
        _delegate(alice, 10_000, 1 hours);
        vm.expectRevert(AgentRouter.ZeroAssets.selector);
        _agentMove(alice, 1e6);
        (,,, uint64 lastMove) = router.policies(alice);
        assertEq(lastMove, 0);
    }

    function test_firstMoveIgnoresCooldown() public {
        _mintAndDeposit(alice, floatingVault, 100e6);
        _delegate(alice, 10_000, type(uint32).max);
        _agentMove(alice, 10e6);
        vm.expectRevert();
        _agentMove(alice, 10e6);
    }
}
