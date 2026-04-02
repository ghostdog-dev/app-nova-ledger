import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { User, Lock, Bell, Building2, AlertTriangle, Globe, Save, CreditCard } from 'lucide-react';
import { clsx } from 'clsx';
import { Card } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Alert } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { useAuthStore } from '@/stores/auth-store';
import { useCompanyStore } from '@/stores/company-store';
import { apiClient } from '@/lib/api-client';

import styles from './SettingsPage.module.css';

type SettingsTab = 'profile' | 'preferences' | 'company' | 'danger';

const TABS: { id: SettingsTab; icon: React.ReactNode; labelKey: string }[] = [
  { id: 'profile', icon: <User className={styles.sectionIcon} />, labelKey: 'settings.profile' },
  { id: 'preferences', icon: <Bell className={styles.sectionIcon} />, labelKey: 'settings.preferences' },
  { id: 'company', icon: <Building2 className={styles.sectionIcon} />, labelKey: 'settings.company' },
  { id: 'danger', icon: <AlertTriangle className={styles.sectionIcon} />, labelKey: 'settings.danger' },
];

const CSV_SEPARATORS = [
  { value: ',', label: 'Virgule (,)' },
  { value: ';', label: 'Point-virgule (;)' },
  { value: '\t', label: 'Tabulation' },
];

export default function SettingsPage() {
  const { t } = useTranslation();
  const { user, updateUser } = useAuthStore();
  const { activeCompany } = useCompanyStore();
  const [activeTab, setActiveTab] = useState<SettingsTab>('profile');

  // Profile form
  const [firstName, setFirstName] = useState(user?.firstName ?? '');
  const [lastName, setLastName] = useState(user?.lastName ?? '');
  const [profileSaving, setProfileSaving] = useState(false);
  const [profileMessage, setProfileMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  // Preferences
  const [csvSeparator, setCsvSeparator] = useState(',');
  const [emailNotifs, setEmailNotifs] = useState(true);
  const [prefSaving, setPrefSaving] = useState(false);

  // Company
  const [companyName, setCompanyName] = useState('');
  const [siret, setSiret] = useState('');
  const [companySaving, setCompanySaving] = useState(false);

  // Danger
  const [deleteConfirm, setDeleteConfirm] = useState('');
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const handleSaveProfile = async () => {
    if (!firstName.trim() || !lastName.trim()) return;
    setProfileSaving(true);
    setProfileMessage(null);
    try {
      await apiClient.patch('/accounts/me/', { firstName, lastName });
      updateUser({ firstName, lastName });
      setProfileMessage({ type: 'success', text: t('settings.saved') });
    } catch {
      setProfileMessage({ type: 'error', text: t('errors.unknown') });
    } finally {
      setProfileSaving(false);
    }
  };

  const handleManageSubscription = async () => {
    try {
      const response = await apiClient.post<{ url: string }>('/billing/portal-session/');
      window.location.href = response.url;
    } catch (err) {
      console.error('Failed to open billing portal', err);
    }
  };

  const handleSavePreferences = async () => {
    setPrefSaving(true);
    try {
      // Preferences are stored in user profile
      await apiClient.patch('/accounts/me/', {
        profile: {
          emailNotifications: emailNotifs,
        },
      });
    } catch {
      // Silently ignore for now
    } finally {
      setPrefSaving(false);
    }
  };

  const handleSaveCompany = async () => {
    const companyId = activeCompany?.publicId;
    if (!companyId) return;
    setCompanySaving(true);
    try {
      await apiClient.patch(`/companies/${companyId}/`, { name: companyName, siret });
    } catch {
      // Silently ignore for now
    } finally {
      setCompanySaving(false);
    }
  };

  return (
    <div className={styles.page}>
      {/* Page header */}
      <div className={styles.pageHeader}>
        <h1 className={styles.title}>{t('settings.title')}</h1>
        <p className={styles.subtitle}>{t('settings.subtitle')}</p>
      </div>

      <div className={styles.layout}>
        {/* Tab sidebar */}
        <nav className={styles.tabNav} aria-label="Settings navigation">
          {TABS.map((tab) => (
            <button
              key={tab.id}
              type="button"
              onClick={() => setActiveTab(tab.id)}
              className={clsx(styles.tab, activeTab === tab.id && styles.tabActive)}
            >
              <span className={clsx(activeTab === tab.id ? styles.tabIconActive : styles.tabIcon)}>
                {tab.icon}
              </span>
              {t(tab.labelKey)}
            </button>
          ))}
        </nav>

        {/* Tab content */}
        <div className={styles.content}>
          {/* Profile */}
          {activeTab === 'profile' && (
            <Card padding="md">
              <div className={styles.cardSpaced}>
                <div className={styles.sectionTitle}>
                  <User className={styles.sectionTitleIcon} aria-hidden="true" />
                  <h2 className={styles.sectionTitleText}>{t('settings.profile')}</h2>
                </div>

                {profileMessage && (
                  <Alert
                    variant={profileMessage.type === 'success' ? 'success' : 'error'}
                    onClose={() => setProfileMessage(null)}
                  >
                    {profileMessage.text}
                  </Alert>
                )}

                <div className={styles.formGrid}>
                  <Input
                    label={t('settings.firstName')}
                    value={firstName}
                    onChange={(e) => setFirstName(e.target.value)}
                  />
                  <Input
                    label={t('settings.lastName')}
                    value={lastName}
                    onChange={(e) => setLastName(e.target.value)}
                  />
                </div>

                <Input
                  label={t('settings.email')}
                  type="email"
                  value={user?.email ?? ''}
                  disabled
                  className={styles.emailDisabled}
                />

                <div className={styles.footer}>
                  <div className={styles.badgeRow}>
                    <Badge variant="info">{user?.plan ?? 'free'}</Badge>
                    <Button
                      variant="ghost"
                      size="sm"
                      leftIcon={<CreditCard className={styles.sectionIcon} />}
                      onClick={handleManageSubscription}
                    >
                      {t('settings.manageSubscription', 'G\u00e9rer l\u2019abonnement')}
                    </Button>
                  </div>
                  <Button
                    size="sm"
                    leftIcon={<Save className={styles.sectionIcon} />}
                    onClick={handleSaveProfile}
                    isLoading={profileSaving}
                  >
                    {t('settings.saveProfile')}
                  </Button>
                </div>
              </div>
            </Card>
          )}

          {/* Preferences */}
          {activeTab === 'preferences' && (
            <Card padding="md">
              <div className={styles.cardSpaced}>
                <div className={styles.sectionTitle}>
                  <Bell className={styles.sectionTitleIcon} aria-hidden="true" />
                  <h2 className={styles.sectionTitleText}>{t('settings.preferences')}</h2>
                </div>

                {/* Language */}
                <div className={styles.settingRow}>
                  <div className={styles.settingRowInner}>
                    <Globe className={styles.sectionTitleIcon} aria-hidden="true" />
                    <div>
                      <p className={styles.settingLabel}>{t('settings.language')}</p>
                      <p className={styles.settingDesc}>{t('settings.languageDescription')}</p>
                    </div>
                  </div>
                  <p className={styles.settingHint}>Via le header &rarr;</p>
                </div>

                {/* CSV separator */}
                <div>
                  <label className={styles.labelBlock}>
                    {t('settings.csvSeparator')}
                  </label>
                  <div className={styles.separatorGroup}>
                    {CSV_SEPARATORS.map((sep) => (
                      <button
                        key={sep.value}
                        type="button"
                        onClick={() => setCsvSeparator(sep.value)}
                        className={clsx(
                          styles.separatorBtn,
                          csvSeparator === sep.value && styles.separatorBtnActive
                        )}
                      >
                        {sep.label}
                      </button>
                    ))}
                  </div>
                </div>

                {/* Email notifications toggle */}
                <label className={styles.toggleLabel}>
                  <div>
                    <p className={styles.settingLabel}>{t('settings.emailNotifications')}</p>
                    <p className={styles.settingDesc}>{t('settings.emailNotificationsHint')}</p>
                  </div>
                  <div
                    className={clsx(styles.toggle, emailNotifs ? styles.toggleOn : styles.toggleOff)}
                    onClick={() => setEmailNotifs(!emailNotifs)}
                  >
                    <span
                      className={clsx(styles.toggleThumb, emailNotifs && styles.toggleThumbOn)}
                    />
                    <input type="checkbox" className="sr-only" checked={emailNotifs} onChange={() => {}} />
                  </div>
                </label>

                <div className={styles.footer}>
                  <Button size="sm" leftIcon={<Save className={styles.sectionIcon} />} onClick={handleSavePreferences} isLoading={prefSaving}>
                    {t('settings.saveProfile')}
                  </Button>
                </div>
              </div>
            </Card>
          )}

          {/* Company */}
          {activeTab === 'company' && (
            <Card padding="md">
              <div className={styles.cardSpaced}>
                <div className={styles.sectionTitle}>
                  <Building2 className={styles.sectionTitleIcon} aria-hidden="true" />
                  <h2 className={styles.sectionTitleText}>{t('settings.company')}</h2>
                </div>
                <Input
                  label={t('settings.companyName')}
                  value={companyName}
                  onChange={(e) => setCompanyName(e.target.value)}
                  placeholder="Ma Société SAS"
                />
                <Input
                  label={t('settings.siret')}
                  value={siret}
                  onChange={(e) => setSiret(e.target.value)}
                  placeholder="123 456 789 00012"
                />
                <div className={styles.footer}>
                  <Button size="sm" leftIcon={<Save className={styles.sectionIcon} />} onClick={handleSaveCompany} isLoading={companySaving}>
                    {t('settings.saveCompany')}
                  </Button>
                </div>
              </div>
            </Card>
          )}

          {/* Danger zone */}
          {activeTab === 'danger' && (
            <Card padding="md" className={styles.dangerBorder}>
              <div className={styles.cardSpaced}>
                <div className={styles.sectionTitle}>
                  <AlertTriangle className={clsx(styles.sectionTitleIcon, styles.sectionIconDanger)} aria-hidden="true" />
                  <h2 className={clsx(styles.sectionTitleText, styles.dangerTitle)}>{t('settings.danger')}</h2>
                </div>
                <Alert variant="error">
                  {t('settings.deleteAccountDescription')}
                </Alert>
                {deleteError && (
                  <Alert variant="error" onClose={() => setDeleteError(null)}>{deleteError}</Alert>
                )}
                <Input
                  label={t('settings.deleteAccountConfirm')}
                  type="email"
                  value={deleteConfirm}
                  onChange={(e) => setDeleteConfirm(e.target.value)}
                  placeholder={user?.email}
                />
                <Button
                  variant="danger"
                  disabled={deleteConfirm !== user?.email}
                  onClick={() => setDeleteError('Not implemented yet')}
                  fullWidth
                >
                  {t('settings.deleteAccount')}
                </Button>
              </div>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}
