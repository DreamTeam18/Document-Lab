# Frontend unit test results

Vitest: 100/100 passed; 0 failed.

Run from `web`: `npm run test:unit:report`. Use `npm test` to also run the six existing Node tests.

Uses React Testing Library and jsdom for components, and Node for streaming adapter tests. Network/provider calls are mocked; these tests consume no OpenRouter credits. They do not validate real browser rendering, WebGL, or live backend behavior.

| Test file | Passed |
| --- | ---: |
| adapter.test.ts | 22 |
| composer.test.tsx | 15 |
| documents.test.tsx | 25 |
| landing.test.tsx | 10 |
| reducer.test.ts | 18 |
| store.test.tsx | 10 |

## Individual results

### adapter.test.ts

- passed: parses LF frames
- passed: parses byte-fragmented CRLF and Unicode
- passed: parses multiple events in one read
- passed: ignores comment keepalives
- passed: defaults absent event name to message
- passed: joins multiline data
- passed: rejects malformed JSON
- passed: releases reader lock after parsing failure
- passed: rejects requests with no message before fetch
- passed: rejects requests ending with assistant
- passed: sends only latest question and selected IDs
- passed: uses backend session ID for follow-up
- passed: maps session event
- passed: maps retrieval progress
- passed: retains unknown progress label
- passed: maps final answer and source metadata
- passed: defaults omitted citations and warnings to empty
- passed: propagates useful HTTP error details
- passed: handles non-JSON HTTP error safely
- passed: propagates SSE errors
- passed: rejects truncated stream without final result
- passed: passes caller cancellation to fetch

### composer.test.tsx

- passed: message field has accessible label and character limit
- passed: source-less composer disables input and send
- passed: submits trimmed question
- passed: does not submit whitespace-only question
- passed: clears draft after successful submission
- passed: preserves draft when submission throws
- passed: stop button aborts rather than submitting another question
- passed: blocks form submission while streaming
- passed: welcome suggestions populate draft
- passed: hides suggestions during established conversation
- passed: shows evidence disclaimer
- passed: renders provided welcome header
- passed: file paste directs user to indexed upload
- passed: file drop directs user to sidebar rather than silently attaching
- passed: Shift+Enter inserts newline without submitting

### documents.test.tsx

- passed: shows document titles and editions
- passed: shows selected source count
- passed: shows empty library guidance
- passed: shows library failure as alert
- passed: refresh button requests latest documents
- passed: selects a document
- passed: deselects an existing source
- passed: allows the fifth source
- passed: rejects the sixth source
- passed: locks selection for existing conversation
- passed: shows thread sources rather than new-chat selection
- passed: collapsed library expands on demand
- passed: mobile sidebar renders source controls even when desktop rail collapsed
- passed: upload button opens file input
- passed: rejects empty files before network
- passed: rejects files larger than 10 MB
- passed: accepts exactly 10 MB
- passed: encodes filename and sends raw file
- passed: successful upload refreshes and selects new source
- passed: successful upload starts new chat and reports chunks
- passed: disables upload and selection while indexing
- passed: disables upload while a chat is streaming
- passed: shows backend upload failure without selecting document
- passed: restores controls after network failure
- passed: renders hostile document titles as text

### landing.test.tsx

- passed: labels examples as scripted rather than live answers
- passed: first scenario is selected and associated with its panel
- passed: switching scenario changes source and question
- passed: Answer control reveals grounded answer and citation
- passed: advances stages on active timer
- passed: pause freezes stage progression
- passed: play resumes stage progression
- passed: offscreen examples do not advance
- passed: reduced motion renders complete answer without waiting
- passed: keyboard navigation moves focus and selection across tabs

### reducer.test.ts

- passed: records backend session without replacing browser ID
- passed: preserves source selection on session update
- passed: updates conversation title
- passed: replaces to-do state
- passed: appends answer fragments in order
- passed: preserves Unicode answer content
- passed: appends reasoning independently from answer
- passed: inserts retrieval step
- passed: updates existing step without duplicate
- passed: preserves distinct step order
- passed: stores citation metadata and warnings
- passed: clears previous sources on empty evidence
- passed: does not mutate input conversation
- passed: does not update user message even with matching ID
- passed: leaves messages unchanged for missing target
- passed: completes answer and records duration
- passed: stopping preserves partial answer and settles steps
- passed: error preserves explanation and does not mutate input

### store.test.tsx

- passed: loads real document list on mount
- passed: exposes document network errors to the UI
- passed: restores recent browser conversation and source IDs
- passed: settles interrupted restored answer to stopped
- passed: invalid stored JSON does not crash workspace
- passed: rejects sending without selected documents
- passed: rejects question beyond 4000 characters
- passed: successful stream persists answer and backend session
- passed: follow-up uses immutable thread selection
- passed: stream error preserves partial output and marks failed turn
