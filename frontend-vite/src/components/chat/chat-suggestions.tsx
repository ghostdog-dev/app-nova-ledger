import { useTranslation } from 'react-i18next';
import { Sparkles } from 'lucide-react';
import styles from './chat-suggestions.module.css';

interface ChatSuggestionsProps {
  onSelect: (question: string) => void;
}

export function ChatSuggestions({ onSelect }: ChatSuggestionsProps) {
  const { t } = useTranslation();

  // i18next array access under chat.suggestions
  const items = [
    t('chat.suggestions.items.0'),
    t('chat.suggestions.items.1'),
    t('chat.suggestions.items.2'),
    t('chat.suggestions.items.3'),
  ];

  return (
    <div className={styles.wrap}>
      <div className={styles.iconWrap}>
        <Sparkles className={styles.iconInner} aria-hidden="true" />
      </div>
      <div>
        <p className={styles.title}>{t('chat.suggestions.title')}</p>
        <p className={styles.subtitle}>
          {t('chat.title')}
        </p>
      </div>
      <div className={styles.items}>
        {items.map((item, i) => (
          <button
            key={i}
            type="button"
            onClick={() => onSelect(item)}
            className={styles.item}
          >
            {item}
          </button>
        ))}
      </div>
    </div>
  );
}
