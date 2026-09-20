# Knodo finalization checklist

This file is a user/platform action list, not an implementation claim.

1. Obtain and save a redacted official wire sample for Tutor Bot Chat, continuation, streaming,
   cancellation, idempotency, errors and usage. Update G_API_CONTRACT only from that evidence.
2. Name the target Tutor and Designer Bot/Skill/bundle versions and record config hashes; do not
   invent IDs or copy a different service's API fields.
3. Record a user-authorized request purpose and maximum request count. Keep currency/points null
   when the platform source is unknown; update G_LIVE_BUDGET only from accountable evidence.
4. Test two synthetic learners across sessions, files, memories, tools, execution identity and
   revocation. Different conversation IDs alone are insufficient.
5. Current prototype scope is explicitly adult contestants + synthetic learners; no real under-16
   data enters the system, so `G_K12_TERMS` does not block this prototype. If the scope ever expands
   to real K12/under-16 use, first obtain competition/K12 terms confirmation and reopen that gate;
   separately obtain real human review signatures for four stage materials.
6. Run scripts/verify-live.sh with the scoped credentials and preserve success/failure/usage/latency
   outputs without PAT, cookies or full private messages.

Until every applicable item is complete, the app remains a synthetic local prototype.
