import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import LanguageDetector from 'i18next-browser-languagedetector';
import fr from './locales/fr.json';
import en from './locales/en.json';

i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources: {
      fr: { translation: fr },
      en: { translation: en },
    },
    fallbackLng: 'fr',
    interpolation: {
      escapeValue: false, // React already escapes
      prefix: '{',
      suffix: '}',
    },
    detection: {
      order: ['cookie', 'navigator'],
      caches: ['cookie'],
      cookieMinutes: 525960, // 1 year
      lookupCookie: 'locale',
    },
  });

export default i18n;

export function setLocale(lang: string) {
  i18n.changeLanguage(lang);
  document.cookie = `locale=${lang};path=/;max-age=${525960 * 60};SameSite=Lax${window.location.protocol === 'https:' ? ';Secure' : ''}`;
  document.documentElement.lang = lang;
}
