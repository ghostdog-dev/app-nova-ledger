import { useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { Mail, Lock, User } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Alert } from '@/components/ui/alert';
import { useAuth } from '@/hooks/use-auth';
import { startSocialLogin } from '@/lib/social-auth';
import styles from './RegisterPage.module.css';
import { Link } from 'react-router-dom';


interface FormErrors {
  firstName?: string;
  lastName?: string;
  email?: string;
  password?: string;
  confirmPassword?: string;
}

function validate(
  firstName: string,
  lastName: string,
  email: string,
  password: string,
  confirmPassword: string
): FormErrors {
  const errors: FormErrors = {};
  if (!firstName) errors.firstName = 'firstNameRequired';
  if (!lastName) errors.lastName = 'lastNameRequired';
  if (!email) errors.email = 'emailRequired';
  else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) errors.email = 'emailInvalid';
  if (!password) errors.password = 'passwordRequired';
  else if (password.length < 12) errors.password = 'passwordTooShort';
  if (!confirmPassword) errors.confirmPassword = 'confirmPasswordRequired';
  else if (password !== confirmPassword) errors.confirmPassword = 'passwordMismatch';
  return errors;
}

export default function RegisterPage() {
  const { t } = useTranslation();
  const { register, isLoading } = useAuth();

  const [firstName, setFirstName] = useState('');
  const [lastName, setLastName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [errors, setErrors] = useState<FormErrors>({});
  const [serverError, setServerError] = useState<string | null>(null);

  const clearFieldError = (field: keyof FormErrors) =>
    setErrors((prev) => ({ ...prev, [field]: undefined }));

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setServerError(null);

    const validationErrors = validate(firstName, lastName, email, password, confirmPassword);
    if (Object.keys(validationErrors).length > 0) {
      setErrors(validationErrors);
      return;
    }
    setErrors({});

    try {
      await register({ firstName, lastName, email, password });
    } catch (err) {
      const message = (err as { message?: string })?.message ?? t('errors.unknown');
      setServerError(message);
    }
  };

  const tValidation = (key: string) =>
    t(`auth.validation.${key}`);

  return (
    <>
      <div className={styles.header}>
        <h1 className={styles.title}>{t('auth.register.title')}</h1>
        <p className={styles.subtitle}>{t('auth.register.subtitle')}</p>
      </div>

      {serverError && (
        <Alert variant="error" className={styles.alertWrap} onClose={() => setServerError(null)}>
          {serverError}
        </Alert>
      )}

      <form onSubmit={handleSubmit} noValidate className={styles.form}>
        <div className={styles.nameGrid}>
          <Input
            type="text"
            label={t('auth.register.firstName')}
            placeholder={t('auth.register.firstNamePlaceholder')}
            value={firstName}
            onChange={(e) => { setFirstName(e.target.value); clearFieldError('firstName'); }}
            error={errors.firstName ? tValidation(errors.firstName) : undefined}
            leftIcon={<User className={styles.oauthIcon} />}
            autoComplete="given-name"
            required
          />
          <Input
            type="text"
            label={t('auth.register.lastName')}
            placeholder={t('auth.register.lastNamePlaceholder')}
            value={lastName}
            onChange={(e) => { setLastName(e.target.value); clearFieldError('lastName'); }}
            error={errors.lastName ? tValidation(errors.lastName) : undefined}
            autoComplete="family-name"
            required
          />
        </div>

        <Input
          type="email"
          label={t('auth.register.email')}
          placeholder={t('auth.register.emailPlaceholder')}
          value={email}
          onChange={(e) => { setEmail(e.target.value); clearFieldError('email'); }}
          error={errors.email ? tValidation(errors.email) : undefined}
          leftIcon={<Mail className={styles.oauthIcon} />}
          autoComplete="email"
          required
        />

        <Input
          type="password"
          label={t('auth.register.password')}
          placeholder={t('auth.register.passwordPlaceholder')}
          value={password}
          onChange={(e) => { setPassword(e.target.value); clearFieldError('password'); }}
          error={errors.password ? tValidation(errors.password) : undefined}
          leftIcon={<Lock className={styles.oauthIcon} />}
          autoComplete="new-password"
          required
        />

        <Input
          type="password"
          label={t('auth.register.confirmPassword')}
          placeholder={t('auth.register.confirmPasswordPlaceholder')}
          value={confirmPassword}
          onChange={(e) => { setConfirmPassword(e.target.value); clearFieldError('confirmPassword'); }}
          error={errors.confirmPassword ? tValidation(errors.confirmPassword) : undefined}
          leftIcon={<Lock className={styles.oauthIcon} />}
          autoComplete="new-password"
          required
        />

        <Button type="submit" fullWidth isLoading={isLoading} className={styles.submitBtn}>
          {t('auth.register.submit')}
        </Button>
      </form>

      {/* OAuth divider */}
      <div className={styles.divider}>
        <div className={styles.dividerLine} />
        <span className={styles.dividerText}>{t('auth.register.orContinueWith')}</span>
        <div className={styles.dividerLine} />
      </div>

      {/* OAuth buttons */}
      <div className={styles.oauthGrid}>
        <Button
          type="button"
          variant="secondary"
          onClick={() => startSocialLogin('google')}
          className={styles.oauthBtnText}
        >
          <svg className={styles.oauthIcon} viewBox="0 0 24 24" aria-hidden="true">
            <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4" />
            <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853" />
            <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05" />
            <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335" />
          </svg>
          {t('auth.register.withGoogle')}
        </Button>
        <Button
          type="button"
          variant="secondary"
          onClick={() => startSocialLogin('microsoft')}
          className={styles.oauthBtnText}
        >
          <svg className={styles.oauthIcon} viewBox="0 0 24 24" aria-hidden="true" fill="currentColor">
            <path d="M11.4 24H0V12.6h11.4V24zM24 24H12.6V12.6H24V24zM11.4 11.4H0V0h11.4v11.4zM24 11.4H12.6V0H24v11.4z" />
          </svg>
          {t('auth.register.withMicrosoft')}
        </Button>
      </div>

      {/* Terms notice */}
      <p className={styles.termsNotice}>
        {t('auth.register.termsInfo')}
      </p>

      {/* Login link */}
      <p className={styles.loginLink}>
        {t('auth.register.hasAccount')}{' '}
        <Link to="/login"
          className={styles.loginLinkAccent}
        >
          {t('auth.register.loginLink')}
        </Link>
      </p>
    </>
  );
}
