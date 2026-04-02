import { useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { Mail, Lock } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Alert } from '@/components/ui/alert';
import { useAuth } from '@/hooks/use-auth';
import { startSocialLogin } from '@/lib/social-auth';
import styles from './LoginPage.module.css';
import { Link, useSearchParams } from 'react-router-dom';


interface FormErrors {
  email?: string;
  password?: string;
}

function validate(email: string, password: string): FormErrors {
  const errors: FormErrors = {};
  if (!email) errors.email = 'emailRequired';
  else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) errors.email = 'emailInvalid';
  if (!password) errors.password = 'passwordRequired';
  return errors;
}

export default function LoginPage() {
  const { t } = useTranslation();
  const { login, isLoading } = useAuth();
  const [searchParams] = useSearchParams();
  const justRegistered = searchParams.get('registered') === 'true';

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [errors, setErrors] = useState<FormErrors>({});
  const [serverError, setServerError] = useState<string | null>(null);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setServerError(null);

    const validationErrors = validate(email, password);
    if (Object.keys(validationErrors).length > 0) {
      setErrors(validationErrors);
      return;
    }
    setErrors({});

    try {
      await login({ email, password });
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
        <h1 className={styles.title}>{t('auth.login.title')}</h1>
        <p className={styles.subtitle}>{t('auth.login.subtitle')}</p>
      </div>

      {justRegistered && (
        <Alert variant="success" className={styles.alertWrap}>
          {t('auth.login.registeredSuccess')}
        </Alert>
      )}

      {serverError && (
        <Alert variant="error" className={styles.alertWrap} onClose={() => setServerError(null)}>
          {serverError}
        </Alert>
      )}

      <form onSubmit={handleSubmit} noValidate className={styles.form}>
        <Input
          type="email"
          label={t('auth.login.email')}
          placeholder={t('auth.login.emailPlaceholder')}
          value={email}
          onChange={(e) => { setEmail(e.target.value); setErrors((p) => ({ ...p, email: undefined })); }}
          error={errors.email ? tValidation(errors.email) : undefined}
          leftIcon={<Mail className={styles.oauthIcon} />}
          autoComplete="email"
          required
        />

        <div>
          <Input
            type="password"
            label={t('auth.login.password')}
            placeholder={t('auth.login.passwordPlaceholder')}
            value={password}
            onChange={(e) => { setPassword(e.target.value); setErrors((p) => ({ ...p, password: undefined })); }}
            error={errors.password ? tValidation(errors.password) : undefined}
            leftIcon={<Lock className={styles.oauthIcon} />}
            autoComplete="current-password"
            required
          />
          <div>
            <Link to="/forgot-password"
              className={styles.forgotLink}
            >
              {t('auth.login.forgotPassword')}
            </Link>
          </div>
        </div>

        <Button type="submit" fullWidth isLoading={isLoading} className={styles.submitBtn}>
          {t('auth.login.submit')}
        </Button>
      </form>

      {/* OAuth divider */}
      <div className={styles.divider}>
        <div className={styles.dividerLine} />
        <span className={styles.dividerText}>{t('auth.login.orContinueWith')}</span>
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
            <path
              d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
              fill="#4285F4"
            />
            <path
              d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
              fill="#34A853"
            />
            <path
              d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"
              fill="#FBBC05"
            />
            <path
              d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
              fill="#EA4335"
            />
          </svg>
          {t('auth.login.withGoogle')}
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
          {t('auth.login.withMicrosoft')}
        </Button>
      </div>

      {/* Register link */}
      <p className={styles.registerLink}>
        {t('auth.login.noAccount')}{' '}
        <Link to="/register"
          className={styles.registerLinkAccent}
        >
          {t('auth.login.registerLink')}
        </Link>
      </p>
    </>
  );
}
