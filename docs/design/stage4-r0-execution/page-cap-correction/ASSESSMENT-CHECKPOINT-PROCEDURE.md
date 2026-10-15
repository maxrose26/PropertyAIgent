# Proposed append-only assessment checkpoint amendment

The original method and both original seals remain unchanged. This amendment is not retrospective acceptance and authorises no observations.

1. Before each bounded UI action, durably record its action ID, window, intent, UTC start and cumulative action/segment/reference counters, including earlier phases. Reserve its budget before navigation and fsync the record. Do not execute multiple windows in one runtime call.
2. After each observed segment, persist the bounded literal references, official criteria/URL/count/terminal evidence, UTC end and updated counters before navigating again. Use create-only numbered files; fsync and verify SHA256. Do not hold several windows solely in runtime variables or retain raw HTML/contact payloads.
3. Seal each window's checkpoint manifest and hash. The final assessor seal covers ordered checkpoint hashes, session/freeze/method identity, attempted/not-attempted rows and UNKNOWN resource fields. Keep primary references, logs and artifact contents hidden until sealing.
4. A checkpoint write/hash failure or uncertain accounting stops assessment. A runtime reset does not authorise replay or a fresh budget. Record a pending action as UNKNOWN and charge its reservation. Close existing source tabs where supported. Never reconstruct lost references from primary output.
5. At cap exhaustion, seal partial evidence and mark remaining scope NOT_ATTEMPTED under the approved literal rule. An early displayed total above the per-window cap also needs an explicit stop/continuation rule. Any future continuation change must be accepted by REVIEW before observation.

Reuse valid sealed evidence only where criteria, literal retention and observation chronology support the exact comparison. Preserve source-change uncertainty. This uses existing create-only fsync/hash mechanics; it is not a new browser platform or monitoring service.

Original method SHA256:
`87f0add587ab6066cc9630bbec13cb78e2fd50c37588c2eb7a330c0a5fb8967d`
