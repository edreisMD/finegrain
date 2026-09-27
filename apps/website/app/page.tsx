import GrainField from './grain-field';
import Architecture from './architecture';
import Image from 'next/image';
import Link from 'next/link';

const repository = 'https://github.com/edreisMD/finegrain';

export default function Home() {
  return (
    <>
      <a className="skip-link" href="#about">Skip to content</a>
      <header className="site-header shell">
        <Link className="brand" href="/" aria-label="GM home">
          <Image src="/gm-mark.svg" width={48} height={36} alt="GM monogram" unoptimized />
        </Link>
        <a className="header-link" href={repository}>GitHub ↗</a>
      </header>
      <main className="shell">
        <section className="hero" aria-labelledby="title">
          <h1 id="title">GM — your company’s learning loop</h1>
          <GrainField />
          <p className="hero-note">Your team learns.<br />Your company model learns with it.</p>
          <p className="edition">Open source · Self-hosted · Built on Gbrain + River</p>
        </section>
        <section className="section" id="about" aria-labelledby="about-title">
          <h2 id="about-title">[ About ]</h2>
          <p>Your team solves problems every day. The next agent session shouldn’t have to learn everything from scratch.</p>
          <p>GM turns the knowledge your company chooses to share into training data, small reinforcement learning tasks, and tests. Then it fine-tunes a company model through River, on your schedule.</p>
          <p>Gbrain keeps the facts. Your model learns the way you work: your conventions, your procedures, when to look something up, and when to say “I don’t know.”</p>
          <p><a href={repository}>Explore the repository ↗</a></p>
        </section>
        <section className="section" id="how-it-works" aria-labelledby="loop-title">
          <h2 id="loop-title">[ Three levels. One learning loop. ]</h2>
          <Architecture />
          <div className="cadence"><span>Your schedule</span><span>Nightly / weekly / monthly / manual</span></div>
        </section>
        <section className="section" id="start" aria-labelledby="start-title">
          <h2 id="start-title">[ Run it yourself ]</h2>
          <p>One repository. A companion for each teammate, and a company learning loop on your own server. Use Docker for the company stack, or connect GM to a Gbrain you already run.</p>
          <div className="terminal" aria-label="Clone GM and run the offline demo">
            <div className="terminal-label">Try the dataset demo · requires uv · no API key</div>
            <pre><code><span className="prompt">$ </span>git clone https://github.com/edreisMD/finegrain.git gm{'\n'}<span className="prompt">$ </span>cd gm{'\n'}<span className="prompt">$ </span>make setup &amp;&amp; make demo</code></pre>
          </div>
          <div className="install-row"><span>On each Mac</span><code>./scripts/install-employee.sh</code></div>
          <div className="install-row"><span>On the company host</span><code>./scripts/install-server.sh</code></div>
          <p className="setup-links"><a href={`${repository}#install-on-each-employees-mac`}>Mac setup ↗</a><a href={`${repository}#install-the-company-server`}>Company setup ↗</a><a href={`${repository}/blob/main/docs/DEMO.md`}>Demo guide ↗</a></p>
        </section>
        <section className="section last-section" aria-labelledby="open-title">
          <h2 id="open-title">[ Built in the open ]</h2>
          <p>Fork it. Run it with your team. Make it better.</p>
          <p>GM is an early, MIT-licensed framework. River is the first training provider; the provider interface leaves room for others. Gbrain remains the source of truth, with its existing personal and company setup.</p>
          <p className="status-note">The training loop is implemented. A completed live training benchmark is still pending. The included demo uses fictional company data.</p>
          <dl className="project-links">
            <div><dt>Code</dt><dd><a href={repository}>github.com/edreisMD/finegrain ↗</a></dd></div>
            <div><dt>Memory</dt><dd><a href="https://github.com/garrytan/gbrain">Gbrain ↗</a></dd></div>
            <div><dt>Training</dt><dd><a href="https://river.ai">River ↗</a></dd></div>
          </dl>
        </section>
      </main>
      <footer className="shell footer">
        <span>GM</span><a href={`${repository}/blob/main/LICENSE`}>MIT license ↗</a>
        <p>Built at the <a href="https://events.ycombinator.com/gbrain-qm-river-memorable-hackathon">Own Your Intelligence Hackathon</a>.</p>
      </footer>
    </>
  );
}
