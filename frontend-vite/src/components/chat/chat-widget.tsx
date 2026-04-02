import { useState, useRef, useEffect, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { MessageCircle, X, Plus, Send, Loader2, WifiOff } from 'lucide-react';
import { clsx } from 'clsx';
import { useChat } from '@/hooks/use-chat';
import { ChatMessage, ThinkingIndicator } from './chat-message';
import { ChatSuggestions } from './chat-suggestions';
import styles from './chat-widget.module.css';

interface ChatWidgetProps {
  /** Pre-contextualize on an execution when on the results page */
  executionId?: number;
}

export function ChatWidget({ executionId }: ChatWidgetProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [input, setInput] = useState('');
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const { messages, isThinking, isReady, connectionFailed, sendMessage, resetSession } = useChat({ executionId });

  // Auto-scroll to bottom when messages change
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, isThinking]);

  // Focus input when panel opens
  useEffect(() => {
    if (open && inputRef.current) {
      setTimeout(() => inputRef.current?.focus(), 100);
    }
  }, [open]);

  const handleSend = useCallback(() => {
    const text = input.trim();
    if (!text || isThinking) return;
    setInput('');
    sendMessage(text);
  }, [input, isThinking, sendMessage]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleSuggestionSelect = useCallback(
    (question: string) => {
      sendMessage(question);
    },
    [sendMessage]
  );

  return (
    <>
      {/* Floating button */}
      <button
        type="button"
        onClick={() => setOpen(true)}
        className={clsx(styles.fabBtn, open && styles.fabHidden)}
        aria-label={t('chat.title')}
      >
        <MessageCircle className={styles.fabIcon} aria-hidden="true" />
      </button>

      {/* Slide-in panel */}
      <div
        className={clsx(styles.panel, open ? styles.panelOpen : styles.panelClosed)}
        role="dialog"
        aria-modal="true"
        aria-label={t('chat.title')}
      >
        {/* Header */}
        <div className={styles.panelHeader}>
          <div className={styles.panelHeaderLeft}>
            <div className={styles.avatar}>
              IA
            </div>
            <div>
              <p className={styles.panelTitle}>{t('chat.title')}</p>
              <p className={styles.panelStatus}>
                {isReady ? 'En ligne' : 'Connexion\u2026'}
              </p>
            </div>
          </div>
          <div className={styles.panelHeaderRight}>
            <button
              type="button"
              onClick={resetSession}
              className={styles.headerBtn}
              title={t('chat.newConversation')}
            >
              <Plus className={styles.headerBtnIcon} aria-hidden="true" />
            </button>
            <button
              type="button"
              onClick={() => setOpen(false)}
              className={styles.headerBtn}
              title={t('chat.close')}
            >
              <X className={styles.headerBtnIcon} aria-hidden="true" />
            </button>
          </div>
        </div>

        {/* F54 — Connection failure notice */}
        {connectionFailed && (
          <div className={styles.connectionWarning}>
            <WifiOff className={styles.connectionWarningIcon} aria-hidden="true" />
            <p className={styles.connectionWarningText}>
              Connexion temps r\u00e9el perdue. Les messages sont envoy\u00e9s en mode classique.
            </p>
          </div>
        )}

        {/* Messages area */}
        <div
          ref={scrollRef}
          className={styles.messages}
        >
          {messages.length === 0 && !isThinking ? (
            <ChatSuggestions onSelect={handleSuggestionSelect} />
          ) : (
            <>
              {messages.map((msg) => (
                <ChatMessage key={msg.id} message={msg} />
              ))}
              {isThinking && <ThinkingIndicator />}
            </>
          )}
        </div>

        {/* Input */}
        <div className={styles.inputArea}>
          <div className={styles.inputWrap}>
            <textarea
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={t('chat.placeholder')}
              rows={1}
              className={styles.textarea}
              style={{ minHeight: '24px' }}
              disabled={!isReady || isThinking}
            />
            <button
              type="button"
              onClick={handleSend}
              disabled={!input.trim() || isThinking || !isReady}
              className={styles.sendBtn}
              aria-label={t('chat.send')}
            >
              {isThinking ? (
                <Loader2 className={styles.sendBtnIcon} style={{ animation: 'spin 1s linear infinite' }} aria-hidden="true" />
              ) : (
                <Send className={styles.sendBtnIcon} aria-hidden="true" />
              )}
            </button>
          </div>
        </div>
      </div>
    </>
  );
}
