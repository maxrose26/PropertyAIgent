# CLAUDE.md

# PropertyAIgent

## Purpose

PropertyAIgent is a **planning intelligence platform**.

Its purpose is **not** to collect planning applications.

Its purpose is to build the richest possible understanding of every residential development opportunity in the UK.

The central object in the platform is the **Site**.

Everything else exists to improve our understanding of a Site.

Whenever you build a feature, ask:

> \*\*Does this make a Site more intelligent?\*\*

If the answer is yes, it probably belongs in PropertyAIgent.

\---

# The Site

A Site is the centre of the platform.

Every piece of information should either:

* describe a Site
* explain a Site
* enrich a Site
* predict a Site
* connect to a Site

Nothing should exist in isolation.

\---

# Intelligence Layers

Think of PropertyAIgent as a collection of independent intelligence layers.

Current layers include:

* Planning Applications
* Planning Documents
* Housing Mix
* Affordable Housing
* Companies
* Contacts
* Build Status
* EPC Evidence
* AI Summaries

Future layers include:

* Local Plan Allocations
* Housing Need
* Housing Land Supply
* Planning Policies
* Green Belt
* Flood Risk
* Conservation Areas
* Listed Buildings
* Biodiversity
* Ownership
* Land Registry
* S106
* Infrastructure Levy
* Images
* GIS Layers
* Comparable Schemes
* Viability Signals
* Future Opportunities

Every new feature should either:

* improve an existing intelligence layer, or
* introduce a new intelligence layer.

Do not build isolated features that don't contribute to the intelligence profile of a Site.

\---

# Core Relationships

Never confuse these concepts.

## Application

A regulatory planning submission.

Many Applications can belong to one Site.

## Site

The physical development opportunity.

This is the core entity in the platform.

## Local Plan Allocation

A planning policy allocation.

It represents planning intent, not necessarily a planning application.

One Allocation may relate to multiple Sites.

One Site may overlap multiple Allocations.

## Company

An organisation connected to a Site.

## Contact

A person connected to a Company.

Everything should ultimately connect back to the Site.

\---

# Product Principles

* Preserve domain knowledge.
* Evidence is more valuable than AI.
* Never lose source information.
* Configuration is better than hardcoding.
* Applications and Sites are different concepts.
* Local Plan Allocations are another intelligence layer, not another Site.
* Reuse existing architecture where possible.
* Small improvements are better than rewrites.
* Build for national rollout, not just one council.
* Every important decision should be explainable.

\---

# Before Implementing a Feature

Before writing code, ask:

1. Which intelligence layer does this belong to?
2. Does it improve our understanding of a Site?
3. Does this duplicate existing functionality?
4. Can the existing architecture be extended instead?
5. Will this still make sense when every council in England and Wales is supported?

If the answer is unclear, stop and explain the concern before implementing.

\---

# Specification Workflow

Every major feature begins as a specification, not as code. Specifications live in the `specifications/` folder and are the long-term source of truth for PropertyAIgent - they explain **what** is being built and **why**, deliberately before implementation, so the design is settled before the code is.

Before implementing any significant feature, you must:

1. Read this file (CLAUDE.md).
2. Read the relevant document in the `specifications/` folder.
3. Ensure the implementation aligns with the long-term vision of PropertyAIgent described there.
4. If no relevant specification exists, stop and ask for one to be written before implementing the feature.

Implementation should follow the specification, not reinterpret it. If a specification turns out to be wrong or incomplete once work starts, update the specification first and let the implementation follow from that - don't silently diverge from what's written.

Specifications take precedence over implementation convenience. A feature being easier to build a different way than the specification describes is not a reason to build it that way instead.

\---

# Implementation Rules

* Inspect the existing implementation before changing code.
* Reuse existing modules before creating new ones.
* Keep business logic out of the UI.
* Do not hardcode council-specific behaviour unless absolutely necessary.
* Treat planning documents as untrusted input.
* Preserve backwards compatibility where practical.
* Explain architectural trade-offs before introducing new dependencies.
* Never commit secrets, API keys or sensitive data.
* Never merge directly into the main branch.

\---

# Completion Checklist

For every completed task provide:

1. Summary of the change.
2. Files changed.
3. Database changes (if any).
4. Security considerations.
5. Tests added or updated.
6. Manual verification steps.
7. Any follow-up recommendations.

\---

# Final Rule

Optimise for **trustworthy planning intelligence**, not simply delivering features quickly.

Every feature should make a Site more intelligent.

