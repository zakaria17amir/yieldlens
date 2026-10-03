#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p deployments/abi
for c in MockUSDG StrategyVault AgentRouter MockYieldAdapter; do
  forge inspect "$c" abi --json > "deployments/abi/$c.json"
done
