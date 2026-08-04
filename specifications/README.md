# Specifications

This folder is the specification workflow for PropertyAIgent.

## Purpose

Every major feature begins as a Specification, not as code.

A specification is a short document that explains **what** we are building and **why**, before any implementation work starts. It intentionally describes the product and the architecture first - the data model, the user experience, the acceptance criteria - so that implementation is a translation of an already-agreed design, not the place where the design actually happens.

## How this works

- Before writing code for a significant feature, Claude should read the relevant specification in this folder.
- If no specification exists for the feature being requested, Claude should stop and ask for one to be written before implementing.
- Implementation should follow the specification, not reinterpret it. If the specification turns out to be wrong or incomplete once work starts, the specification should be updated first, and the implementation should follow from that update - not silently diverge from it.
- Specifications are the long-term source of truth for PropertyAIgent. Code changes; the specification is where the reasoning behind it is preserved.

## Numbering and naming

- `000-template.md` is the reusable template every new specification is copied from.
- Specifications are numbered sequentially (`001-`, `002-`, ...) in the order they were written, e.g. `001-platform-vision.md`.
- File names are short, lowercase, and hyphenated after the number.

## What belongs here

Specifications for anything that changes what PropertyAIgent does or how it's structured - a new intelligence layer, a new data source, a change to the core data model, a new user-facing capability. Not every code change needs one (a bug fix or a small refactor doesn't), but anything that a future contributor would need context to understand the "why" of should have one.
