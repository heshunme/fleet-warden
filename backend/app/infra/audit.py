from sqlalchemy.orm import Session

from app.persistence.models import AuditLog


def record_audit(
    db: Session,
    *,
    entity_type: str,
    entity_id: int,
    event_type: str,
    payload: dict,
    operator_id: str = "operator",
) -> AuditLog:
    audit = AuditLog(
        entity_type=entity_type,
        entity_id=entity_id,
        event_type=event_type,
        payload=payload,
        operator_id=operator_id,
    )
    db.add(audit)
    db.flush()
    return audit

