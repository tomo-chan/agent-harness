# Design Principles

## 1. Assume the model will eventually make a bad decision

Do not build the system around perfect instruction following. Prompt injection, ambiguous intent, hallucination and ordinary implementation mistakes are expected failure modes. Safety comes from independent enforcement layers.

## 2. Separate policy from capability

A hook deciding that `rm -rf /` is forbidden is policy. A sandbox making `/` non-writable is capability control. Use both. Policy provides semantic precision; capability controls contain failures in policy, hooks and the model.

## 3. Soft controls are not security boundaries

AGENTS.md, CLAUDE.md, prompts, Skills, playbooks and model-generated plans are behavioral inputs. They improve reliability but must never be the sole mechanism protecting credentials, production systems or protected branches.

## 4. Prefer fail-closed enforcement

Security-critical enforcement should fail closed. Hook engines that continue execution after hook crashes/timeouts must be treated as advisory/semantic layers and backed by sandbox, IAM and server-side policy.

## 5. Least privilege at every layer

Grant the smallest useful capability:

- repository rather than organization scope;
- feature branch rather than default branch;
- read-only cloud API where mutation is unnecessary;
- task-scoped credentials rather than persistent personal tokens;
- explicit egress destinations rather than unrestricted Internet;
- workspace writes rather than home-directory writes.

## 6. Optimize for autonomous safe paths

A mature harness should not ask a human about every shell command. Encode common safe operations into permissions/rules and sandbox constraints. Reserve approval for boundary crossings and semantically risky actions.

## 7. Server-side policy is authoritative

Do not rely on the agent to avoid pushing to `main`. Make direct pushes impossible using GitHub rulesets/branch protection and credential scope. Apply the same principle to cloud IAM, deployment environments and production databases.

## 8. Completion is a predicate

Define "done" as machine-checkable predicates rather than conversational confidence. Tests, Git state, CI state, PR state and deployment evidence belong outside model memory.

## 9. Keep vendor adapters thin

Normalize vendor lifecycle events into a small internal contract such as:

```json
{
  "event": "pre_tool_use",
  "tool": "exec",
  "input": {"command": "git push origin feature/x"},
  "context": {
    "session_id": "...",
    "cwd": "...",
    "repository": "...",
    "branch": "feature/x"
  }
}
```

The central policy engine should return a vendor-neutral decision. Claude Code, Codex and Devin adapters translate to/from their native hook schemas.

## 10. Make policy observable

Record policy version, normalized action, decision, reason, approval identity and execution result. Logs must avoid leaking secrets. Correlate events with task/session/turn IDs.

## 11. Bound autonomous loops

Use budgets for turns, wall-clock time, tool calls, token/compute cost and repeated failures. Stop hooks and self-repair loops require circuit breakers.

## 12. Treat cloud handoff as a trust-boundary transition

A local-to-cloud handoff changes execution environment, credentials, network controls and data residency. Re-evaluate authorization rather than assuming local policy automatically applies in the cloud environment.
