import { useState, useEffect } from 'react';
import { Outlet } from 'react-router-dom';
import { Sidebar } from '@/components/layout/sidebar';
import { Header } from '@/components/layout/header';
import { NotificationListener } from '@/components/notifications/notification-listener';
import { ToastContainer } from '@/components/notifications/toast-container';
import { QuotaExceededListener } from '@/components/notifications/quota-exceeded-toast';
import { ChatWidget } from '@/components/chat/chat-widget';
import { useCompanyStore } from '@/stores/company-store';
import styles from './AppLayout.module.css';

export function AppLayout() {
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);
  const { fetchCompanies } = useCompanyStore();

  useEffect(() => {
    fetchCompanies();
  }, [fetchCompanies]);

  return (
    <div className={styles.container}>
      <NotificationListener />
      <QuotaExceededListener />

      <div className={styles.desktopSidebar}>
        <Sidebar />
      </div>

      {mobileSidebarOpen && (
        <div className={styles.mobileOverlay}>
          <div
            className={styles.mobileBackdrop}
            onClick={() => setMobileSidebarOpen(false)}
            aria-hidden="true"
          />
          <div className={styles.mobileSidebar}>
            <Sidebar onNavigate={() => setMobileSidebarOpen(false)} />
          </div>
        </div>
      )}

      <div className={styles.mainArea}>
        <Header onMenuToggle={() => setMobileSidebarOpen(true)} />

        <main className={styles.main} id="main-content">
          <Outlet />
        </main>
      </div>

      <ToastContainer />
      <ChatWidget />
    </div>
  );
}
