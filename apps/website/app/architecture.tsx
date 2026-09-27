import { ArrowDown, ArrowRight, BrainCircuit, Check, Database, Laptop, LockKeyhole, RotateCcw, Workflow } from 'lucide-react';
import './architecture.css';

export default function Architecture() {
  return (
    <figure className="architecture" aria-label="Three levels of the GM learning loop">
      <div className="architecture-level">
        <header className="level-heading">
          <span className="level-index" aria-hidden="true">01</span>
          <h3>Your Mac</h3>
          <span className="level-location"><Laptop aria-hidden="true" /> Personal</span>
        </header>
        <div className="architecture-flow personal-flow">
          <div className="flow-node agents-node">
            <span className="node-label">Your agent sessions</span>
            <span className="agent-names">Claude <span>·</span> Codex <span>·</span> Pi</span>
          </div>
          <ArrowRight className="flow-arrow" aria-hidden="true" />
          <div className="flow-node emphasized-node">
            <BrainCircuit aria-hidden="true" />
            <div><strong>Personal Gbrain</strong><span>Compiled decisions &amp; conventions</span></div>
          </div>
        </div>
        <p className="level-note">Useful knowledge is compiled locally. Raw traces stay on your Mac.</p>
      </div>

      <div className="architecture-connector">
        <ArrowDown aria-hidden="true" />
        <span><LockKeyhole aria-hidden="true" /> Only approved, compiled notes</span>
      </div>

      <div className="architecture-level company-level">
        <header className="level-heading">
          <span className="level-index" aria-hidden="true">02</span>
          <h3>Your company brain</h3>
          <span className="level-location"><Database aria-hidden="true" /> Company host</span>
        </header>
        <div className="architecture-flow company-flow">
          <div className="flow-node"><strong>Company Gbrain</strong><span>Shared source of truth</span></div>
          <ArrowRight className="flow-arrow" aria-hidden="true" />
          <div className="flow-node"><strong>Dataset compiler</strong><span>River teacher + critic via API</span></div>
        </div>
        <div className="dataset-fork">
          <div><span className="dataset-dot" aria-hidden="true" /><strong>Training set</strong><span>SFT examples + RL tasks</span></div>
          <div><span className="dataset-dot test-dot" aria-hidden="true" /><strong>Held-out tests</strong><span>Separated before training</span></div>
        </div>
      </div>

      <div className="architecture-connector">
        <ArrowDown aria-hidden="true" />
        <span>Train remotely. Evaluate separately.</span>
      </div>

      <div className="architecture-level learning-level">
        <header className="level-heading">
          <span className="level-index" aria-hidden="true">03</span>
          <h3>Your company model</h3>
          <span className="level-location"><Workflow aria-hidden="true" /> Learning loop</span>
        </header>
        <div className="training-flow">
          <div className="training-step"><strong>SFT</strong><span>River</span></div>
          <ArrowRight aria-hidden="true" />
          <div className="training-step"><strong>Optional RL</strong><span>River</span></div>
          <ArrowRight aria-hidden="true" />
          <div className="training-step"><strong>Evaluate</strong><span>Company host</span></div>
        </div>
        <div className="promotion-gate">
          <span className="gate-label">Promotion gate</span>
          <div><span><Check aria-hidden="true" /> Pass: promote candidate</span><span><RotateCcw aria-hidden="true" /> Fail: keep current model</span></div>
        </div>
        <p className="level-note">Test recall, procedures, changed facts, and when to abstain.</p>
      </div>
      <figcaption>Gbrain keeps the facts. The model learns how your company works.</figcaption>
    </figure>
  );
}
