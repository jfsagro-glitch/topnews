import logging

try:
    from config.railway_config import DISABLE_PROD_SIDE_EFFECTS, APP_ENV
except (ImportError, ValueError):
    from config.config import DISABLE_PROD_SIDE_EFFECTS, APP_ENV

logger = logging.getLogger(__name__)


def guard_side_effect(action_name: str) -> bool:
    """
    Guard for potentially dangerous side effects in sandbox.
    Returns False if action should be skipped.
    """
    if DISABLE_PROD_SIDE_EFFECTS:
        logger.warning(f"Side effect '{action_name}' disabled in {APP_ENV} environment")
        return False
    return True
