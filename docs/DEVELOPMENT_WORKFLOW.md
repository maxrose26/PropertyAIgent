# PropertyAIgent Development Workflow

Status: **Binding engineering workflow for authorised development**

## Purpose

GitHub is the durable source of truth for PropertyAIgent engineering history. Temporary agent workspaces and local worktrees are disposable. A REVIEW-ready or accepted implementation candidate must never exist only in a temporary/local environment.

This workflow governs engineering process only. It does not itself authorise implementation, merge, deployment, production access, database changes, model calls or operational activation.

## 1. Start every authorised implementation from an exact remote base

Before substantial implementation begins:

1. Confirm the exact REVIEW-approved integration-base commit.
2. Refresh the remote repository state.
3. Create/use a dedicated feature branch for the authorised workstream.
4. Confirm authenticated native Git publication to that remote branch is available.

If genuine Git publication is unavailable, resolve or report that capability **before substantial implementation proceeds**. Do not defer publication capability until final acceptance.

Never implement directly on `master`.

## 2. GitHub durability rule

Local investigation, experiments and intermediate edits are allowed.

Once a coherent implementation checkpoint exists, publish the **genuine Git history** to the dedicated remote feature branch. For substantial work, continue pushing coherent checkpoints so accepted engineering history is not stranded in an ephemeral environment.

Before DEVELOPMENT reports a candidate as implementation-complete or REVIEW-ready, verify:

- the exact reported commit exists on GitHub;
- the remote tree equals the tested tree;
- parentage is correct;
- the remote branch contains no unexpected commits;
- the remote diff matches the authorised scope;
- a review PR can be created from that genuine history.

A local-only commit is not a completed REVIEW candidate.

## 3. Preserve genuine history

Do not reconstruct replacement commits through an API merely to recover from late publication failure unless REVIEW explicitly authorises replacement history.

Do not silently squash, rebase, amend or cherry-pick an accepted candidate into a different identity.

If exact-history recovery is genuinely required, stop and use a separately reviewed recovery route.

## 4. Branch, PR, merge and release are separate authorities

These actions are distinct:

- **Feature-branch publication** makes development history durable.
- **Pull-request creation** enables review and hosted verification.
- **Merge** integrates accepted work into `master`.
- **Production deployment** changes the live application.
- **Operational activation** may start ingestion, monitoring, scheduled processing or other production activity.

Authority for one does not imply authority for the next.

A pushed branch is not merge authority. A PR is not merge authority. A merge is not deployment authority. Deployment is not cron/operational activation authority.

Follow the current REVIEW decision for every gated transition.

## 5. Hosted verification must test the actual candidate

Hosted CI must run against the genuinely published candidate proposed for integration.

Local tests remain valuable evidence but do not substitute for required hosted verification.

Do not alter, skip, xfail, deselect, weaken or retarget a required gate merely to obtain a pass. Any intentional evolution of a frozen contract requires explicit REVIEW authority and preserved historical provenance.

## 6. Workstream isolation

Keep separately gated workstreams separate unless REVIEW explicitly authorises integration.

In particular, P0-A/AH work, Stage 2.x slices, security/access work and operational activation must not be bundled merely for convenience.

Do not pull later-roadmap features into an authorised slice without a demonstrated dependency and REVIEW approval.

## 7. Sensitive material must never enter Git

Never commit:

- passwords, tokens, API keys or connection strings;
- production credentials or secret-bearing environment files;
- private database exports;
- unnecessary personal information;
- sensitive evidence artifacts that are not explicitly approved for repository retention.

Use approved secret-storage and evidence-handling mechanisms.

## 8. Completion reporting

Every implementation completion report must distinguish:

- implemented and tested;
- published remotely;
- hosted-CI verified;
- merged;
- deployed;
- production-verified;
- proposed or blocked.

Report exact commit/tree/base identities and relevant test results.

Do not describe local acceptance as hosted or production acceptance.

## 9. Failure handling

Routine implementation/test failures should be remediated autonomously within the authorised scope.

Return to REVIEW when a genuine product, architecture, security, release or scope decision is required.

Publication/authentication capability failures discovered after substantial implementation are process failures to avoid, not a normal release step.

## 10. Agent preflight

Before beginning future authorised implementation, the coding agent must read this document and confirm internally that:

- the approved base is known;
- the feature branch/workstream is correct;
- remote publication is available;
- the work can remain within the authorised scope;
- required release gates are understood.

Temporary agent worktrees are disposable. **Durable accepted PropertyAIgent engineering history belongs on GitHub.**
