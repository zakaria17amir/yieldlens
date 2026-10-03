import { ConnectButton } from "@rainbow-me/rainbowkit";
import DeskPanel from "./components/DeskPanel";
import PositionPanel from "./components/PositionPanel";
import { isDeployed } from "./contracts";
import { activeChain } from "./wagmi";

export default function App() {
  return (
    <div className="app">
      <header className="header">
        <h1>YieldLens</h1>
        <span className="badge">{activeChain.name}</span>
        <div className="spacer" />
        <ConnectButton showBalance={false} />
      </header>
      {!isDeployed && (
        <div className="banner" role="alert">
          Contracts not deployed yet — showing placeholders until
          <code> contracts/deployments/arbitrum-sepolia.json </code> exists.
        </div>
      )}
      <main>
        <PositionPanel />
        <DeskPanel />
        <section className="panel">
          <h2>Track record</h2>
          <p className="muted">Fix-or-float performance appears here.</p>
        </section>
      </main>
    </div>
  );
}
