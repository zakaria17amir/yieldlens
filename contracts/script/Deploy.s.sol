// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import {Script} from "forge-std/Script.sol";
import {VmSafe} from "forge-std/Vm.sol";
import {MockUSDG} from "../src/MockUSDG.sol";
import {MockYieldAdapter} from "../src/MockYieldAdapter.sol";
import {StrategyVault} from "../src/StrategyVault.sol";
import {AgentRouter} from "../src/AgentRouter.sol";

contract Deploy is Script {
    string internal constant OUT_PATH = "deployments/arbitrum-sepolia.json";

    function run() external {
        uint256 deployerKey = vm.envUint("DEPLOYER_PRIVATE_KEY");
        address agentAddress = vm.envAddress("AGENT_ADDRESS");
        address deployer = vm.addr(deployerKey);

        vm.startBroadcast(deployerKey);
        MockUSDG usdg = new MockUSDG();
        StrategyVault fixedVault = new StrategyVault(usdg, "YieldLens Fixed USDG", "ylFIX", deployer);
        StrategyVault floatingVault = new StrategyVault(usdg, "YieldLens Floating USDG", "ylFLT", deployer);
        MockYieldAdapter fixedAdapter = new MockYieldAdapter(usdg, address(fixedVault), 1000, deployer);
        MockYieldAdapter floatingAdapter = new MockYieldAdapter(usdg, address(floatingVault), 2000, deployer);
        usdg.setMinter(address(fixedAdapter), true);
        usdg.setMinter(address(floatingAdapter), true);
        fixedVault.setAdapter(fixedAdapter);
        floatingVault.setAdapter(floatingAdapter);
        AgentRouter router = new AgentRouter(deployer);
        router.setVaults(address(fixedVault), address(floatingVault));
        router.grantRole(router.AGENT_ROLE(), agentAddress);
        usdg.mint(deployer, 1_000_000e6);
        vm.stopBroadcast();

        if (!vm.isContext(VmSafe.ForgeContext.ScriptBroadcast)) return;

        string memory key = "deployment";
        vm.serializeUint(key, "chainId", block.chainid);
        // block before the deploy transactions; safe as a log fromBlock
        vm.serializeUint(key, "deployedAtBlock", block.number);
        vm.serializeAddress(key, "usdg", address(usdg));
        vm.serializeAddress(key, "fixedVault", address(fixedVault));
        vm.serializeAddress(key, "floatingVault", address(floatingVault));
        vm.serializeAddress(key, "fixedAdapter", address(fixedAdapter));
        vm.serializeAddress(key, "floatingAdapter", address(floatingAdapter));
        string memory json = vm.serializeAddress(key, "router", address(router));
        vm.writeJson(json, OUT_PATH);
    }
}
