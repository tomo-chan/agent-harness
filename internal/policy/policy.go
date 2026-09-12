// Package policy implements deterministic tool classification. Regex rules are
// not a shell parser, repository authority check, or authorization gateway.
package policy

import (
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"regexp"
	"strings"
)

type Decision struct {
	Decision string    `json:"decision"`
	Reason   string    `json:"reason"`
	Rule     *string   `json:"rule"`
	Evidence *Evidence `json:"evidence,omitempty"`
}

// Evidence identifies the exact tool-policy bytes and normalized action used
// for a decision. Repository is populated only when mutation authority requires
// fresh repository and GitHub evaluation.
type Evidence struct {
	PolicySHA256 string              `json:"policy_sha256"`
	ActionSHA256 string              `json:"action_sha256"`
	Evaluator    string              `json:"evaluator"`
	Repository   *RepositoryEvidence `json:"repository,omitempty"`
}

// RepositoryEvidence binds a decision to the trusted repository policy and
// fresh local/GitHub state used by Repository Authority / Posture. Rule digests
// identify the exact default-branch and current-branch responses evaluated.
type RepositoryEvidence struct {
	PolicySHA256             string                    `json:"policy_sha256"`
	PostureState             string                    `json:"posture_state"`
	Repository               string                    `json:"repository"`
	RepositoryID             int64                     `json:"repository_id"`
	RepoRoot                 string                    `json:"repo_root"`
	MutationTarget           string                    `json:"mutation_target"`
	Branch                   string                    `json:"branch"`
	HeadSHA                  string                    `json:"head_sha"`
	DefaultBranch            string                    `json:"default_branch"`
	LinkedWorktree           bool                      `json:"linked_worktree"`
	MetadataSHA256           string                    `json:"github_metadata_sha256"`
	DefaultRulesSHA256       string                    `json:"github_default_rules_sha256,omitempty"`
	CurrentBranchRulesSHA256 string                    `json:"github_current_branch_rules_sha256,omitempty"`
	CheckedAt                string                    `json:"checked_at"`
	Checks                   []RepositoryCheckEvidence `json:"checks"`
}

// RepositoryCheckEvidence retains pass/fail/unknown without converting missing
// authoritative state into success.
type RepositoryCheckEvidence struct {
	Name   string `json:"name"`
	Status string `json:"status"`
	Detail string `json:"detail"`
}

// Evaluator identifies the experimental normalization and matching semantics.
// It is not a source or build provenance identifier.
const Evaluator = "go-s1-experiment-v2"

func Result(outcome, reason, rule string) Decision {
	return Decision{Decision: outcome, Reason: reason, Rule: &rule}
}

type rule struct {
	id       *string
	reason   string
	patterns [3]*regexp.Regexp
}

type Engine struct {
	fallback     string
	rules        [3][]rule
	policySHA256 string
}

var outcomes = [3]string{"deny", "ask", "allow"}

func Load(r io.Reader) (*Engine, error) {
	b, err := io.ReadAll(io.LimitReader(r, MaxJSON+1))
	if err != nil {
		return nil, err
	}
	m, err := Object(bytes.NewReader(b))
	if err != nil {
		return nil, err
	}
	digest := sha256.Sum256(b)
	e := &Engine{fallback: "ask", policySHA256: hex.EncodeToString(digest[:])}
	for k, v := range m {
		switch k {
		case "default":
			s, ok := v.(string)
			if !ok || (s != "deny" && s != "ask" && s != "allow") {
				return nil, fmt.Errorf("invalid default")
			}
			e.fallback = s
		case "deny", "ask", "allow":
		default:
			return nil, fmt.Errorf("unknown policy field")
		}
	}
	for i, outcome := range outcomes {
		v, exists := m[outcome]
		if !exists {
			continue
		}
		list, ok := v.([]any)
		if !ok {
			return nil, fmt.Errorf("rules must be an array")
		}
		for _, v := range list {
			fields, ok := v.(map[string]any)
			if !ok {
				return nil, fmt.Errorf("rule must be an object")
			}
			r := rule{reason: "matched " + outcome + " rule"}
			for k, v := range fields {
				s, ok := v.(string)
				if !ok {
					return nil, fmt.Errorf("rule fields must be strings")
				}
				switch k {
				case "id":
					r.id = &s
				case "reason":
					r.reason = s
				case "tool_regex", "command_regex", "action_regex":
					p, err := regexp.Compile(s)
					if err != nil {
						return nil, fmt.Errorf("invalid regex: %w", err)
					}
					index := map[string]int{"tool_regex": 0, "command_regex": 1, "action_regex": 2}[k]
					r.patterns[index] = p
				default:
					return nil, fmt.Errorf("unknown rule field")
				}
			}
			e.rules[i] = append(e.rules[i], r)
		}
	}
	return e, nil
}

// Action preserves the complete normalized tool input for policy matching and
// evidence. CWD and the derived Command/Target fields are untrusted until
// Repository Guard validates them against the trusted task/worktree binding.
type Action struct {
	Tool    string
	Input   map[string]any
	Command string
	CWD     string
	Target  string
}

// ParseHook supports the two existing generic hook spellings. Ambiguous aliases
// and wrong types are rejected instead of silently becoming empty commands.
func ParseHook(r io.Reader) (Action, error) {
	m, err := Object(r)
	if err != nil {
		return Action{}, err
	}
	for k := range m {
		switch k {
		case "tool", "tool_name", "input", "tool_input", "event", "context", "session_id", "turn_id", "prompt_id", "cwd":
		default:
			return Action{}, fmt.Errorf("unknown hook field")
		}
	}
	alias := func(a, b string) (any, error) {
		v, ok := m[a]
		w, other := m[b]
		if ok && other {
			return nil, fmt.Errorf("ambiguous hook aliases")
		}
		if ok {
			return v, nil
		}
		if other {
			return w, nil
		}
		return nil, fmt.Errorf("missing hook field")
	}
	t, err := alias("tool", "tool_name")
	if err != nil {
		return Action{}, err
	}
	tool, ok := t.(string)
	if !ok || strings.TrimSpace(tool) == "" {
		return Action{}, fmt.Errorf("invalid tool")
	}
	v, err := alias("input", "tool_input")
	if err != nil {
		return Action{}, err
	}
	input, ok := v.(map[string]any)
	if !ok {
		return Action{}, fmt.Errorf("invalid input")
	}
	a := Action{Tool: tool, Input: input}
	command, err := command(a)
	if err != nil {
		return Action{}, err
	}
	target := ""
	for _, key := range []string{"path", "file_path"} {
		if value, exists := input[key]; exists {
			if target != "" {
				return Action{}, fmt.Errorf("ambiguous target")
			}
			path, ok := value.(string)
			if !ok || strings.TrimSpace(path) == "" {
				return Action{}, fmt.Errorf("invalid target")
			}
			target = path
		}
	}
	var cwdValue any
	var hasCWD bool
	if value, exists := m["cwd"]; exists {
		cwdValue, hasCWD = value, true
	}
	if value, exists := m["context"]; exists {
		contextFields, ok := value.(map[string]any)
		if !ok {
			return Action{}, fmt.Errorf("invalid context")
		}
		if value, exists := contextFields["cwd"]; exists {
			if hasCWD {
				return Action{}, fmt.Errorf("ambiguous cwd")
			}
			cwdValue, hasCWD = value, true
		}
	}
	cwd := ""
	if hasCWD {
		var ok bool
		cwd, ok = cwdValue.(string)
		if !ok || strings.TrimSpace(cwd) == "" {
			return Action{}, fmt.Errorf("invalid cwd")
		}
	}
	a.Command = command
	a.CWD = cwd
	a.Target = target
	return a, nil
}

func (e *Engine) Evaluate(a Action) (Decision, error) {
	command, err := command(a)
	if err != nil {
		return Decision{}, err
	}
	actionJSON, err := json.Marshal(struct {
		Tool  string         `json:"tool"`
		Input map[string]any `json:"input"`
		CWD   string         `json:"cwd,omitempty"`
	}{a.Tool, a.Input, a.CWD})
	if err != nil {
		return Decision{}, fmt.Errorf("serialize normalized action: %w", err)
	}
	actionDigest := sha256.Sum256(actionJSON)
	evidence := &Evidence{
		PolicySHA256: e.policySHA256,
		ActionSHA256: hex.EncodeToString(actionDigest[:]),
		Evaluator:    Evaluator,
	}
	texts := [3]string{a.Tool, command, string(actionJSON)}
	for i, rules := range e.rules {
		for _, r := range rules {
			match := true
			for j, p := range r.patterns {
				if p != nil && !p.MatchString(texts[j]) {
					match = false
					break
				}
			}
			if match {
				return Decision{Decision: outcomes[i], Reason: r.reason, Rule: r.id, Evidence: evidence}, nil
			}
		}
	}
	d := Result(e.fallback, "no explicit policy rule matched", "default")
	d.Evidence = evidence
	return d, nil
}

func command(a Action) (string, error) {
	v, exists := a.Input["command"]
	if !exists {
		if a.Input == nil && a.Command != "" {
			return a.Command, nil
		}
		if a.Tool == "exec" || a.Tool == "Bash" {
			return "", fmt.Errorf("missing command")
		}
		return "", nil
	}
	command, ok := v.(string)
	if !ok {
		// Array execution semantics differ across adapters. Joining argv loses
		// boundaries, so S1 rejects it until the common schema defines it.
		return "", fmt.Errorf("command must be a string")
	}
	return command, nil
}

// Command returns the exact command string without joining argv or otherwise
// losing input boundaries. Non-command tools return an empty string.
func Command(a Action) (string, error) {
	return command(a)
}
