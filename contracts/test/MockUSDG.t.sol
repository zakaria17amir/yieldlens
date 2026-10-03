// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import {Test} from "forge-std/Test.sol";
import {MockUSDG} from "../src/MockUSDG.sol";

contract MockUSDGTest is Test {
    function test_setMinterOnlyOwner() public {
        MockUSDG usdg = new MockUSDG();
        vm.prank(address(0xBAD));
        vm.expectRevert();
        usdg.setMinter(address(0xBAD), true);
        usdg.setMinter(address(0xBEEF), true);
        assertTrue(usdg.minters(address(0xBEEF)));
    }

    function test_mintStillCapped() public {
        MockUSDG usdg = new MockUSDG();
        usdg.mint(address(this), usdg.MAX_MINT());
        assertEq(usdg.balanceOf(address(this)), usdg.MAX_MINT());
        uint256 tooMuch = usdg.MAX_MINT() + 1;
        vm.expectRevert(MockUSDG.MintTooLarge.selector);
        usdg.mint(address(this), tooMuch);
    }
}
