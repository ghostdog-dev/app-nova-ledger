import { Menu, X } from 'lucide-react';
import { useState, useEffect } from 'react';
import { cn } from '@/lib/utils';
import styles from './navbar.module.css';
import { Link } from 'react-router-dom';

const navItems = [
  { label: 'Methodology', href: '#methodology' },
  { label: 'Features', href: '#features' },
  { label: 'Preview', href: '#preview' },
  { label: 'Pricing', href: '#pricing' },
];

export function Navbar() {
  const [isOpen, setIsOpen] = useState(false);
  const [isScrolled, setIsScrolled] = useState(false);

  useEffect(() => {
    const handleScroll = () => setIsScrolled(window.scrollY > 50);
    window.addEventListener('scroll', handleScroll);
    return () => window.removeEventListener('scroll', handleScroll);
  }, []);

  return (
    <nav className={cn(styles.nav, { [styles.navScrolled]: isScrolled })}>
      <div className={styles.navInner}>
        <div className={styles.logoWrap}>
          <div className={styles.logoIcon}>
            <div className={styles.logoIconDot} />
          </div>
          <span className={styles.logoText}>Nova Ledger</span>
        </div>

        <div className={styles.desktopMenu}>
          {navItems.map((item) => (
            <a key={item.label} href={item.href} className={styles.navLink}>
              {item.label}
            </a>
          ))}
          <Link to="/register" className={styles.navCta}>
            Start Free
          </Link>
        </div>

        <button className={styles.mobileToggle} onClick={() => setIsOpen(!isOpen)}>
          {isOpen ? <X /> : <Menu />}
        </button>
      </div>

      {isOpen && (
        <div className={styles.mobileMenu}>
          {navItems.map((item) => (
            <a
              key={item.label}
              href={item.href}
              className={styles.mobileLink}
              onClick={() => setIsOpen(false)}
            >
              {item.label}
            </a>
          ))}
          <Link to="/register" className={styles.mobileCta} onClick={() => setIsOpen(false)}>
            Start Free
          </Link>
        </div>
      )}
    </nav>
  );
}
