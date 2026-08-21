import clsx from 'clsx';
import Link from '@docusaurus/Link';
import useDocusaurusContext from '@docusaurus/useDocusaurusContext';
import useBaseUrl from '@docusaurus/useBaseUrl';
import Layout from '@theme/Layout';
import HomepageFeatures from '@site/src/components/HomepageFeatures';

import Heading from '@theme/Heading';
import styles from './index.module.css';

function HomepageArchitecture() {
  return (
    <section className={styles.architecture}>
      <div className="container">
        <Heading as="h2">System Architecture</Heading>
        <img
          className={styles.architectureImage}
          src={useBaseUrl('/img/architecture.png')}
          alt="TaskSAT verification pipeline: TaskNet spec → Parser → AST → Transformations → Wellformedness Checker → SMT Encoder → Z3 Formula → Z3 Solver → Schedule/UNSAT"
        />
        <p className={styles.architectureCaption}>
          The TaskSAT verification pipeline: a TaskNet specification is parsed,
          transformed, checked for wellformedness, encoded into SMT, and solved
          with Z3 to produce a schedule or an UNSAT result.
        </p>
      </div>
    </section>
  );
}

function HomepageHeader() {
  const {siteConfig} = useDocusaurusContext();
  return (
    <header className={clsx('hero hero--primary', styles.heroBanner)}>
      <div className="container">
        <Heading as="h1" className="hero__title">
          {siteConfig.title}
        </Heading>
        <p className="hero__subtitle">{siteConfig.tagline}</p>
        <div className={styles.buttons}>
          <Link
            className="button button--secondary button--lg"
            to="/docs/getting-started">
            Get Started →
          </Link>
        </div>
      </div>
    </header>
  );
}

export default function Home() {
  const {siteConfig} = useDocusaurusContext();
  return (
    <Layout
      title={siteConfig.title}
      description="A DSL and SMT-based verifier for task scheduling with temporal and resource constraints">
      <HomepageHeader />
      <main>
        <HomepageFeatures />
        <HomepageArchitecture />
      </main>
    </Layout>
  );
}
