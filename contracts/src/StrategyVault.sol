// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import {ERC4626, ERC20, IERC20} from "@openzeppelin/contracts/token/ERC20/extensions/ERC4626.sol";
import {SafeERC20} from "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import {ReentrancyGuard} from "@openzeppelin/contracts/utils/ReentrancyGuard.sol";
import {Ownable} from "@openzeppelin/contracts/access/Ownable.sol";
import {IYieldAdapter} from "./interfaces/IYieldAdapter.sol";

contract StrategyVault is ERC4626, Ownable, ReentrancyGuard {
    using SafeERC20 for IERC20;

    error AdapterAlreadySet();
    error AdapterNotSet();
    error AdapterAssetMismatch();
    error AdapterVaultMismatch();

    event AdapterSet(address indexed adapter);

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
        if (adapter_.vault() != address(this)) revert AdapterVaultMismatch();
        _adapter = adapter_;
        emit AdapterSet(address(adapter_));
    }

    function totalAssets() public view override returns (uint256) {
        IYieldAdapter a = _adapter;
        return address(a) == address(0) ? 0 : a.totalAssets();
    }

    function deposit(uint256 assets, address receiver) public virtual override nonReentrant returns (uint256) {
        return super.deposit(assets, receiver);
    }

    function mint(uint256 shares, address receiver) public virtual override nonReentrant returns (uint256) {
        return super.mint(shares, receiver);
    }

    function withdraw(uint256 assets, address receiver, address owner_)
        public
        virtual
        override
        nonReentrant
        returns (uint256)
    {
        return super.withdraw(assets, receiver, owner_);
    }

    function redeem(uint256 shares, address receiver, address owner_)
        public
        virtual
        override
        nonReentrant
        returns (uint256)
    {
        return super.redeem(shares, receiver, owner_);
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
