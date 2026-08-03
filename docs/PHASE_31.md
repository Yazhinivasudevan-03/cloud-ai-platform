# Phase 31 — Twilio SMS SDK Integration + Dynamic Per-User Phone Numbers & Notification History

Project: Cloud Usage Monitoring and AI-Driven Predictive Resource Optimization Platform for Microservices
Phase: 31 (replaces the SMS notification channel's raw HTTP integration with the official Twilio SDK, and
enriches Notification History with SMS delivery tracking)
Status: **Complete**

---

## 1. What this phase covers

Two related user requests, worked as one phase since the second built directly on the first:

1. Integrate the real Twilio Python SDK for SMS (real credentials, real API calls, real error handling),
   replacing the previous raw HTTP notifier.
2. Make sure SMS delivery is dynamic per authenticated user (not a hardcoded number), and that every SMS
   attempt - success or failure - is recorded in Notification History with enough detail to audit it.

## 2. What was already true before this phase

An investigation pass (before writing any code for requirement 2) found most of the "dynamic phone
number" requirements were **already implemented** in earlier phases and did not need to be rebuilt:

- E.164 phone validation already existed on both registration (`UserCreate.mobile_number`) and profile
  update (`UserProfileUpdate.phone_number`) via a shared `_E164_PATTERN` validator
  (`backend/app/schemas/user.py`).
- Registration and Profile → Notification Settings already let every user save/update country code,
  mobile number, and an SMS-enabled toggle.
- The phone number was already stored on the `users` table, not hardcoded anywhere.
- The dispatcher already resolved the *authenticated owner* of the alert's cloud account/deployment
  and sent to `user.phone_number` - never a fixed number - and per-tenant isolation (a user only ever
  receives alerts for cloud accounts they own) was already structurally guaranteed by
  `dispatcher.py`'s `_recipients()` resolution (Phase 24).
- The "Send Test SMS" feature already targeted the logged-in user's own stored number.

**What was genuinely new this phase:**

- Swapping the SMS notifier from a raw HTTP call to the official Twilio Python SDK, with real exception
  handling instead of guessed error shapes.
- Fixing the actual root cause of "SMS doesn't send": `docker-compose.yml` never passed
  `TWILIO_ACCOUNT_SID` / `TWILIO_AUTH_TOKEN` / `TWILIO_PHONE_NUMBER` into the backend container's
  environment at all - regardless of what was set in `.env`, the app never saw them.
- Notification History enrichment: 4 new columns (`cloud_provider_account_id`, `phone_number`,
  `message_sid`, `delivery_status`) so every SMS attempt - not just successful ones - is auditable.
- Capturing the real Twilio message SID and delivery status end-to-end, and always writing a
  Notification row on both success *and* failure (every other channel in `dispatcher.py` only logs on
  success; SMS was deliberately changed, since a "Delivery Status" history field is meaningless if
  failures are silently dropped).

## 3. Backend changes

- **`app/notifications/sms_notifier.py`** - rewritten to use `twilio.rest.Client` instead of raw HTTP.
  `send_sms_with_details()` is a new function returning a `SmsSendResult` NamedTuple (`sent`, `reason`,
  `message_sid`, `status`) with real Twilio error detail (`exc.status`/`exc.code`/`exc.msg`/`exc.uri`) on
  failure. The existing `send_sms()` / `send_sms_with_reason()` contracts (2-arg, bool/tuple-returning)
  are preserved byte-for-byte for backward compatibility - nothing else that already called them needed
  to change.
- **`app/utils/retry.py`** - new `twilio_retry`: retries on Twilio 5xx and on real
  `requests.exceptions.RequestException` (connection-level failures), not on 4xx (those are permanent,
  e.g. bad number).
- **`app/config/settings.py`** - `TWILIO_FROM_NUMBER` renamed to `TWILIO_PHONE_NUMBER` (matching the
  requested env var name exactly).
- **`docker-compose.yml`** - backend service now actually passes `TWILIO_ACCOUNT_SID` /
  `TWILIO_AUTH_TOKEN` / `TWILIO_PHONE_NUMBER` through from the host environment. This was the real root
  cause of SMS never sending in practice.
- **`.env.example`** - documents the 3 new variables (no values, no secrets).
- **`app/models/notification.py`** + new Alembic migration
  (`12f99b7b30bb_sms_notification_history_fields.py`) - adds `cloud_provider_account_id` (FK, nullable),
  `phone_number`, `message_sid`, `delivery_status` to `notifications`. All nullable/additive - no
  existing row or query breaks.
- **`app/notifications/dispatcher.py`** - the SMS block now always creates a `Notification` row (success
  or failure), populated with the deployment's `cloud_provider_account_id`, the recipient's
  `phone_number`, the real Twilio `message_sid` (or `None` on failure), and `delivery_status` (Twilio's
  real status on success, or the detailed error reason on failure).
- **`app/schemas/notification.py`** - `NotificationRead` exposes the 4 new fields.

## 4. Frontend changes

- **`types/index.ts`** - `Notification` interface gains the 4 new fields.
- **`NotificationsPage.tsx`** - new "SMS Delivery" column showing the phone number and a delivery-status
  chip for SMS rows.

## 5. Live verification (real Twilio account, real API calls)

Using the real credentials provided for this account (not repeated here - see `.env`, which is
git-ignored and was never committed):

- **Authentication confirmed real**: a genuine, read-only Twilio API call succeeded against the live
  account.
- **Trial-account limitation discovered**: the account is a Twilio Trial account with zero purchased
  phone numbers. Twilio rejected an outbound send with a real `422` response, error code `572002`
  ("No Twilio trial phone number is assigned for messaging to this destination number... add the 'to'
  number as a verified recipient"). This is a genuine account-configuration limitation on Twilio's side,
  not a bug in this integration - and failed sends of this kind are not charged.
- **Detailed error capture proven end-to-end**: the application's own `send_sms_with_reason()` correctly
  captured and returned this exact real error, satisfying "return detailed errors if delivery fails"
  with genuine evidence rather than a mocked assumption.
- **Notification History persistence proven with real data**: a full, real `dispatch()` call (real
  throwaway User → CloudProviderAccount → Project → Microservice → Deployment → Alert chain, cleaned up
  immediately after) produced a real `Notification` row with:
  - `cloud_provider_account_id` = the correct owning account's ID
  - `phone_number` = the correct owner's stored number
  - `message_sid` = `None` (Twilio never created a message, since the send was rejected)
  - `delivery_status` = the full real Twilio error text (`"failed: Twilio error 572002 - ..."`)

  This is exactly the behavior requested: every alert attempt - success or failure - lands in
  Notification History with enough detail to audit it.

## 6. Testing

- `test_notifiers.py` - SMS tests rewritten to mock `twilio.rest.Client` instead of raw HTTP; new tests
  cover a successful send, an unrecognized Twilio failure (using the real 572002 error found in live
  verification), and an invalid-recipient (400-class) failure.
- `test_alert_evaluation.py` - SMS dispatch test updated for the SDK swap; 3 new tests added:
  Notification History records cloud account/phone/SID/status on success, records a failed delivery with
  full error detail, and a two-user isolation test proving each user only ever receives alerts for cloud
  accounts they own.
- Full backend regression: **710 passed**, 0 failed, 0 errors (352.82s).

## 7. A real test-infra bug found and fixed along the way

While re-running the full regression after an earlier container had to be force-killed mid-run (an
unrelated tooling issue, not a Twilio bug), every single test started erroring with a MySQL duplicate-key
error on the test database's seeded `roles` table. Root cause: the force-killed run never reached its
teardown (`Base.metadata.drop_all`), leaving stale seed rows in the throwaway `_test`-suffixed schemas
for the next session to collide with. Fixed by making `backend/tests/conftest.py`'s
`_create_test_schema` fixture self-healing - it now calls `drop_all` *before* `create_all` at the start
of every session, not just at the end - so an interrupted previous run can never poison the next one.
This is a genuine, permanent robustness improvement to the test suite, not scoped-out scaffolding.
