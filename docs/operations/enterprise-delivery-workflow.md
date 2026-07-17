# MT Presence Enterprise Delivery Workflow

## 1. Purpose

This workflow governs every product, design, engineering, review, and release task for MT Presence. Its purpose is to produce an internationally credible photography platform that is visually distinctive, operationally safe, accessible, secure, measurable, and maintainable.

The product specification remains authoritative for product behavior. This document defines **how work is executed and accepted**.

## 2. Non-negotiable principles

- Photography leads; interface chrome supports viewing and work completion.
- Public pages feel editorial, quiet, image-led, and culturally credible.
- Workspace and Admin pages feel precise, dense, calm, and operational—not promotional.
- Every state has one authoritative server-side source.
- Security and permissions are enforced by APIs, never by hidden UI alone.
- Every visible feature covers its relevant loading, empty, error, success, disabled, permission, offline, dirty, and conflict states.
- Every change is delivered as a small vertical slice with measurable acceptance criteria.
- No task is “done” because it looks good in one screenshot.
- User-facing UI, code identifiers, API fields, database fields, events, and implementation comments use English.
- Product/design documentation may use Chinese for team communication.

## 3. Definition of international enterprise quality

A release passes only when all applicable dimensions meet their gate:

| Dimension | Required evidence |
| --- | --- |
| Brand | Consistent typography, spacing, image treatment, tone, and terminology across public/product/admin surfaces. |
| UX | Primary task is obvious; navigation is predictable; destructive actions explain impact; recovery paths exist. |
| Responsive | Verified at 1440×1000 and 390×844; no overlap, clipping, hidden actions, or forced desktop layout. |
| Accessibility | Keyboard completion, visible focus, semantic labels, error association, dialog focus management, useful alt text, reduced motion. |
| Performance | Responsive images, bounded asset sizes, stable layout, no unnecessary blocking scripts, measured Core Web Vitals before production. |
| Security | Server-side ownership/RBAC, MFA for admins, secure sessions, CSRF/XSS controls, upload validation, no sensitive-field leakage. |
| Data integrity | Explicit schema, migrations, constraints, immutable review/audit records, optimistic concurrency, backup/restore test. |
| Reliability | Observable request IDs, predictable errors, retries where safe, idempotency for high-risk mutations, monitoring and alerts. |
| Compliance | Rights declarations, EXIF/GPS privacy, releases, takedown/escalation, retention/legal hold, auditable decisions. |
| Maintainability | Existing architecture reused, responsibilities documented, tests updated, no duplicate state or component systems. |
| Internationalization | UTF-8, locale/timezone-aware dates, translatable UI structure, no layout assumptions tied to short English labels. |
| SEO/public trust | Correct metadata, canonical URLs, structured data where appropriate, accessible public content, clear contact/privacy/legal paths. |

## 4. Delivery pipeline

```text
Intake
  -> Context and risk audit
  -> Reference research
  -> Prompt contract
  -> Vertical slice plan
  -> Design states
  -> Implementation
  -> Automated verification
  -> Browser and accessibility review
  -> Security/data review
  -> Release gate
  -> Production observation
  -> Retrospective and documentation
```

Only one stage may be the active delivery stage. A failed gate returns work to the earliest stage that caused the failure.

## 5. Stage gates

### Gate 0 — Intake

Input:

- User request, business reason, affected users, urgency, and known constraints.

Required output:

- Goal.
- Non-goals.
- Affected route, feature, data, roles, and environments.
- Success metric or observable acceptance condition.
- Risk class: low, medium, high, or critical.

Stop when:

- The request conflicts with the product specification.
- A missing choice would materially change user rights, security, data retention, publishing, or legal behavior.

### Gate 1 — Context and risk audit

Read before editing:

- `docs/product/user-upload-admin-spec.md`
- `docs/design/design-system.md`
- `docs/architecture/project-map.md`
- Relevant neighboring code, schema, API, styles, and tests.

Required output:

- Existing patterns to reuse.
- Files expected to change.
- State ownership and permission boundary.
- Risks: security, privacy, data loss, concurrency, accessibility, performance, responsive layout.

Pass condition:

- No proposed second architecture, request layer, component system, or writable state source.

### Gate 2 — Reference research

For every Web/UI task:

1. Search real shipped products by the exact pattern: gallery navigation, upload queue, review detail, audit table, empty state, conflict dialog, etc.
2. Prefer complete flows and component patterns over isolated visual shots.
3. Record three useful principles, not copied pixels.
4. Identify one anti-pattern to avoid.
5. Verify recommendations are current when tools, standards, browsers, vendors, laws, or platform behavior may have changed.

Suggested sources:

- Mobbin and Page Flows for real product flows.
- Refero, SaaSFrame, and Checklist Design for pattern research.
- Awwwards, SiteInspire, museum archives, galleries, and editorial photography publications for public-site art direction.
- W3C/WAI, MDN, web.dev, OWASP, provider documentation, and framework documentation for technical decisions.

Pass condition:

- Research findings are translated into project-specific principles and do not conflict with the design system.

### Gate 3 — Prompt contract

Before UI implementation, create a page-specific English prompt using the master prompt in section 7.

The prompt must state:

- Page goal and primary user task.
- Information hierarchy and content priority.
- Visual direction and image role.
- Components and interaction behavior.
- All applicable states.
- Desktop/mobile/accessibility behavior.
- Explicit avoid list.
- Acceptance criteria.

Pass condition:

- Another designer or agent could implement the same intent without guessing what “premium,” “beautiful,” or “enterprise” means.

### Gate 4 — Vertical slice plan

Each slice must produce usable value across UI, data, permissions, errors, tests, and documentation.

Required output:

- Scope and non-scope.
- Files and existing modules reused.
- API/data contracts.
- Acceptance criteria.
- Verification commands and browser scenarios.
- Rollback/recovery approach for medium-or-higher risk changes.

Maximum preferred slice:

- One user journey, one page, or one coherent API workflow.

### Gate 5 — Design states

Design the normal path and every relevant boundary before implementation:

- Loading and progressive loading.
- Empty and first-use.
- Partial failure and retry.
- Validation and server error.
- Success and saved state.
- Disabled with explanation.
- Permission denied without data leakage.
- Offline/unsynchronized.
- Dirty/autosaving/save failed.
- Conflict with Reload/Compare.
- Destructive confirmation and recovery.

Pass condition:

- No important behavior exists only as an unhandled alert, console message, or invisible state.

### Gate 6 — Implementation

Rules:

- Make the smallest coherent change.
- Reuse current tokens, components, API patterns, helpers, and schemas.
- Keep business rules outside presentation-only event handlers.
- Escape/sanitize user content at output boundaries.
- Preserve a single writable state source.
- Use optimistic concurrency for editable server data.
- Add idempotency for review, publication, takedown, quota, and role mutations.
- Do not silently broaden permissions or public data exposure.
- Update `docs/architecture/project-map.md` in the same slice.

### Gate 7 — Automated verification

Run the narrowest relevant checks first, then broader checks in proportion to risk:

```text
format/static checks
  -> syntax/typecheck
  -> unit tests
  -> database/migration validation
  -> API integration tests
  -> targeted E2E
  -> build
```

Minimum current-repository checks where applicable:

```bash
python3 scripts/validate_product_phase0.py
python3 scripts/validate_local_archive_db.py
python3 -m py_compile server.py scripts/*.py
node --check <changed-javascript-file>
git diff --check
```

Pass condition:

- New failures are fixed. Existing unrelated failures are documented with evidence and impact.

### Gate 8 — Browser and accessibility review

For every Web/UI change:

- Open the real page through the local server.
- Capture and inspect 1440×1000 and 390×844.
- Exercise hover, focus-visible, active, disabled, error, empty, and dialog states as applicable.
- Complete the primary workflow using keyboard only.
- Check long text, localization expansion, image failure, slow response, and no-data behavior.
- Confirm no console errors and no failed required network requests.
- Check reduced motion and 200% zoom for critical flows.

Pass condition:

- The review has evidence (screenshots, browser observations, or automated E2E results), not only source-code inspection.

### Gate 9 — Security and data review

Mandatory for auth, upload, review, admin, publishing, exports, user management, and deletion:

- Verify authentication and server-side authorization.
- Test horizontal and vertical privilege escalation.
- Verify CSRF/XSS controls and sensitive-field filtering.
- Verify upload MIME/magic/decode/size/scan behavior.
- Verify transaction and concurrency behavior.
- Verify audit event, actor, reason, request ID, policy version, and before/after data.
- Verify public API immediately excludes unpublished/quarantined/deleted work.

Critical failures block release.

### Gate 10 — Release readiness

Required evidence:

- Acceptance criteria checked.
- Database migration forward and rollback/restore strategy reviewed.
- Environment configuration documented without committing secrets.
- Monitoring/alerts and request IDs ready.
- Backup and recovery impact understood.
- Changelog/release note prepared where applicable.
- Feature flag or controlled rollout used for risky changes.
- Product, design, architecture, operation, and project-map documentation consistent.

### Gate 11 — Production observation

After release:

- Monitor errors, latency, upload failures, review queue health, publication failures, permission denials, and storage processing.
- Validate one synthetic critical journey.
- Compare outcomes with the success metric.
- Roll back or disable when defined thresholds are exceeded.

### Gate 12 — Retrospective

Record:

- What changed and why.
- Unexpected behavior or failure.
- Reusable pattern discovered.
- Tests or guardrails added.
- Follow-up work and owner.

Update existing authoritative documents instead of creating duplicate completion reports.

## 6. Operating roles

Every medium/high-risk slice must be reviewed through these perspectives, even when one person performs them:

| Perspective | Primary question |
| --- | --- |
| Product owner | Does this solve the specified user problem without adding conflicting scope? |
| Art director | Does the interface strengthen the photography and brand rather than compete with it? |
| UX designer | Is the task, hierarchy, feedback, recovery, and responsive behavior clear? |
| Accessibility reviewer | Can users perceive, understand, navigate, and complete it without a mouse? |
| Frontend engineer | Is rendering predictable, responsive, performant, and maintainable? |
| Backend/data engineer | Are contracts, ownership, consistency, concurrency, and migrations correct? |
| Security/privacy reviewer | Can permissions be bypassed or private/sensitive data leak? |
| QA/release owner | Is there reproducible evidence that acceptance criteria pass? |

The implementation author cannot waive a failed critical security, privacy, data-loss, or accessibility gate.

## 7. Master prompt

Copy this prompt and replace every bracketed field before a Web/UI task:

```text
You are the senior product designer, art director, accessibility specialist, and frontend architect for MT Presence, an international fine-art photography platform.

TASK
Design and implement [PAGE / FEATURE] for [PRIMARY USER]. The primary job is: [ONE SENTENCE USER OUTCOME].

PRODUCT CONTEXT
- Public product: editorial, quiet, image-led, culturally credible.
- Workspace/Admin product: precise, calm, dense, operational, highly scannable.
- Product behavior must follow docs/product/user-upload-admin-spec.md.
- Visual and interaction behavior must follow docs/design/design-system.md.
- Reuse the current architecture documented in docs/architecture/project-map.md.
- User-facing UI, code, API fields, database fields, events, and implementation comments use English.

INFORMATION PRIORITY
1. [PRIMARY CONTENT / ACTION]
2. [SECONDARY CONTENT / ACTION]
3. [TERTIARY OR SUPPORTING CONTENT]
Remove or demote anything that does not support these priorities.

VISUAL DIRECTION
- [3–5 concrete adjectives tied to the brand]
- Typography: [families / hierarchy / density / line length]
- Color: [surface, text, border, accent, semantic colors]
- Photography role: [crop, aspect behavior, prominence, captions, metadata]
- Spacing: [compact/editorial; explicit density goal]
- Motion: [single restrained motion language; reduced-motion behavior]

LAYOUT
- Desktop [TARGET VIEWPORT]: [regions, columns, sticky/fixed behavior, max widths].
- Mobile [TARGET VIEWPORT]: [normal-flow transformation, navigation, primary action placement].
- Components: [LIST].
- State ownership: [URL / local UI / server cache / server database].

INTERACTION AND STATES
Design applicable loading, empty, error, partial failure, success, disabled, permission, offline, dirty, autosave, conflict, destructive confirmation, and recovery states.
Every action must have immediate feedback and a predictable result.

ACCESSIBILITY
- Semantic HTML and programmatic labels.
- Complete keyboard workflow and logical focus order.
- Visible focus; focus trap and restoration for dialogs.
- Errors associated with fields and announced where needed.
- Text and essential controls meet WCAG 2.2 AA contrast.
- 200% zoom, reduced motion, long text, and missing-image behavior remain usable.

SECURITY AND DATA
- Enforce ownership and roles on the server.
- Do not expose private asset URLs, tokens, release documents, internal notes, or sensitive EXIF.
- Define validation, concurrency, idempotency, audit, and error contracts where applicable.

AVOID
- Generic AI-generated SaaS dashboard aesthetics.
- Decorative hero sections inside workspaces/admin pages.
- Excessive cards, rounded containers, gradients, glassmorphism, shadows, pills, badges, and animation.
- Tiny low-contrast text, icon-only actions without names, hidden critical actions, layout shifts, and desktop layouts compressed onto mobile.
- New component systems, request clients, stores, or writable state sources when existing patterns can be reused.
- Any claim that the feature is complete without browser and test evidence.

REFERENCE RESEARCH
Study [3 RELEVANT REAL PRODUCTS / PATTERNS]. Extract principles, not pixels. Explain which principles are adopted and which are rejected for MT Presence.

ACCEPTANCE CRITERIA
- [VISIBLE USER OUTCOME]
- [STATE / FAILURE OUTCOME]
- [PERMISSION / DATA OUTCOME]
- [DESKTOP / MOBILE OUTCOME]
- [ACCESSIBILITY OUTCOME]
- [PERFORMANCE OUTCOME]
- [TEST COMMANDS]
- docs/architecture/project-map.md is updated.

DELIVERY FORMAT
1. State goal, non-goals, risks, reused patterns, and affected files.
2. Show the completed page-specific design prompt before implementation.
3. Implement the smallest complete vertical slice.
4. Run automated checks and real browser review at desktop and mobile sizes.
5. Self-review against product, design, accessibility, security, data, and maintainability gates.
6. Report completed work, evidence, remaining risk, and the next safe slice without overstating completion.
```

## 8. Prompt quality checklist

Reject and rewrite the prompt if any answer is “no”:

- Does it name one primary user outcome?
- Does it distinguish public editorial UI from operational workspace/admin UI?
- Are information hierarchy and image role explicit?
- Are desktop and mobile transformations specified?
- Are relevant non-happy-path states listed?
- Are accessibility and keyboard requirements testable?
- Are permission/data boundaries explicit?
- Does the avoid list prevent generic AI styling?
- Are references pattern-specific?
- Are acceptance criteria observable?
- Are implementation and verification bounded to one slice?

## 9. Task record template

Use this lightweight record in the working conversation or issue:

```text
Goal:
Non-goals:
Primary user/outcome:
Risk class:
Authoritative requirements:
Existing patterns reused:
Reference findings:
Page-specific prompt:
Slice scope:
Acceptance criteria:
Files expected:
Verification plan:
Rollback/recovery:
Documentation update:
```

## 10. Release scorecard

Score each applicable dimension 0–2:

- 0: missing or failed.
- 1: present but incomplete or weakly evidenced.
- 2: complete with evidence.

Dimensions: product fit, visual/brand, UX states, responsive, accessibility, performance, security, data integrity, reliability, compliance/privacy, maintainability, internationalization, SEO/public trust, tests, documentation.

Rules:

- Any 0 blocks release.
- Security, privacy, data integrity, permissions, and destructive recovery must each score 2.
- Production release requires at least 27/30 and no waived critical finding.
- A prototype may ship internally with a lower score only when clearly labeled, access-restricted, and tracked with explicit gaps.

## 11. Current program sequence

Use the product specification phases as the program backlog:

1. Phase 0 — schema, provider boundaries, remove conflicting public responsibilities.
2. Phase 1 — Supabase Auth, verified users, protected Workspace, role guards, admin MFA.
3. Phase 2 — server drafts, folders, uploads, processing, autosave, quota, scanning.
4. Phase 3 — immutable submissions, assignment, review decisions, notifications, publication.
5. Phase 4 — all-images/users operations, unpublish, quarantine, takedown, audit.
6. Phase 5 — security hardening, monitoring, backup/restore, retention, accessibility, load and security testing.

Do not start a later phase by weakening an earlier phase’s ownership, permission, state, or audit boundary.
