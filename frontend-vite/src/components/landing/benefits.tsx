import { Eye, TrendingUp, Clock, ShieldCheck, FileText, Zap } from 'lucide-react';
import styles from './benefits.module.css';

const benefits = [
  { icon: Eye, title: 'Visual Clarity', desc: 'Dashboards that respect your intelligence. Clean lines, zero clutter, pure signal.' },
  { icon: TrendingUp, title: 'Instant Correlation', desc: 'Every transaction matched to its source document in <0.2s. 99.9% accuracy.' },
  { icon: Clock, title: 'Time Recaptured', desc: 'Save an average of 14 hours per week on manual reconciliation.' },
  { icon: ShieldCheck, title: 'Audit Proof', desc: 'Every data point is traceable to its origin. Sleep soundly during tax season.' },
  { icon: FileText, title: 'Elegant Reports', desc: 'Generate PDFs that look like they were designed by a Swiss typographer.' },
  { icon: Zap, title: 'Live Sync', desc: 'Real-time connections to Pennylane, Stripe, Sellsy, Evoliz, and more.' },
];

export function Benefits() {
  return (
    <section className={styles.section}>
      <div className={styles.container}>
        <div className={styles.header}>
          <h2 className={styles.heading}>
            Engineered for <span className={styles.headingAccent}>precision</span>.
          </h2>
        </div>
        <div className={styles.featureGrid}>
          {benefits.map((benefit, i) => (
            <div
              key={i}
              className={styles.card}
            >
              <div className={styles.iconBox}>
                <benefit.icon className={styles.icon} strokeWidth={1.5} />
              </div>
              <div>
                <h3 className={styles.title}>{benefit.title}</h3>
                <p className={styles.desc}>{benefit.desc}</p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
