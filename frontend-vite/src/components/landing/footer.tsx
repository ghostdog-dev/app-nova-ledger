import { ArrowRight, Twitter, Linkedin, Github } from 'lucide-react';
import styles from './footer.module.css';
import { Link } from 'react-router-dom';

export function Footer() {
  return (
    <footer className={styles.footer}>
      <div className={styles.ctaSection}>
        <div className={styles.ctaInner}>
          <h2 className={styles.ctaHeading}>
            Finalize your <br /> <span className={styles.ctaAccent}>ledger</span>.
          </h2>
          <p className={styles.ctaDesc}>
            Stop guessing. Start knowing. Join financial controllers who have
            chosen clarity over chaos.
          </p>
          <Link to="/register" className={styles.ctaButton}>
            <span className={styles.ctaButtonText}>Start 14-Day Trial</span>
            <ArrowRight size={16} className={styles.ctaButtonIcon} />
          </Link>
        </div>
      </div>

      <div className={styles.linksSection}>
        <div className={styles.brandBlock}>
          <div className={styles.brandRow}>
            <div className={styles.brandDot} />
            <span className={styles.brandName}>Nova Ledger</span>
          </div>
          <p className={styles.brandDesc}>
            Automated financial reconciliation powered by AI.
          </p>
        </div>
        <div>
          <h4 className={styles.linkGroupTitle}>Product</h4>
          <ul className={styles.linkList}>
            <li><a href="#methodology" className={styles.linkItem}>Methodology</a></li>
            <li><a href="#features" className={styles.linkItem}>Features</a></li>
            <li><a href="#pricing" className={styles.linkItem}>Pricing</a></li>
            <li><Link to="/login" className={styles.linkItem}>Sign In</Link></li>
          </ul>
        </div>
        <div>
          <h4 className={styles.linkGroupTitle}>Company</h4>
          <ul className={styles.linkList}>
            <li><a href="#" className={styles.linkItem}>About</a></li>
            <li><a href="#" className={styles.linkItem}>Legal</a></li>
            <li><a href="#" className={styles.linkItem}>Privacy</a></li>
            <li><a href="#" className={styles.linkItem}>Contact</a></li>
          </ul>
        </div>
        <div>
          <h4 className={styles.linkGroupTitle}>Social</h4>
          <div className={styles.socialLinks}>
            <a href="#" className={styles.socialLink}><Twitter size={16} /></a>
            <a href="#" className={styles.socialLink}><Linkedin size={16} /></a>
            <a href="#" className={styles.socialLink}><Github size={16} /></a>
          </div>
        </div>
      </div>

      <div className={styles.bottomBar}>
        <div className={styles.bottomBarInner}>
          <span>&copy; {new Date().getFullYear()} Nova Ledger. All rights reserved.</span>
          <span className={styles.statusText}>System Status: Operational</span>
        </div>
      </div>
    </footer>
  );
}
