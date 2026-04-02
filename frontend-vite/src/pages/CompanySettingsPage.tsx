import { useState, useEffect, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { Building2, Users, Trash2, UserPlus, X, AlertTriangle, Save } from 'lucide-react';
import { clsx } from 'clsx';
import { Card } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Alert } from '@/components/ui/alert';
import { Spinner } from '@/components/ui/spinner';
import { useCompanyStore } from '@/stores/company-store';
import { useAuthStore } from '@/stores/auth-store';
import { apiClient } from '@/lib/api-client';
import { companyApi } from '@/lib/company-api';
import type { CompanyMember, MemberRole, PaginatedResponse } from '@/types';
import styles from './CompanySettingsPage.module.css';
import { useNavigate, useSearchParams } from 'react-router-dom';


export default function CompanyPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const isCreate = searchParams.get('create') === '1';

  const { activeCompany, fetchCompanies } = useCompanyStore();
  const { user } = useAuthStore();

  // Determine if current user is the owner by comparing owner.id with user.id
  const isOwner = activeCompany?.owner?.id === user?.id;

  // Company form
  const [name, setName] = useState(activeCompany?.name ?? '');
  const [siret, setSiret] = useState(activeCompany?.siret ?? '');
  const [sector, setSector] = useState(activeCompany?.sector ?? '');
  const [saving, setSaving] = useState(false);
  const [saveMessage, setSaveMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  // Members
  const [members, setMembers] = useState<CompanyMember[]>([]);
  const [membersLoading, setMembersLoading] = useState(false);
  const [inviteEmail, setInviteEmail] = useState('');
  const [inviteRole, setInviteRole] = useState<MemberRole>('member');
  const [inviting, setInviting] = useState(false);
  const [inviteError, setInviteError] = useState<string | null>(null);

  // Danger
  const [deleteConfirm, setDeleteConfirm] = useState('');
  const [deleteError, setDeleteError] = useState<string | null>(null);

  // Create company form
  const [createName, setCreateName] = useState('');
  const [createSiret, setCreateSiret] = useState('');
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  useEffect(() => {
    if (activeCompany?.name) setName(activeCompany.name);
    if (activeCompany?.siret) setSiret(activeCompany.siret);
    if (activeCompany?.sector) setSector(activeCompany.sector ?? '');
  }, [activeCompany]);

  const fetchMembers = useCallback(async () => {
    if (!activeCompany) return;
    setMembersLoading(true);
    try {
      const data = await companyApi.get<PaginatedResponse<CompanyMember> | CompanyMember[]>('/members/');
      setMembers(Array.isArray(data) ? data : data.results ?? []);
    } catch {
      setMembers([]);
    } finally {
      setMembersLoading(false);
    }
  }, [activeCompany]);

  useEffect(() => {
    if (activeCompany && !isCreate) fetchMembers();
  }, [activeCompany, isCreate, fetchMembers]);

  const handleSave = async () => {
    if (!activeCompany) return;
    setSaving(true);
    setSaveMessage(null);
    try {
      await apiClient.patch(`/companies/${activeCompany.publicId}/`, {
        name,
        siret: siret || undefined,
        sector: sector || undefined,
      });
      setSaveMessage({ type: 'success', text: t('settings.saved') });
      await fetchCompanies();
    } catch {
      setSaveMessage({ type: 'error', text: t('errors.unknown') });
    } finally {
      setSaving(false);
    }
  };

  const handleCreate = async () => {
    if (!createName.trim()) return;
    setCreating(true);
    setCreateError(null);
    try {
      await apiClient.post('/companies/', { name: createName, siret: createSiret || undefined });
      await fetchCompanies();
      navigate('/settings/company');
    } catch {
      setCreateError(t('errors.unknown'));
    } finally {
      setCreating(false);
    }
  };

  const handleInvite = async () => {
    if (!inviteEmail.trim() || !activeCompany) return;
    setInviting(true);
    setInviteError(null);
    try {
      await companyApi.post('/members/', {
        email: inviteEmail,
        role: inviteRole,
      });
      setInviteEmail('');
      await fetchMembers();
    } catch {
      setInviteError(t('errors.unknown'));
    } finally {
      setInviting(false);
    }
  };

  const handleRemoveMember = async (memberId: number) => {
    if (!activeCompany) return;
    try {
      await companyApi.delete(`/members/${memberId}/`);
      setMembers((prev) => prev.filter((m) => m.id !== memberId));
    } catch {
      // Ignore
    }
  };

  // -- Create company mode -------------------------------------------------------

  if (isCreate) {
    return (
      <div className={styles.pageCreate}>
        <div>
          <h1 className={styles.title}>{t('company.create')}</h1>
        </div>
        {createError && <Alert variant="error" onClose={() => setCreateError(null)}>{createError}</Alert>}
        <Card padding="md">
          <div className={styles.cardSpaced}>
            <Input
              label={t('settings.companyName')}
              value={createName}
              onChange={(e) => setCreateName(e.target.value)}
              placeholder="Ma Societe SAS"
            />
            <Input
              label={`${t('settings.siret')} (${t('common.optional')})`}
              value={createSiret}
              onChange={(e) => setCreateSiret(e.target.value)}
              placeholder="123 456 789 00012"
            />
            <div className={styles.footer}>
              <Button variant="ghost" onClick={() => navigate(-1)} disabled={creating}>
                {t('common.cancel')}
              </Button>
              <Button onClick={handleCreate} isLoading={creating} leftIcon={<Save className={styles.iconSm} />}>
                {t('company.create')}
              </Button>
            </div>
          </div>
        </Card>
      </div>
    );
  }

  // -- Manage company mode -------------------------------------------------------

  const roleClass: Record<MemberRole, string> = {
    owner: styles.roleOwner,
    admin: styles.roleAdmin,
    member: styles.roleMember,
  };

  return (
    <div className={styles.page}>
      <div>
        <h1 className={styles.title}>{t('company.manage')}</h1>
        {activeCompany && (
          <p className={styles.subtitle}>{activeCompany.name}</p>
        )}
      </div>

      {/* Company info */}
      <Card padding="md">
        <div className={styles.cardSpaced}>
          <div className={styles.sectionHeader}>
            <Building2 className={styles.sectionIcon} aria-hidden="true" />
            <h2 className={styles.sectionTitle}>{t('settings.company')}</h2>
          </div>
          {saveMessage && (
            <Alert variant={saveMessage.type === 'success' ? 'success' : 'error'} onClose={() => setSaveMessage(null)}>
              {saveMessage.text}
            </Alert>
          )}
          <Input
            label={t('settings.companyName')}
            value={name}
            onChange={(e) => setName(e.target.value)}
            disabled={!isOwner}
          />
          <Input
            label={t('settings.siret')}
            value={siret}
            onChange={(e) => setSiret(e.target.value)}
            disabled={!isOwner}
            placeholder="123 456 789 00012"
          />
          <Input
            label="Secteur"
            value={sector}
            onChange={(e) => setSector(e.target.value)}
            disabled={!isOwner}
            placeholder="Services, Commerce, Industrie..."
          />
          {isOwner && (
            <div className={styles.footerRight}>
              <Button size="sm" leftIcon={<Save className={styles.iconSm} />} onClick={handleSave} isLoading={saving}>
                {t('settings.saveCompany')}
              </Button>
            </div>
          )}
        </div>
      </Card>

      {/* Members */}
      <Card padding="md">
        <div className={styles.sectionHeader} style={{ marginBottom: '1rem' }}>
          <Users className={styles.sectionIcon} aria-hidden="true" />
          <h2 className={styles.sectionTitle}>{t('company.members')}</h2>
        </div>

        {membersLoading ? (
          <div className={styles.membersLoading}><Spinner size="sm" /></div>
        ) : (
          <div className={styles.membersList}>
            {members.map((member) => {
              const memberUser = member.user;
              const initials = `${(memberUser?.firstName ?? '?')[0]}${(memberUser?.lastName ?? '?')[0]}`;
              return (
                <div
                  key={member.id ?? member.user?.email ?? member.userId}
                  className={styles.memberRow}
                >
                  <div className={styles.memberAvatar}>
                    {initials}
                  </div>
                  <div className={styles.memberInfo}>
                    <p className={styles.memberName}>
                      {memberUser?.firstName} {memberUser?.lastName}
                    </p>
                    <p className={styles.memberEmail}>{memberUser?.email}</p>
                  </div>
                  <span className={clsx(styles.roleBadge, roleClass[member.role])}>
                    {t(`company.roles.${member.role}`)}
                  </span>
                  {isOwner && member.role !== 'owner' && (
                    <button
                      type="button"
                      onClick={() => handleRemoveMember(member.id)}
                      className={styles.removeBtn}
                    >
                      <X className={styles.removeIcon} />
                    </button>
                  )}
                </div>
              );
            })}
          </div>
        )}

        {/* Invite form */}
        {isOwner && (
          <div className={styles.inviteSection}>
            <p className={styles.inviteLabel}>{t('company.invite')}</p>
            {inviteError && <Alert variant="error" onClose={() => setInviteError(null)}>{inviteError}</Alert>}
            <div className={styles.inviteRow}>
              <Input
                type="email"
                placeholder={t('company.inviteEmail')}
                value={inviteEmail}
                onChange={(e) => setInviteEmail(e.target.value)}
              />
              <select
                value={inviteRole}
                onChange={(e) => setInviteRole(e.target.value as MemberRole)}
                className={styles.inviteSelect}
              >
                <option value="member">{t('company.roles.member')}</option>
                <option value="admin">{t('company.roles.admin')}</option>
              </select>
              <Button
                size="sm"
                leftIcon={<UserPlus className={styles.iconSm} />}
                onClick={handleInvite}
                isLoading={inviting}
                disabled={!inviteEmail.trim()}
              >
                {t('company.invite')}
              </Button>
            </div>
          </div>
        )}
      </Card>

      {/* Danger zone (owner only) */}
      {isOwner && (
        <Card padding="md" className={styles.dangerBorder}>
          <div className={styles.cardSpaced}>
            <div className={styles.sectionHeader}>
              <AlertTriangle className={styles.dangerIcon} aria-hidden="true" />
              <h2 className={clsx(styles.sectionTitle, styles.dangerTitle)}>{t('settings.danger')}</h2>
            </div>
            <Alert variant="error">
              {t('company.deleteCompanyDescription')}
            </Alert>
            {deleteError && <Alert variant="error" onClose={() => setDeleteError(null)}>{deleteError}</Alert>}
            <Input
              label={t('company.deleteCompanyConfirm')}
              value={deleteConfirm}
              onChange={(e) => setDeleteConfirm(e.target.value)}
              placeholder={activeCompany?.name}
            />
            <Button
              variant="danger"
              leftIcon={<Trash2 className={styles.iconSm} />}
              disabled={deleteConfirm !== activeCompany?.name}
              onClick={() => setDeleteError('Not implemented yet')}
              fullWidth
            >
              {t('company.deleteCompany')}
            </Button>
          </div>
        </Card>
      )}
    </div>
  );
}
