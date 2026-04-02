import styles from './social-proof.module.css';

const clients = [
  'Pennylane', 'Stripe', 'Sellsy', 'Evoliz', 'Axonaut',
  'GoCardless', 'Fintecture', 'Wise', 'Qonto',
];

export function SocialProof() {
  return (
    <section className={styles.section}>
      <div className={styles.track}>
        <div className={styles.marquee}>
          {[...clients, ...clients].map((client, i) => (
            <span key={i} className={styles.client}>{client}</span>
          ))}
        </div>
        <div className={styles.marquee} aria-hidden="true">
          {[...clients, ...clients].map((client, i) => (
            <span key={i} className={styles.client}>{client}</span>
          ))}
        </div>
      </div>
    </section>
  );
}
