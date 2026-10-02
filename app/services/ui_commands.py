"""Existing UI mutations, with server checks before querying or changing data."""
import datetime as dt
from sqlalchemy import select
from app.db.models import Application, ApplicationCompany, Contact, Settings, Site
from app.security.access import AccessDenied, require_operator


from app.security.commands import command

@command('credits.write')
def add_credits(session, amount):
    require_operator('credits.write')
    if isinstance(amount,bool) or not isinstance(amount,int) or amount <= 0:
        raise ValueError('Credits must be a positive integer')
    settings = session.get(Settings,1)
    if settings is None: raise ValueError('Settings unavailable')
    settings.credits_remaining += amount
    require_operator('credits.write')
    session.commit()


@command('site.exclude')
def set_site_exclusion(session, site_id, excluded, reason=None):
    require_operator('site.exclude')
    site = session.get(Site,site_id)
    if site is None: raise AccessDenied('Access denied.')
    site.excluded = bool(excluded)
    site.excluded_reason = (reason or None) if excluded else None
    site.excluded_at = dt.datetime.now(dt.timezone.utc) if excluded else None
    require_operator('site.exclude')
    session.commit()


@command('matching.write')
def relink_site_applications(session, site_id, parent_ref):
    require_operator('matching.write')
    site = session.get(Site,site_id)
    if site is None: raise AccessDenied('Access denied.')
    target = session.execute(select(Application).where(Application.council_code == site.council_code, Application.reference == parent_ref.strip())).scalar_one_or_none()
    if not target: return 'error', f'No application {parent_ref!r} found for {site.council_code} - it needs to already be scraped.'
    if not target.site_id: return 'error', f"{parent_ref} exists but isn't linked to a site itself yet - can't merge into it."
    if target.site_id == site.id: return 'warning', 'That application is already part of this same site.'
    for application in site.applications:
        application.site_id = target.site_id
        application.site_link_method = 'manual'
    require_operator('matching.write')
    session.commit()
    return 'success', f"Linked to {parent_ref}'s site."


@command('contacts.write')
def save_contacts(session, site_id, company_id, changes):
    require_operator('contacts.write')
    with session.no_autoflush:
        linked = session.execute(select(ApplicationCompany.id).join(Application,Application.id == ApplicationCompany.application_id).where(Application.site_id == site_id,ApplicationCompany.company_id == company_id)).first()
        if not linked: raise AccessDenied('Access denied.')
        contacts = session.execute(select(Contact).where(Contact.company_id == company_id, Contact.id.in_(changes))).scalars().all()
    if len(contacts) != len(changes): raise AccessDenied('Access denied.')
    for contact in contacts:
        status,suppressed = changes[contact.id]
        if status not in ('not_contacted','contacted','interested','rejected') or not isinstance(suppressed,bool):
            raise ValueError('Invalid contact change')
    for contact in contacts:
        contact.outreach_status,contact.suppressed=changes[contact.id]
    require_operator('contacts.write')
    session.commit()
