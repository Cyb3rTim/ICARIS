"""Structured audit trail for record changes (AU-2 / AU-3 style events)."""
import logging

logger = logging.getLogger("icaris.audit")


def record(request, action: str, obj) -> None:
    """Log who changed what, from where. Never logs field contents."""
    user = getattr(request, "user", None)
    logger.info(
        "action=%s model=%s id=%s user=%s ip=%s",
        action,
        obj._meta.model_name,
        getattr(obj, "pk", None),
        getattr(user, "username", "anonymous"),
        request.META.get("REMOTE_ADDR", "-"),
    )
