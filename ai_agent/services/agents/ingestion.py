"""
Ingestion Agent — no LLM, runs normalizers per provider.

Fetches data from all connected sources and creates UnifiedTransactions.
Handles deduplication via unique constraint (user + source_type + source_id).
"""
import logging

from django.db import IntegrityError

from ai_agent.models import UnifiedTransaction
from ai_agent.services.agents.base import BaseAgent, AgentResult
from ai_agent.services.normalizers.stripe import StripeNormalizer
from ai_agent.services.normalizers.mollie import MollieNormalizer
from ai_agent.services.normalizers.paypal import PayPalNormalizer
from ai_agent.services.normalizers.bank_api import BankAPINormalizer
from ai_agent.services.normalizers.email import EmailNormalizer

logger = logging.getLogger(__name__)


class IngestionAgent(BaseAgent):
    """No LLM needed — pure Python normalizer execution."""

    def execute(self, user, context: dict) -> AgentResult:
        stats = {'created': 0, 'skipped': 0, 'errors': 0, 'per_source': {}}
        errors = []

        normalizer_configs = self._get_normalizer_configs(user)

        for source_name, config in normalizer_configs.items():
            source_stats = {'created': 0, 'skipped': 0}
            normalizer = config['normalizer']
            queryset = config['queryset']
            normalize_fn = config['normalize_fn']

            for obj in queryset:
                try:
                    ut = normalize_fn(normalizer, user, obj)
                    ut.save()
                    source_stats['created'] += 1
                except IntegrityError:
                    source_stats['skipped'] += 1  # duplicate
                except Exception as e:
                    logger.error(f'[Ingestion] Error normalizing {source_name} #{getattr(obj, "pk", "?")}: {e}')
                    stats['errors'] += 1
                    errors.append(f'{source_name}: {e}')

            stats['per_source'][source_name] = source_stats
            stats['created'] += source_stats['created']
            stats['skipped'] += source_stats['skipped']

        logger.info(f'[Ingestion] Done: {stats["created"]} created, {stats["skipped"]} skipped')
        return AgentResult(
            success=True,
            items_processed=stats['created'],
            stats=stats,
            errors=errors,
        )

    def _get_normalizer_configs(self, user) -> dict:
        configs = {}

        # Stripe charges
        try:
            from stripe_provider.models import StripeCharge
            existing_ids = set(
                UnifiedTransaction.objects.filter(user=user, source_type='stripe')
                .values_list('source_id', flat=True)
            )
            charges = StripeCharge.objects.filter(connection__user=user).exclude(
                stripe_id__in=existing_ids
            )
            if charges.exists():
                configs['stripe_charges'] = {
                    'normalizer': StripeNormalizer(),
                    'queryset': charges,
                    'normalize_fn': lambda n, u, obj: n.normalize_charge(u, obj),
                }
        except (ImportError, Exception) as e:
            logger.debug(f'[Ingestion] Stripe not available: {e}')

        # Mollie payments
        try:
            from mollie_provider.models import MolliePayment
            existing_ids = set(
                UnifiedTransaction.objects.filter(user=user, source_type='mollie')
                .values_list('source_id', flat=True)
            )
            payments = MolliePayment.objects.filter(
                connection__user=user, status__in=['paid', 'open', 'authorized']
            ).exclude(mollie_id__in=existing_ids)
            if payments.exists():
                configs['mollie_payments'] = {
                    'normalizer': MollieNormalizer(),
                    'queryset': payments,
                    'normalize_fn': lambda n, u, obj: n.normalize_payment(u, obj),
                }
        except (ImportError, Exception) as e:
            logger.debug(f'[Ingestion] Mollie not available: {e}')

        # PayPal transactions
        try:
            from paypal_provider.models import PayPalTransaction
            existing_ids = set(
                UnifiedTransaction.objects.filter(user=user, source_type='paypal')
                .values_list('source_id', flat=True)
            )
            txs = PayPalTransaction.objects.filter(
                connection__user=user
            ).exclude(paypal_id__in=existing_ids)
            if txs.exists():
                configs['paypal_transactions'] = {
                    'normalizer': PayPalNormalizer(),
                    'queryset': txs,
                    'normalize_fn': lambda n, u, obj: n.normalize_transaction(u, obj),
                }
        except (ImportError, Exception) as e:
            logger.debug(f'[Ingestion] PayPal not available: {e}')

        # Bank API transactions
        try:
            from banking.models import BankTransaction
            existing_ids = set(
                UnifiedTransaction.objects.filter(user=user, source_type='bank_api')
                .values_list('source_id', flat=True)
            )
            bank_txs = BankTransaction.objects.filter(user=user).exclude(
                powens_transaction_id__in=[int(x) for x in existing_ids if x.isdigit()]
            )
            if bank_txs.exists():
                configs['bank_api'] = {
                    'normalizer': BankAPINormalizer(),
                    'queryset': bank_txs,
                    'normalize_fn': lambda n, u, obj: n.normalize(u, obj),
                }
        except (ImportError, Exception) as e:
            logger.debug(f'[Ingestion] Bank API not available: {e}')

        # Email transactions
        try:
            from emails.models import Transaction as EmailTransaction
            existing_ids = set(
                UnifiedTransaction.objects.filter(user=user, source_type='email')
                .values_list('source_id', flat=True)
            )
            email_txs = EmailTransaction.objects.filter(
                user=user, status='complete'
            ).exclude(pk__in=[int(x.replace('email_tx_', '')) for x in existing_ids if x.startswith('email_tx_')])
            if email_txs.exists():
                configs['email'] = {
                    'normalizer': EmailNormalizer(),
                    'queryset': email_txs,
                    'normalize_fn': lambda n, u, obj: n.normalize(u, obj),
                }
        except (ImportError, Exception) as e:
            logger.debug(f'[Ingestion] Email not available: {e}')

        return configs
