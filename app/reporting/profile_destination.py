"""Shared read contract for a surfaced site's evidence destination (no writes)."""
from app.pipeline.lapse_tracking import compute_lapse_status


def site_destination(site_id, *, phase_code=None, application_reference=None):
    params = {"site_id": str(site_id), "origin": "opportunities"}
    if phase_code:
        params["phase_code"] = str(phase_code)
    if application_reference:
        params["application_reference"] = str(application_reference)
    return params


def limited_profile(site, applications):
    """Retain the same subject and authoritative anchor when display filters omit it.

    Application linkage is checked even when the caller has already scoped its
    query. This never promotes an administrative filing into substantive evidence.
    """
    own = [a for a in applications if a.site_id == site.id]
    lapse = compute_lapse_status(own, site)
    anchor = lapse.get("granted_app")
    return {
        "site_id": site.id,
        "address": site.display_address,
        "limitation": "Detailed scheme evidence is not available through the current display qualification rules. This does not invalidate the linked planning record or establish commencement, availability or legal lapse.",
        "reference": anchor.reference if anchor else None,
        "source_url": anchor.summary_url if anchor else None,
        "lapse": lapse,
    }


def origin_evidence(site_id, applications, reference=None, phase_code=None):
    """Validate the originating record within the destination subject only."""
    match = next((a for a in applications if a.site_id == site_id and a.reference == reference), None)
    return {
        "reference": match.reference if match else None,
        "source_url": match.summary_url if match else None,
        "limitation": (
            "The originating planning record is not available for this site; no substitute subject is shown."
            if reference and match is None else
            "The linked record belongs to this site. The profile below covers the wider site; phase-only evidence and physical progress are unverified."
            if phase_code else
            "The linked record belongs to this site; the profile may include other applications on the same site."
        ),
        "requested_phase": str(phase_code) if phase_code else None,
    }
