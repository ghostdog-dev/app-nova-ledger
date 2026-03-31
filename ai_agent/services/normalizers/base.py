from ai_agent.models import UnifiedTransaction


class BaseNormalizer:
    """
    All normalizers return unsaved UnifiedTransaction instances.
    The caller is responsible for saving (allows dedup checks first).
    """

    def _build(self, user, **kwargs) -> UnifiedTransaction:
        """Create an unsaved UnifiedTransaction with the given fields."""
        return UnifiedTransaction(user=user, **kwargs)
