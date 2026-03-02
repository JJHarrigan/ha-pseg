# PSEG Long Island Integration — Auth Refresh Stabilization Plan

**Date:** 2026-03-02  
**Goal:** eliminate recurring manual cookie intervention and make auth recovery automatic.

---

## Problem Statement

Live HA logs show a recurring pattern:

1. Scheduled runs at `:00`/`:30` continue executing.
2. Data path fails with:
   - `Chart setup redirected to: /`
   - `Authentication failed during update: Chart setup failed — hourly context not established`
3. Manual cookie injection restores operation immediately.
4. Add-on refresh sometimes fails with:
   - `Failed to connect to addon: Server disconnected`

This indicates a gap between lightweight cookie checks and actual chart-context auth, plus add-on refresh reliability issues.

---

## Desired End State

1. Integration detects data-path auth failure automatically.
2. Integration forces refresh on data-path auth failure without waiting for manual action.
3. Add-on refresh path handles transient disconnects with bounded retries.
4. Persistent notifications clearly distinguish:
   - add-on connectivity failure
   - CAPTCHA challenge
   - chart-context auth failure loop
5. Manual cookie entry remains fallback, not primary recovery path.

---

## Phase 1 — Close the Auth Validation Gap

### 1.1 Add a data-path auth probe in `PSEGLIClient`

Implement a synchronous method (executor-run by integration) that validates the same auth path used by statistics updates:
- dashboard fetch
- token extraction
- chart context setup

Do not rely only on `/Dashboard` success as auth-valid signal.

### 1.2 Use data-path probe where scheduler currently uses lightweight check

Replace “cookie still valid” determination in scheduled flow with the data-path probe result.
- If probe fails with auth redirect/error, treat cookie as expired/invalid.
- Proceed directly to refresh attempt.

---

## Phase 2 — Automatic Recovery on Update Failure

### 2.1 Promote chart-context auth failure to refresh trigger

When `_do_update_statistics` hits auth errors such as:
- `Chart setup redirected to: /`
- chart setup auth failure

mark state as “refresh required” and trigger refresh logic immediately (or very short delay), instead of waiting for next cycle only.

### 2.2 Prevent infinite fail loops

Track consecutive auth-failure count in `hass.data[DOMAIN]`.
- After N consecutive failures, emit a dedicated persistent notification:
  - `psegli_chart_auth_failed_loop`
- Continue bounded retries, but surface clear operator action.

---

## Phase 3 — Harden Add-on Refresh Reliability

### 3.1 Retry policy for add-on `/login` disconnects

On add-on connectivity failures (`Server disconnected`, timeout):
- retry 2-3 times with short jittered backoff.
- keep upper-bound latency reasonable.

### 3.2 Improved diagnostics

Log refresh attempt IDs and classify failure reasons:
- addon_unreachable
- addon_disconnect
- captcha_required
- invalid_credentials
- unknown_runtime_error

This avoids “generic refresh failed” ambiguity.

---

## Phase 4 — Tests and Regression Coverage

Add tests that reproduce real failure sequence:

1. Dashboard check passes, chart setup redirects (`/`) -> scheduler must refresh.
2. Add-on disconnect on first refresh attempt, success on second -> automatic recovery.
3. Consecutive chart auth failures -> loop notification emitted.

Also keep existing lifecycle/startup guarantees:
- scheduler runs as background task
- no startup blocking warnings.

---

## Phase 5 — Rollout and Validation

### 5.1 Staged rollout checks

After deployment:
1. Force `psegli.update_statistics` and verify success.
2. Force `psegli.refresh_cookie` and verify add-on path.
3. Observe at least two scheduled checkpoints (`:00`/`:30`).

### 5.2 Acceptance criteria

All must be true:
1. No sustained `Chart setup redirected to: /` loop over 24h.
2. At least one simulated add-on disconnect is auto-recovered without manual cookie.
3. No startup timeout/blocking warnings from PSEG scheduled task.
4. Manual cookie remains optional fallback only.

---

## Out of Scope

1. Replacing cookie auth model entirely.
2. Reworking PSEG upstream endpoint behavior.
3. Full mobile notification UX redesign.
