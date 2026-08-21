import clsx from 'clsx';
import Heading from '@theme/Heading';
import styles from './styles.module.css';

const FeatureList = [
  {
    title: 'Rich State Modeling',
    description: (
      <>
        Model discrete states, Boolean flags, and continuous resources with
        rate-based evolution. Tasks specify preconditions, invariants,
        postconditions, and resource impacts at boundaries or during execution.
      </>
    ),
  },
  {
    title: 'Property Verification',
    description: (
      <>
        Express LTL-style temporal properties (always, eventually, until, since)
        that are verified alongside scheduling — with comprehensive error traces
        and violation zone identification for violated properties.
      </>
    ),
  },
  {
    title: 'SMT-Based Reasoning & Optimization',
    description: (
      <>
        Specifications are encoded into quantifier-free SMT using zone-based time
        discretization and solved with Z3, supporting both satisfiability
        checking and optimization of scheduling objectives.
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
