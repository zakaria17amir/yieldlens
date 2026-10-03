// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import {ERC4626, ERC20, IERC20} from "@openzeppelin/contracts/token/ERC20/extensions/ERC4626.sol";
import {SafeERC20} from "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import {Ownable} from "@openzeppelin/contracts/access/Ownable.sol";
import {IYieldAdapter} from "./interfaces/IYieldAdapter.sol";

contract StrategyVault is ERC4626, Ownable {
    using SafeERC20 for IERC20;

    error AdapterAlreadySet();
    error AdapterNotSet();
    error AdapterAssetMismatch();

    IYieldAdapter private _adapter;

    constructor(IERC20 asset_, string memory name_, string memory symbol_, address owner_)
        ERC20(name_, symbol_)
        ERC4626(asset_)
        Ownable(owner_)
    {}

    function adapter() external view returns (IYieldAdapter) {
        return _adapter;
    }

    function setAdapter(IYieldAdapter adapter_) external onlyOwner {
        if (address(_adapter) != address(0)) revert AdapterAlreadySet();
        if (adapter_.asset() != asset()) revert AdapterAssetMismatch();
        _adapter = adapter_;
    }

    function totalAssets() public view override returns (uint256) {
        IYieldAdapter a = _adapter;
        return address(a) == address(0) ? 0 : a.totalAssets();
    }

    function _decimalsOffset() internal pure override returns (uint8) {
        return 3;
    }

    function _deposit(address caller, address receiver, uint256 assets, uint256 shares) internal override {
        IYieldAdapter a = _requireAdapter();
        super._deposit(caller, receiver, assets, shares);
        IERC20(asset()).forceApprove(address(a), assets);
        a.deposit(assets);
    }

    function _withdraw(address caller, address receiver, address owner_, uint256 assets, uint256 shares)
        internal
        override
    {
        _requireAdapter().withdraw(assets, address(this));
        super._withdraw(caller, receiver, owner_, assets, shares);
    }

    function _requireAdapter() private view returns (IYieldAdapter a) {
        a = _adapter;
        if (address(a) == address(0)) revert AdapterNotSet();
    }
}
