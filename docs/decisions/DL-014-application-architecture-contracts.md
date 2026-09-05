# DL-014 — Application architecture is enforced by deterministic contracts and gates

- Date: 2026-09-05
- Status: Accepted
- Scope: Applications built on the agent harness

## Context

The harness defines execution/security architecture and reusable enforcement primitives. An application built on top of it has a second policy domain: architecture and product invariants specific to that application.

A human or agent can review whether an implementation appears consistent with those principles, but a non-deterministic review should not be the merge/release authority for invariants that can be expressed mechanically.

## Decision

Introduce an explicit Application Layer consisting of:

1. application design principles;
2. a versioned architecture contract;
3. deterministic evidence collectors;
4. a deterministic architecture gate;
5. CI/release wiring that consumes the gate result.

The same repository state and contract must produce the same gate result independently of model, prompt, conversation history, or reviewer confidence.

## Principle-to-gate rule

A written principle becomes an enforced gate only after it has a deterministic predicate and reproducible evidence. Principles that cannot yet meet that requirement remain advisory.

LLM/human reviews may discover missing principles, propose invariants, explain failures, or propose waivers. They do not directly emit the authoritative pass/fail result.

## Control-plane protection

The architecture contract, gate implementation, evidence collectors, CI wiring, and waivers are control-plane artifacts. They must not be modifiable through the ordinary autonomous source-edit path without the review/approval policy that protects harness controls.

## Failure semantics

Malformed contracts, unsupported check types, path escapes, missing required evidence, evaluator failures, and expired waivers fail closed.

Waivers are explicit data with check ID, owner, reason, and expiry. There is no broad permanent switch to ignore the architecture gate.

## Initial implementation boundary

The first reference gate intentionally supports a small deterministic vocabulary:

- path exists;
- path absent;
- file contains regex;
- file does not contain regex.

This is not intended as a universal architecture language. New evidence types should be added when there is a concrete invariant that needs them, preferably using structured evidence over text heuristics.

## Consequences

- Application architecture becomes executable and regression-testable.
- Non-deterministic reasoning remains useful without becoming an authority boundary.
- Architecture policy changes become explicit code-review events.
- CI can be configured to require the architecture gate before merge.
- The harness and application layers remain distinct even though they share control-plane mechanisms.

## Revisit triggers

Revisit when a broader policy engine, dependency-graph framework, schema-compatibility system, signed attestation platform, or organization-level architecture service can provide the same deterministic contract with less custom implementation.
