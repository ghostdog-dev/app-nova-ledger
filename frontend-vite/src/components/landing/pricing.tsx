import { Check } from 'lucide-react';
import { cn } from '@/lib/utils';
import styles from './pricing.module.css';
import { Link } from 'react-router-dom';

const plans = [
  {
    name: 'Starter',
    price: '€29',
    desc: 'For freelancers and small businesses.',
    features: ['Up to 500 transactions/mo', '2 Connections', 'Real-time Correlation', 'CSV Export'],
  },
  {
    name: 'Pro',
    price: '€79',
    desc: 'For growing companies with high volume.',
    features: ['Unlimited transactions', '10 Connections', 'Custom API Access', 'Priority Support', 'Audit Logs'],
  },
  {
    name: 'Enterprise',
    price: 'Custom',
    desc: 'For large organizations and groups.',
    features: ['Dedicated Instance', 'On-premise Options', 'White-glove Onboarding', 'SLA Guarantee', '24/7 Concierge'],
  },
];

export function Pricing() {
  return (
    <section id="pricing" className={styles.section}>
      <div className={styles.container}>
        <div className={styles.header}>
          <h2 className={styles.heading}>
            Simple <span className={styles.headingAccent}>pricing</span>.
          </h2>
          <p className={styles.subtitle}>Transparent pricing for transparent finances.</p>
        </div>

        <div className={styles.grid}>
          {plans.map((plan, i) => (
            <div
              key={i}
              className={cn(styles.card, i === 1 ? styles.cardDark : styles.cardLight)}
            >
              <div>
                <div className={styles.cardTop}>
                  <h3 className={styles.planName}>{plan.name}</h3>
                  {i === 1 && <span className={styles.recommendedBadge}>Recommended</span>}
                </div>
                <div className={styles.priceBlock}>
                  <span className={styles.price}>{plan.price}</span>
                  {plan.price !== 'Custom' && <span className={styles.pricePeriod}>/mo</span>}
                </div>
                <p className={styles.planDesc}>{plan.desc}</p>
                <ul className={styles.featureList}>
                  {plan.features.map((feat, j) => (
                    <li key={j} className={styles.featureItem}>
                      <Check size={14} className={i === 1 ? styles.checkIconDark : styles.checkIconLight} />
                      {feat}
                    </li>
                  ))}
                </ul>
              </div>
              <Link to="/register" className={cn(styles.button, i === 1 ? styles.buttonDark : styles.buttonLight)} style={{ textAlign: 'center' }}>
                Select {plan.name}
              </Link>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
