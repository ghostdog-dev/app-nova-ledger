import { create } from 'zustand';

export type NotificationType =
  | 'execution_completed'
  | 'execution_failed'
  | 'token_expired'
  | 'anomaly_detected'
  | 'quota_exceeded';

export interface AppNotification {
  id: string;
  type: NotificationType;
  title: string;
  message: string;
  executionId?: string;
  read: boolean;
  createdAt: string;
}

interface NotificationState {
  notifications: AppNotification[];
  unreadCount: number;
  /** Toast queue — newest first, auto-dismissed by ToastContainer */
  toastQueue: AppNotification[];

  addNotification: (n: Omit<AppNotification, 'id' | 'read' | 'createdAt'>) => AppNotification;
  markRead: (id: string) => void;
  markAllRead: () => void;
  dismiss: (id: string) => void;
  dequeueToast: (id: string) => void;
}

export const useNotificationStore = create<NotificationState>()((set) => ({
  notifications: [],
  unreadCount: 0,
  toastQueue: [],

  addNotification: (n) => {
    const notification: AppNotification = {
      ...n,
      id: `notif-${Date.now()}-${Math.random().toString(36).slice(2)}`,
      read: false,
      createdAt: new Date().toISOString(),
    };
    set((state) => ({
      notifications: [notification, ...state.notifications].slice(0, 100),
      unreadCount: state.unreadCount + 1,
      toastQueue: [notification, ...state.toastQueue].slice(0, 5),
    }));
    return notification;
  },

  markRead: (id) =>
    set((state) => {
      const notifications = state.notifications.map((n) =>
        n.id === id && !n.read ? { ...n, read: true } : n
      );
      return { notifications, unreadCount: notifications.filter((n) => !n.read).length };
    }),

  markAllRead: () =>
    set((state) => ({
      notifications: state.notifications.map((n) => ({ ...n, read: true })),
      unreadCount: 0,
    })),

  dismiss: (id) =>
    set((state) => {
      const notifications = state.notifications.filter((n) => n.id !== id);
      return {
        notifications,
        unreadCount: notifications.filter((n) => !n.read).length,
        toastQueue: state.toastQueue.filter((n) => n.id !== id),
      };
    }),

  dequeueToast: (id) =>
    set((state) => ({ toastQueue: state.toastQueue.filter((n) => n.id !== id) })),
}));
