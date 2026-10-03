// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import {AccessControl} from "@openzeppelin/contracts/access/AccessControl.sol";
import {Pausable} from "@openzeppelin/contracts/utils/Pausable.sol";
import {ReentrancyGuard} from "@openzeppelin/contracts/utils/ReentrancyGuard.sol";
import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {IERC4626} from "@openzeppelin/contracts/interfaces/IERC4626.sol";
import {SafeERC20} from "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";

contract AgentRouter is AccessControl, Pausable, ReentrancyGuard {
    using SafeERC20 for IERC20;

    struct Policy {
        bool enabled;
        uint16 maxMoveBps;
        uint32 cooldown;
        uint64 lastMove;
    }

    bytes32 public constant AGENT_ROLE = keccak256("AGENT_ROLE");

    error NotAllowedVault(address vault);
    error SameVault();
    error InvalidBps();
    error ZeroAssets();
    error ZeroAddress();
    error VaultsAlreadySet();
    error ZeroShares();
    error AssetMismatch();
    error PolicyDisabled(address user);
    error CooldownActive(uint64 availableAt);
    error ExceedsCap(uint256 assets, uint256 cap);

    event PolicySet(address indexed user, bool enabled, uint16 maxMoveBps, uint32 cooldown);
    event VaultsSet(address indexed fixedVault, address indexed floatingVault);
    event Moved(
        address indexed user,
        address indexed fromVault,
        address indexed toVault,
        uint256 assets,
        bytes32 reportHash,
        bool byAgent
    );

    address public fixedVault;
    address public floatingVault;
    mapping(address => Policy) public policies;

    constructor(address admin) {
        if (admin == address(0)) revert ZeroAddress();
        _grantRole(DEFAULT_ADMIN_ROLE, admin);
    }

    /// @notice Sets the vault pair once. To migrate, deploy a new router.
    /// @dev The admin is trusted (pause, agent role, one-time vault pair) but cannot re-point an existing
    /// router; use a multisig as admin in production.
    function setVaults(address fixedVault_, address floatingVault_) external onlyRole(DEFAULT_ADMIN_ROLE) {
        if (fixedVault != address(0)) revert VaultsAlreadySet();
        if (fixedVault_ == address(0) || floatingVault_ == address(0)) revert ZeroAddress();
        if (fixedVault_ == floatingVault_) revert SameVault();
        if (IERC4626(fixedVault_).asset() != IERC4626(floatingVault_).asset()) revert AssetMismatch();
        fixedVault = fixedVault_;
        floatingVault = floatingVault_;
        emit VaultsSet(fixedVault_, floatingVault_);
    }

    function pause() external onlyRole(DEFAULT_ADMIN_ROLE) {
        _pause();
    }

    function unpause() external onlyRole(DEFAULT_ADMIN_ROLE) {
        _unpause();
    }

    function setPolicy(bool enabled, uint16 maxMoveBps, uint32 cooldown) external {
        if (maxMoveBps > 10_000) revert InvalidBps();
        Policy storage p = policies[msg.sender];
        p.enabled = enabled;
        p.maxMoveBps = maxMoveBps;
        p.cooldown = cooldown;
        emit PolicySet(msg.sender, enabled, maxMoveBps, cooldown);
    }

    function assetsOf(address user, address vault) public view returns (uint256) {
        IERC4626 v = IERC4626(vault);
        return v.convertToAssets(v.balanceOf(user));
    }

    function userTotalAssets(address user) public view returns (uint256) {
        return assetsOf(user, fixedVault) + assetsOf(user, floatingVault);
    }

    function moveSelf(address fromVault, address toVault, uint256 assets, bytes32 reportHash)
        external
        nonReentrant
        whenNotPaused
    {
        _move(msg.sender, fromVault, toVault, assets, reportHash, false);
    }

    function moveFor(address user, address fromVault, address toVault, uint256 assets, bytes32 reportHash)
        external
        onlyRole(AGENT_ROLE)
        whenNotPaused
        nonReentrant
    {
        _requireVaults(fromVault, toVault);
        Policy memory p = policies[user];
        if (!p.enabled) revert PolicyDisabled(user);
        uint64 availableAt = p.lastMove + p.cooldown;
        if (p.lastMove != 0 && block.timestamp < availableAt) revert CooldownActive(availableAt);
        uint256 cap = userTotalAssets(user) * p.maxMoveBps / 10_000;
        if (assets > cap) revert ExceedsCap(assets, cap);

        policies[user].lastMove = uint64(block.timestamp);
        _move(user, fromVault, toVault, assets, reportHash, true);
    }

    function _requireVaults(address from, address to) private view {
        if (!_isVault(from)) revert NotAllowedVault(from);
        if (!_isVault(to)) revert NotAllowedVault(to);
        if (from == to) revert SameVault();
    }

    function _isVault(address vault) private view returns (bool) {
        return vault != address(0) && (vault == fixedVault || vault == floatingVault);
    }

    function _move(address user, address from, address to, uint256 assets, bytes32 reportHash, bool byAgent) internal {
        _requireVaults(from, to);
        if (assets == 0) revert ZeroAssets();

        IERC20 token = IERC20(IERC4626(from).asset());
        uint256 before = token.balanceOf(address(this));
        if (assets >= assetsOf(user, from)) {
            IERC4626(from).redeem(IERC4626(from).balanceOf(user), address(this), user);
        } else {
            IERC4626(from).withdraw(assets, address(this), user);
        }
        uint256 received = token.balanceOf(address(this)) - before;
        if (received == 0) revert ZeroAssets();

        token.forceApprove(to, received);
        if (IERC4626(to).deposit(received, user) == 0) revert ZeroShares();

        emit Moved(user, from, to, received, reportHash, byAgent);
    }
}
