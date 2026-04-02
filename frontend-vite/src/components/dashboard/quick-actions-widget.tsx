import { useTranslation } from 'react-i18next';
import { PlaySquare, Link2, Settings, History } from 'lucide-react';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import styles from './quick-actions-widget.module.css';
import { useNavigate } from 'react-router-dom';

interface QuickActionsWidgetProps {
  onAddConnection: () => void;
}

export function QuickActionsWidget({ onAddConnection }: QuickActionsWidgetProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();

  const actions = [
    {
      label: t('dashboard.startExecution'),
      icon: <PlaySquare className={styles.iconMd} aria-hidden="true" />,
      onClick: () => navigate('/executions'),
      variant: 'primary' as const,
    },
    {
      label: t('connections.addConnection'),
      icon: <Link2 className={styles.iconMd} aria-hidden="true" />,
      onClick: onAddConnection,
      variant: 'secondary' as const,
    },
    {
      label: t('executions.title'),
      icon: <History className={styles.iconMd} aria-hidden="true" />,
      onClick: () => navigate('/executions'),
      variant: 'ghost' as const,
    },
    {
      label: t('settings.title'),
      icon: <Settings className={styles.iconMd} aria-hidden="true" />,
      onClick: () => navigate('/settings'),
      variant: 'ghost' as const,
    },
  ];

  return (
    <Card padding="md">
      <CardHeader>
        <CardTitle>Actions rapides</CardTitle>
      </CardHeader>
      <CardContent>
        <div className={styles.grid}>
          {actions.map((action) => (
            <Button
              key={action.label}
              variant={action.variant}
              size="sm"
              onClick={action.onClick}
              leftIcon={action.icon}
              className={styles.actionBtn}
              fullWidth
            >
              <span className={styles.actionLabel}>{action.label}</span>
            </Button>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
