// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import {ERC20} from "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import {Ownable} from "@openzeppelin/contracts/access/Ownable.sol";

contract MockUSDG is ERC20, Ownable {
    error MintTooLarge();
    error NotMinter();

    event MinterSet(address indexed minter, bool allowed);

    uint256 public constant MAX_MINT = 10_000_000e6;

    mapping(address => bool) public minters;

    constructor() ERC20("Global Dollar", "USDG") Ownable(msg.sender) {}

    function setMinter(address minter, bool allowed) external onlyOwner {
        minters[minter] = allowed;
        emit MinterSet(minter, allowed);
    }

    function decimals() public pure override returns (uint8) {
        return 6;
    }

    function mint(address to, uint256 amount) external {
        if (amount > MAX_MINT) revert MintTooLarge();
        _mint(to, amount);
    }

    function mintYield(address to, uint256 amount) external {
        if (!minters[msg.sender]) revert NotMinter();
        _mint(to, amount);
    }
}
