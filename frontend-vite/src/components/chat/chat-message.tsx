import { clsx } from 'clsx';
import type { ChatMessage as ChatMessageType } from '@/types';
import styles from './chat-message.module.css';

interface ChatMessageProps {
  message: ChatMessageType;
}

/**
 * Minimal markdown: bold (**text**), inline code (`code`), line breaks.
 * Full markdown parsing is intentionally avoided to keep bundle small.
 */
function renderContent(text: string): React.ReactNode {
  // Split by newlines, process each line
  return text.split('\n').map((line, li) => {
    // Bold: **text**
    const parts = line.split(/(\*\*[^*]+\*\*|`[^`]+`)/g).map((part, pi) => {
      if (part.startsWith('**') && part.endsWith('**')) {
        return <strong key={pi}>{part.slice(2, -2)}</strong>;
      }
      if (part.startsWith('`') && part.endsWith('`')) {
        return (
          <code key={pi} className={styles.inlineCode}>
            {part.slice(1, -1)}
          </code>
        );
      }
      return part;
    });
    return (
      <span key={li}>
        {parts}
        {li < text.split('\n').length - 1 && <br />}
      </span>
    );
  });
}

export function ChatMessage({ message }: ChatMessageProps) {
  const isUser = message.role === 'user';

  return (
    <div
      className={clsx(styles.row, isUser ? styles.rowUser : styles.rowAssistant)}
    >
      {!isUser && (
        <div className={styles.avatar}>
          IA
        </div>
      )}
      <div
        className={clsx(
          styles.bubble,
          isUser ? styles.bubbleUser : styles.bubbleAssistant
        )}
      >
        {renderContent(message.content)}
      </div>
    </div>
  );
}

export function ThinkingIndicator() {
  return (
    <div className={styles.thinkingRow}>
      <div className={styles.avatar}>
        IA
      </div>
      <div className={styles.thinkingBubble}>
        <div className={styles.thinkingDots}>
          {[0, 1, 2].map((i) => (
            <span
              key={i}
              className={styles.dot}
              style={{ animationDelay: `${i * 150}ms` }}
            />
          ))}
        </div>
      </div>
    </div>
  );
}
