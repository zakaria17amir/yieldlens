// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import {Ownable} from "@openzeppelin/contracts/access/Ownable.sol";
import {Math} from "@openzeppelin/contracts/utils/math/Math.sol";
import {SafeERC20} from "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import {IYieldAdapter} from "./interfaces/IYieldAdapter.sol";
import {MockUSDG} from "./MockUSDG.sol";

contract MockYieldAdapter is IYieldAdapter, Ownable {
    using SafeERC20 for MockUSDG;

    error OnlyVault();
    error InvalidBps();

    event AprSet(uint256 aprBps);

    uint256 private constant BPS = 10_000;

    MockUSDG private immutable _asset;
    address private immutable _vault;
    uint256 private _aprBps;
    uint256 private _principal;
    uint256 private _lastAccrual;

    modifier onlyVault() {
        if (msg.sender != _vault) revert OnlyVault();
        _;
    }

    constructor(MockUSDG asset_, address vault_, uint256 aprBps_, address owner_) Ownable(owner_) {
        if (aprBps_ > BPS) revert InvalidBps();
        _asset = asset_;
        _vault = vault_;
        _aprBps = aprBps_;
        _lastAccrual = block.timestamp;
    }

    function asset() external view returns (address) {
        return address(_asset);
    }

    function vault() external view returns (address) {
        return _vault;
    }

    function aprBps() external view returns (uint256) {
        return _aprBps;
    }

    function principal() external view returns (uint256) {
        return _principal;
    }

    function setAprBps(uint256 newAprBps) external onlyOwner {
        if (newAprBps > BPS) revert InvalidBps();
        accrue();
        _aprBps = newAprBps;
        emit AprSet(newAprBps);
    }

    function totalAssets() public view returns (uint256) {
        return _principal + _pending();
    }

    function accrue() public {
        uint256 pending = _pending();
        _lastAccrual = block.timestamp;
        if (pending > 0) {
            _asset.mintYield(address(this), pending);
            _principal += pending;
        }
    }

    function deposit(uint256 assets) external onlyVault {
        accrue();
        _principal += assets;
        _asset.safeTransferFrom(_vault, address(this), assets);
    }

    function withdraw(uint256 assets, address to) external onlyVault {
        accrue();
        _principal -= assets;
        _asset.safeTransfer(to, assets);
    }

    function _pending() private view returns (uint256) {
        return Math.mulDiv(_principal, _aprBps * (block.timestamp - _lastAccrual), BPS * 365 days);
    }
}
