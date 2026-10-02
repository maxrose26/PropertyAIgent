"""Constrain ownership in SQL before loading private objects or autoflush."""
from sqlalchemy import select
from app.db.models import Buyer, BuyerMandate
from app.security.access import AccessDenied, require_admitted


def buyer_query():
    actor = require_admitted()
    return select(Buyer).where(Buyer.workspace_id == actor.workspace_id, Buyer.id.in_(actor.buyer_ids), Buyer.status == 'active')


def buyer_by_key(session, key):
    require_admitted()
    with session.no_autoflush:
        buyer = session.execute(buyer_query().where(Buyer.buyer_key == key)).scalar_one_or_none()
    if buyer is None:
        raise AccessDenied('Access denied.')
    require_admitted()
    return buyer


def mandate_by_id(session, mandate_id):
    actor = require_admitted()
    with session.no_autoflush:
        mandate = session.execute(select(BuyerMandate).join(Buyer, Buyer.id == BuyerMandate.buyer_id).where(Buyer.workspace_id == actor.workspace_id, Buyer.id.in_(actor.buyer_ids), BuyerMandate.id == mandate_id)).scalar_one_or_none()
    if mandate is None:
        raise AccessDenied('Access denied.')
    require_admitted()
    return mandate


def require_workspace_write(session, workspace_id, *, new_buyers=0):
    from app.security.access import require_operator
    actor=require_operator('buyer.write')
    if workspace_id != actor.workspace_id:raise AccessDenied('Access denied.')
    with session.no_autoflush:
        existing=set(session.execute(select(Buyer.id).where(Buyer.workspace_id==workspace_id)).scalars())
        used=set(session.execute(select(Buyer.id).where(Buyer.id.in_(actor.buyer_ids))).scalars())
    if not existing.issubset(actor.buyer_ids):raise AccessDenied('Access denied.')
    available=sorted(actor.buyer_ids-used)
    if len(available)<new_buyers:raise AccessDenied('Explicit buyer IDs required before creation.')
    return iter(available)


def persistent_id(row):
    from sqlalchemy import inspect
    identity=inspect(row).identity
    if not identity:raise AccessDenied('Access denied.')
    return identity[0]


def reload_shared(session, row, model):
    from app.security.access import require_operator
    actor=require_admitted()
    if actor.role != "operator":raise AccessDenied("Operator permission required.")
    with session.no_autoflush:
        result=session.execute(select(model).where(model.id==persistent_id(row)).execution_options(populate_existing=True)).scalar_one_or_none()
    if result is None:raise AccessDenied('Access denied.')
    return result
