import { useState, useCallback, useRef, useEffect } from 'react';
import { getWsTicket } from '@/lib/api-client';
import { companyApi } from '@/lib/company-api';
import type { ChatSession, ChatMessage } from '@/types';

const WS_BASE_URL = import.meta.env.VITE_WS_URL ?? 'ws://localhost:8000/ws';

/**
 * F54 — WebSocket reconnection configuration.
 * Exponential backoff with jitter and a maximum retry limit.
 */
const WS_MAX_RETRIES = 5;
const WS_BASE_DELAY_MS = 1000;
const WS_MAX_DELAY_MS = 30000;

type WsIncoming =
  | { type: 'thinking' }
  | { type: 'message'; id: number; role: 'assistant'; content: string };

// -- REST API -------------------------------------------------------------------

/**
 * Create a new chat session.
 * Backend endpoint: POST /companies/{company_pk}/chat/sessions/
 */
async function createSession(executionId?: number): Promise<ChatSession> {
  return companyApi.post<ChatSession>('/chat/sessions/', {
    executionId: executionId ?? null,
  });
}

/**
 * Get an existing chat session.
 * Backend endpoint: GET /companies/{company_pk}/chat/sessions/{id}/
 */
async function getSession(id: number): Promise<ChatSession> {
  return companyApi.get<ChatSession>(`/chat/sessions/${id}/`);
}

/**
 * Send a message to a chat session (REST fallback).
 * Backend endpoint: POST /companies/{company_pk}/chat/sessions/{id}/message/
 */
async function sendMessageRest(sessionId: number, content: string): Promise<ChatMessage> {
  return companyApi.post<ChatMessage>(`/chat/sessions/${sessionId}/message/`, { content });
}

/**
 * F54 — Calculate exponential backoff delay with jitter.
 */
function getBackoffDelay(attempt: number): number {
  // Exponential: 1s, 2s, 4s, 8s, 16s (capped at WS_MAX_DELAY_MS)
  const exponentialDelay = Math.min(
    WS_BASE_DELAY_MS * Math.pow(2, attempt),
    WS_MAX_DELAY_MS
  );
  // Add random jitter (0-50% of the delay) to prevent thundering herd
  const jitter = Math.random() * exponentialDelay * 0.5;
  return exponentialDelay + jitter;
}

// -- Hook -----------------------------------------------------------------------

interface UseChatOptions {
  /** Pre-contextualize the session on a specific execution */
  executionId?: number;
}

interface UseChatReturn {
  messages: ChatMessage[];
  isThinking: boolean;
  isReady: boolean;
  /** True when WebSocket reconnection has been exhausted */
  connectionFailed: boolean;
  sendMessage: (content: string) => void;
  resetSession: () => void;
}

export function useChat(options: UseChatOptions = {}): UseChatReturn {
  const { executionId } = options;

  const [session, setSession] = useState<ChatSession | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isThinking, setIsThinking] = useState(false);
  const [isReady, setIsReady] = useState(false);
  const [connectionFailed, setConnectionFailed] = useState(false);

  const socketRef = useRef<WebSocket | null>(null);
  const sessionRef = useRef<ChatSession | null>(null);
  /** F54 — Track reconnection attempts */
  const reconnectAttemptRef = useRef(0);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const connectWs = useCallback(async (sess: ChatSession) => {
    // [F06] Obtain a single-use ticket instead of passing JWT in the URL
    const ticket = await getWsTicket();
    const url = `${WS_BASE_URL}/chat/${sess.id}/${ticket ? `?ticket=${ticket}` : ''}`;

    try {
      const ws = new WebSocket(url);
      socketRef.current = ws;

      ws.onopen = () => {
        setIsReady(true);
        setConnectionFailed(false);
        // Reset reconnection counter on successful connection
        reconnectAttemptRef.current = 0;
      };

      ws.onmessage = (event) => {
        try {
          const msg: WsIncoming = JSON.parse(event.data as string);
          if (msg.type === 'thinking') {
            setIsThinking(true);
          } else if (msg.type === 'message') {
            setIsThinking(false);
            setMessages((prev) => [
              ...prev,
              {
                id: msg.id,
                role: 'assistant',
                content: msg.content,
                createdAt: new Date().toISOString(),
              },
            ]);
          }
        } catch {
          // Ignore malformed messages
        }
      };

      ws.onclose = () => {
        setIsReady(false);

        /**
         * F54 — Reconnect with exponential backoff and retry limit.
         * After WS_MAX_RETRIES attempts, stop trying and mark as failed.
         * The user can still use REST fallback via sendMessage.
         */
        if (sessionRef.current && reconnectAttemptRef.current < WS_MAX_RETRIES) {
          const attempt = reconnectAttemptRef.current;
          reconnectAttemptRef.current = attempt + 1;
          const delay = getBackoffDelay(attempt);

          reconnectTimerRef.current = setTimeout(() => {
            if (sessionRef.current) {
              connectWs(sessionRef.current);
            }
          }, delay);
        } else if (reconnectAttemptRef.current >= WS_MAX_RETRIES) {
          // Max retries exhausted — mark connection as failed
          setConnectionFailed(true);
          // Still mark as "ready" so REST fallback works
          setIsReady(true);
        }
      };

      ws.onerror = () => ws.close();
    } catch {
      // WebSocket unavailable -- fall back to REST only
      setIsReady(true);
    }
  }, []);

  const initSession = useCallback(async () => {
    setIsReady(false);
    setMessages([]);
    setConnectionFailed(false);
    reconnectAttemptRef.current = 0;
    try {
      const sess = await createSession(executionId);
      setSession(sess);
      sessionRef.current = sess;
      // Load existing messages from the session
      if (sess.messages && sess.messages.length > 0) {
        setMessages(sess.messages);
      }
      connectWs(sess);
    } catch {
      // If session creation fails, mark as not ready
      setIsReady(false);
    }
  }, [executionId, connectWs]);

  useEffect(() => {
    initSession();
    return () => {
      // Clean up WebSocket and reconnection timer
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current);
        reconnectTimerRef.current = null;
      }
      socketRef.current?.close();
      socketRef.current = null;
    };
  }, [initSession]);

  const sendMessage = useCallback(
    (content: string) => {
      if (!session || !content.trim() || content.length > 10000) return;

      const userMsg: ChatMessage = {
        id: `local-${Date.now()}`,
        role: 'user',
        content,
        createdAt: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, userMsg]);
      setIsThinking(true);

      const ws = socketRef.current;
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ message: content }));
      } else {
        // Fallback to REST (always available even when WS is down)
        sendMessageRest(session.id, content)
          .then((resp) => {
            setIsThinking(false);
            setMessages((prev) => [...prev, resp]);
          })
          .catch(() => setIsThinking(false));
      }
    },
    [session]
  );

  const resetSession = useCallback(() => {
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
    socketRef.current?.close();
    socketRef.current = null;
    initSession();
  }, [initSession]);

  return { messages, isThinking, isReady, connectionFailed, sendMessage, resetSession };
}
