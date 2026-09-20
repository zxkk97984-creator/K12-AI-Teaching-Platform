# Final acceptance status

## Can be demonstrated locally

The project can be started from the clean bootstrap path with synthetic accounts/content. The
local demo covers lesson/conversation fixture flow, practice, resources, CodeLab, growth/next-step,
privacy boundaries, responsive browser flows, the deterministic animation controller on an explicitly
marked synthetic fixture, and real Docker runner isolation.

## User-operable local path

1. Inject the already-authorized development/test database and session settings through the secure
   environment, then run `./scripts/bootstrap.sh`. Do not place passwords, PATs, cookies, or student
   data in the repository. To provision demo accounts, set the six `T05_DEMO_*_USERNAME/PASSWORD`
   variables documented by `scripts/bootstrap.sh`; otherwise use the controlled synthetic accounts
   created by the test/bootstrap harness.
2. Sign in with a synthetic profile and open `/courses`. The course list and chapter reader are
   stage/revision filtered; use the profile's `PRIMARY_LOWER`, `PRIMARY_UPPER`, `JUNIOR`, or `SENIOR`
   stage to verify the corresponding entry. A stage label is not evidence that the formal content has
   been human-reviewed.
3. Follow `/lessons` → `/practice` → `/growth` or `/learn`: start a lesson, answer a deterministic
   exercise, inspect feedback/evidence, and use the projected next step. Refresh and use pause/resume
   where applicable to verify the persistent local session.
4. For CodeLab open `/code?task=temperature-converter`, run an intentional syntax/logic error, then
   correct it. With the T24 loopback runner available, the result is a trusted Docker score plus
   separately labelled fixture feedback; without it the UI must show `UNAVAILABLE` and never execute
   code on the API host.
5. Open `/resources` for the controlled Word/PPT/video flow and `/animations` for the explicitly
   marked development/test fixture. Formal profile content, live Knodo calls, and human review remain
   separate gates.

The full repeatable command list and current exit codes are in `LOCAL_BUILD_COMPLETE.md` and
`docs/acceptance/T30.md`.

## Cannot be claimed

It includes a live Knodo integration and a 16-case T31 synthetic evaluation, but it is not a verified paid-model cost result, not a human-approved
four-stage course release, not a real-under-16 student product, not proof of platform deletion or
tenant isolation, and not evidence of learning-effect improvement. The animation fixture is not a
human-approved senior chapter and cannot be used as formal content-release evidence.

## Gate state

G_API_CONTRACT and G_LIVE_BUDGET are PASS for the bounded T11/T13 path. G_AGENT_ISOLATION and G_HUMAN_CONTENT_REVIEW remain BLOCKED.
`G_K12_TERMS` is OUT_OF_SCOPE for the declared adult-contestant/synthetic-data prototype; any
future real-under-16 or formal K12 release must reopen and pass that gate. T31 human review and T33 formal release therefore remain blocked.
