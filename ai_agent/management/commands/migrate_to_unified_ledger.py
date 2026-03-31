"""
One-time migration: convert existing provider data to UnifiedTransactions.
Idempotent — can run multiple times safely (unique constraint prevents duplicates).
Usage: python manage.py migrate_to_unified_ledger [--user EMAIL]
"""
import logging
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from ai_agent.services.agents.ingestion import IngestionAgent

logger = logging.getLogger(__name__)
User = get_user_model()


class Command(BaseCommand):
    help = 'Migrate existing provider data to UnifiedTransaction ledger'

    def add_arguments(self, parser):
        parser.add_argument('--user', type=str, help='Migrate only this user (email)')

    def handle(self, *args, **options):
        if options.get('user'):
            users = User.objects.filter(email=options['user'])
        else:
            users = User.objects.all()

        agent = IngestionAgent()

        for user in users:
            self.stdout.write(f'Migrating data for {user.email}...')
            result = agent.execute(user, context={})
            self.stdout.write(
                f'  Created: {result.stats.get("created", 0)}, '
                f'Skipped: {result.stats.get("skipped", 0)}, '
                f'Errors: {len(result.errors)}'
            )
            if result.errors:
                for err in result.errors[:5]:
                    self.stdout.write(self.style.WARNING(f'  Error: {err}'))

        self.stdout.write(self.style.SUCCESS('Migration complete.'))
