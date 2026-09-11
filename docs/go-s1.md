[日本語](ja/go-s1.md)

# Go S1: trusted execution / policy

This is Issue #14's independent realization of S1, based on PR #6 at
`97bb264` (launcher, policy engine, adapter, tests and
`docs/review/slices/S1-trusted-execution-policy.ja.md`). It does not depend on
merging that branch. The Python reference remains unchanged.

## Deployment and invocation

```sh
go test ./...
go build
# A trusted operator installs agent-harness and policy.json in one directory.
# Copy reference/policies/policy.example.json as the initial policy.json.
AGENT_HARNESS_TRUSTED_ROOT=/opt/agent-harness /opt/agent-harness/agent-harness <<'JSON'
{"tool_name":"exec","tool_input":{"command":"git status"}}
JSON
```

The executable is at the module root so plain `go build` produces the single
executable. There are no subcommands, runtime plugins or third-party modules.

The trusted operator MUST protect the binary, policy, installation directory,
all ancestors and hook invocation/configuration from agent/repository writes
(using filesystem permissions, read-only mounts or equivalent deployment
controls). The operator supplies the absolute trusted root in the environment.
An attacker who can select another executable and its root, replace the binary,
change this environment, or write the trusted tree is outside this guarantee.
Merely placing this build in an agent-writable checkout does not establish trust.

The canonical executable parent must equal the canonical configured root.
`policy.json` is fixed beneath that root; its resolved path must remain inside
and refer to a regular file. In-root symlinks are permitted; escaping symlinks,
missing files and directories are rejected. Validation followed by opening is
safe only under the immutable-installation assumption; this is not a race-proof
filesystem sandbox. Mount/ownership attestation is not implemented.

The adapter is compiled in. Nonempty `AGENT_HARNESS_TRUSTED_ADAPTER` or
`AGENT_HARNESS_TRUSTED_POLICY` is rejected. `AGENT_HARNESS_POLICY`, `AGENT_POLICY`,
Python variables and repository policy files are not consulted. No arguments
are accepted. cwd has no role in policy selection.

## Data and failure contract

- Input: exactly one UTF-8 JSON object, `tool`/`input` or
  `tool_name`/`tool_input`; mixed spelling is allowed, duplicate aliases are not.
  Tool must be a nonempty string and input an object. Command is a string or
  string array (joined with spaces, as in Python); exec/Bash require it.
  Other tool inputs may omit command. Context/session/turn/prompt/cwd/event
  metadata is accepted but has no policy authority. Unknown top-level fields
  are rejected; tool-specific input fields are opaque.
- Policy: optional `default` (`ask` if absent), and `deny`, `ask`, `allow` arrays.
  Rules support only string `id`, `reason`, `tool_regex`, `command_regex`,
  `action_regex`. All patterns compile before any decision. Omitted predicates
  are unconditional, empty regex matches everything. All present predicates
  must match; action text is tool + newline + command.
- Priority is always deny > ask > allow; within a class, first match wins.
- Output: one JSON object with `decision`, `reason`, `rule` (nullable for a rule
  without ID). A valid decision, including deny or ask, exits 0. Path/configuration/
  policy/input failures emit deny with a stable error category and exit 2.
  Raw input, paths and regex contents are not reflected in failure output.
  Output write failure exits 2. There is no tool execution.
- The consumer MUST treat nonzero exit, missing/invalid output, process crash or
  timeout as denial, and route ask to external approval. This binary cannot
  enforce a vendor runtime's behavior. Input EOF/deadline and overall process
  resource limits remain the caller's responsibility.
- Policy and input each have a 1 MiB limit and JSON nesting is bounded. Duplicate
  keys, trailing JSON, malformed JSON, invalid UTF-8 and wrong schema types are
  rejected. Go regex uses RE2 syntax, not Python `re`; unsupported constructs
  fail closed. Regex classification does not establish shell or SCM safety.

## Assurance evidence and comparison

| S1 claim / Python evidence | Go evidence |
|---|---|
| Required root, matching installation, outside-policy denial / launcher tests | `TestTrustedPaths`, `TestSingleBinary` |
| Trusted policy required; no repository fallback / adapter test | Missing policy, poisoned cwd and legacy environment subprocess cases |
| Fixed priority / `test_deny_precedes_ask_and_allow` | `TestPriorityAndPredicates`, including ask over allow |
| Invalid default / `test_invalid_policy_fails_validation` | `TestInvalidPolicies`, including malformed regex and typed fields |
| Read-only Git, force push, main push, merge, unknown command | `TestPythonS1Vectors`, same commands and unchanged sample policy |
| Input interpretation failure produces deny | `TestHookParsing` plus malformed and oversized subprocess cases |
| Adapter/policy cannot escape installation | Path and override tests; adapter is linked, not loaded |
| No cwd/import dependency | `TestSingleBinary` builds and runs with unrelated cwd, nonexistent PATH and poisoned Python variables |

These are corresponding vectors, not a claim of byte-for-byte Python behavior.
The Go boundary is deliberately stricter about types, duplicate keys, aliases,
unknown fields and explicit paths. Existing main-branch Python tests can still
be run with `python3 -m pytest reference/hooks/tests -q`.

| Dimension | Python S1 (`97bb264`) | Go S1 |
|---|---|---|
| Guarantee | Root/adapter/policy containment; deny-first engine | Same S1 claims; fixed compiled adapter and fixed policy location |
| Implementation | Three runtime Python files (~270 lines) | Root entry + two internal packages; additional strict JSON/schema logic; not a line-count reduction |
| Runtime | Python, imports, multiple source files, exec handoff | One native executable + policy data; no Python/import/adapter exec path |
| Deployment | Interpreter and trusted source tree | Build per target OS/architecture, distribute binary and policy atomically through trusted deployment |
| Failure modes | Interpreter/import/path and handoff errors | Wrong architecture, stale binary, Go toolchain/build provenance, RE2 incompatibility; same installation mutation risk |
| Testability | Small unit tests and launcher subprocess tests | Standard `go test ./...`, actual binary subprocess tests, Linux/macOS CI |
| Debugging / operations | Editable source and interpreter diagnostics | Rebuild needed; stable JSON failure categories, reproduce with trusted policy; binary lifecycle must be managed |

The runtime boundary is simpler because interpreter selection, PYTHONPATH,
module imports and runtime adapter replacement disappear. The implementation
is not smaller: strict decoding and adversarial tests add code. Compile-time
linkage does not solve trusted distribution, host compromise or caller failure
semantics. The S1 evidence supports continuing Go as a production candidate,
not declaring production readiness. There is value in evaluating the next
slice independently, but this spike provides no evidence to rewrite S2–S6
wholesale. Keep Python as an executable reference and a comparison baseline.

S2 repository identity/protection and monotonic composition, S3 SCM publication,
S4 control-plane review, S5 completion and S6 vendor/deployment adapters are
explicitly excluded. In particular, inherited example regexes are compatibility
fixtures, not proof that a shell command is read-only or a Git push is safe.
