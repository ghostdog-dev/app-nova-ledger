import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Building2, Check, ChevronDown, Plus, Loader2 } from 'lucide-react';
import { clsx } from 'clsx';
import { useCompanyStore } from '@/stores/company-store';
import type { Company, PlanType } from '@/types';
import styles from './company-switcher.module.css';
import { useNavigate } from 'react-router-dom';

const PLAN_BADGE_CLASS: Record<PlanType, string> = {
  free: styles.badgeFree,
  plan1: styles.badgePlan1,
  plan2: styles.badgePlan2,
};

const PLAN_LABEL: Record<PlanType, string> = {
  free: 'Free',
  plan1: 'Plan 1',
  plan2: 'Plan 2',
};

function PlanBadge({ plan }: { plan: PlanType }) {
  return (
    <span className={clsx(styles.badge, PLAN_BADGE_CLASS[plan])}>
      {PLAN_LABEL[plan]}
    </span>
  );
}

export function CompanySwitcher() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { companies, activeCompany, isLoading, fetchCompanies, switchCompany } = useCompanyStore();
  const [open, setOpen] = useState(false);

  useEffect(() => {
    fetchCompanies();
  }, [fetchCompanies]);

  const handleSwitch = async (company: Company) => {
    setOpen(false);
    if (company.publicId === activeCompany?.publicId) return;
    await switchCompany(company);
  };

  const displayName = activeCompany?.name ?? t('company.switcher');

  return (
    <div className={styles.relative}>
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className={styles.trigger}
        aria-expanded={open}
        aria-haspopup="listbox"
        aria-label={t('company.switcher')}
      >
        {isLoading ? (
          <Loader2 className={clsx(styles.triggerIcon, styles.triggerIconSpin)} />
        ) : (
          <Building2 className={styles.triggerIcon} aria-hidden="true" />
        )}
        <span className={styles.triggerName}>{displayName}</span>
        {activeCompany && (
          <PlanBadge plan={activeCompany.plan} />
        )}
        <ChevronDown className={styles.triggerChevron} aria-hidden="true" />
      </button>

      {open && (
        <>
          <div
            className={styles.overlay}
            onClick={() => setOpen(false)}
            aria-hidden="true"
          />
          <div
            className={styles.dropdown}
            role="listbox"
            aria-label={t('company.switcher')}
          >
            {/* Company list */}
            {companies.length === 0 ? (
              <p className={styles.emptyText}>{t('company.noCompanies')}</p>
            ) : (
              companies.map((company) => {
                const isActive = company.publicId === activeCompany?.publicId;
                return (
                  <button
                    key={company.publicId}
                    type="button"
                    role="option"
                    aria-selected={isActive}
                    onClick={() => handleSwitch(company)}
                    className={clsx(
                      styles.companyOption,
                      isActive && styles.companyOptionActive
                    )}
                  >
                    <div
                      className={clsx(
                        styles.companyInitials,
                        isActive && styles.companyInitialsActive
                      )}
                    >
                      {company.name.slice(0, 2).toUpperCase()}
                    </div>
                    <div className={styles.companyInfo}>
                      <p className={clsx(styles.companyName, isActive && styles.companyNameActive)}>
                        {company.name}
                      </p>
                    </div>
                    <PlanBadge plan={company.plan} />
                    {isActive && <Check className={styles.checkIcon} aria-hidden="true" />}
                  </button>
                );
              })
            )}

            {/* Divider + actions */}
            <div className={styles.divider} />
            <button
              type="button"
              onClick={() => {
                setOpen(false);
                navigate('/settings/company?create=1');
              }}
              className={styles.actionBtn}
            >
              <span className={styles.addIcon}>
                <Plus className={styles.addIconInner} aria-hidden="true" />
              </span>
              {t('company.create')}
            </button>
            <button
              type="button"
              onClick={() => { setOpen(false); navigate('/settings/company'); }}
              className={styles.manageBtn}
            >
              {t('company.manage')} →
            </button>
          </div>
        </>
      )}
    </div>
  );
}
