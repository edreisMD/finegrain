import GrainField from './grain-field';
import Image from 'next/image';
import Link from 'next/link';

const repository = 'https://github.com/arav-rithvik/gm';

export default function Home() {
  return (
    <>
      <a className="skip-link" href="#about">Skip to content</a>
      <header className="site-header shell">
        <Link className="brand" href="/" aria-label="GM Nightly Loop home">
          <Image src="/coffee-bean.jpeg" width={32} height={32} alt="GM mark" unoptimized />
        </Link>
        <a className="header-link" href={repository}>GitHub ↗</a>
      </header>
      <main className="shell">
        <section className="hero" aria-labelledby="title">
          <h1 id="title">GM Nightly Loop</h1>
          <GrainField />
          <p className="hero-note">GBrain gets better the more it’s used.<br />Every correction your team makes becomes training data, and GM improves overnight.</p>
          <p className="edition">Open source · Self-hosted · Built on Gbrain + River</p>
        </section>
        <section className="section" id="about" aria-labelledby="about-title">
          <h2 id="about-title">[ About ]</h2>
          <p>Your team solves problems every day. The next agent session shouldn’t have to learn everything from scratch.</p>
          <p>GM Nightly Loop is Part 2 of GM. It turns the knowledge your company chooses to share into training data, small reinforcement learning tasks, and tests. Then it fine-tunes from the Part 1 GM checkpoint through River, on your schedule.</p>
          <p>Gbrain keeps the facts. Your model learns the way you work: your conventions, your procedures, when to look something up, and when to say “I don’t know.”</p>
          <p><a href={repository}>Explore the repository ↗</a></p>
        </section>
        <section className="section" id="how-it-works" aria-labelledby="loop-title">
          <h2 id="loop-title">[ From daily work to better models ]</h2>
          <ol className="steps">
            <li><span className="step-number">01</span><div><h3>Remember locally.</h3><p>A Mac menu-bar companion reads sessions from Claude, Codex, Pi, and other agents. Selected decisions and conventions are compiled into your normal personal Gbrain.</p></div></li>
            <li><span className="step-number">02</span><div><h3>Share what belongs to the company.</h3><p>Approved, compiled notes travel to the official company Gbrain. The relay leaves raw session traces on the Mac and uses Gbrain’s own access controls.</p></div></li>
            <li><span className="step-number">03</span><div><h3>Turn knowledge into a curriculum.</h3><p>A River teacher and independent critic create grounded examples and verifiable tasks. Separate tests check recall, company procedures, changed facts, and knowing when to abstain.</p></div></li>
            <li><span className="step-number">04</span><div><h3>Train. Test. Earn the upgrade.</h3><p>Run supervised fine-tuning and optional reinforcement learning remotely on River. A candidate becomes the current model only if it passes the improvement and regression checks.</p></div></li>
          </ol>
          <div className="cadence"><span>Your schedule</span><span>Nightly / weekly / monthly / manual</span></div>
        </section>
        <section className="section" id="start" aria-labelledby="start-title">
          <h2 id="start-title">[ Run it yourself ]</h2>
          <p>One GM repository. A companion for each teammate, and a company learning loop on your own server. Use Docker for the company stack, or connect GM Nightly Loop to a Gbrain you already run.</p>
          <div className="terminal" aria-label="Clone GM and run the offline Part 2 demo">
            <div className="terminal-label">Try the dataset demo · requires uv · no API key</div>
            <pre><code><span className="prompt">$ </span>git clone https://github.com/arav-rithvik/gm.git{'\n'}<span className="prompt">$ </span>cd gm{'\n'}<span className="prompt">$ </span>make part2-setup &amp;&amp; make part2-demo</code></pre>
          </div>
          <div className="install-row"><span>On each Mac</span><code>./scripts/install-employee.sh</code></div>
          <div className="install-row"><span>On the company host</span><code>./scripts/install-server.sh</code></div>
          <p className="setup-links"><a href={`${repository}#install-on-each-employees-mac`}>Mac setup ↗</a><a href={`${repository}#install-the-company-server`}>Company setup ↗</a><a href={`${repository}/blob/main/docs/DEMO.md`}>Demo guide ↗</a></p>
        </section>
        <section className="section last-section" aria-labelledby="open-title">
          <h2 id="open-title">[ Built in the open ]</h2>
          <p>Fork it. Run it with your team. Make it better.</p>
          <p>GM Nightly Loop is an early, MIT-licensed framework. River is the first training provider; the provider interface leaves room for others. Gbrain remains the source of truth, with its existing personal and company setup.</p>
          <p className="status-note">The training loop is implemented. A completed live training benchmark is still pending. The included demo uses fictional company data.</p>
          <dl className="project-links">
            <div><dt>Code</dt><dd><a href={repository}>github.com/arav-rithvik/gm ↗</a></dd></div>
            <div><dt>Memory</dt><dd><a href="https://github.com/garrytan/gbrain">Gbrain ↗</a></dd></div>
            <div><dt>Training</dt><dd><a href="https://river.ai">River ↗</a></dd></div>
          </dl>
        </section>
      </main>
      <footer className="shell footer">
        <span>GM Nightly Loop</span><a href={`${repository}/blob/main/LICENSE`}>MIT license ↗</a>
        <p>Built at the <a href="https://events.ycombinator.com/gbrain-qm-river-memorable-hackathon">Own Your Intelligence Hackathon</a>.</p>
      </footer>
    </>
  );
}
