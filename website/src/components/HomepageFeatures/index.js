import clsx from 'clsx';
import Heading from '@theme/Heading';
import styles from './styles.module.css';

const FeatureList = [
  {
    title: 'Declarative Scheduling DSL',
    description: (
      <>
        Model tasks, timelines, and rich temporal and resource constraints in a
        concise domain-specific language designed to mirror MEXEC tasknet
        concepts.
      </>
    ),
  },
  {
    title: 'SMT-Based Verification',
    description: (
      <>
        Specifications are encoded into quantifier-free SMT using zone-based time
        discretization and solved with Z3 — supporting satisfiability checking
        and optimization.
      </>
    ),
  },
  {
    title: 'Temporal Properties',
    description: (
      <>
        Express LTL-style properties (always, eventually, until, since) and
        final-state constraints, verified alongside scheduling with clear
        counterexample traces.
      </>
    ),
  },
];

function Feature({title, description}) {
  return (
    <div className={clsx('col col--4')}>
      <div className="text--center padding-horiz--md">
        <Heading as="h3">{title}</Heading>
        <p>{description}</p>
      </div>
    </div>
  );
}

export default function HomepageFeatures() {
  return (
    <section className={styles.features}>
      <div className="container">
        <div className="row">
          {FeatureList.map((props, idx) => (
            <Feature key={idx} {...props} />
          ))}
        </div>
      </div>
    </section>
  );
}
