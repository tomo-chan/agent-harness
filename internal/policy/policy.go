// Package policy implements only deterministic S1 classification. Regex rules
// are not a shell parser, repository authority check or authorization gateway.
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

// Evidence identifies the exact policy bytes and normalized action used for a
// decision. S1 reads no external state, so there is no external-state evidence.
type Evidence struct {
	PolicySHA256 string `json:"policy_sha256"`
	ActionSHA256 string `json:"action_sha256"`
}

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

type Action struct{ Tool, Command string }

// ParseHook supports the two existing generic S1 spellings. Ambiguous aliases
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
	command := ""
	if v, exists := input["command"]; exists {
		switch v := v.(type) {
		case string:
			command = v
		case []any:
			parts := make([]string, len(v))
			for i, x := range v {
				s, ok := x.(string)
				if !ok {
					return Action{}, fmt.Errorf("invalid command element")
				}
				parts[i] = s
			}
			command = strings.Join(parts, " ")
		default:
			return Action{}, fmt.Errorf("invalid command")
		}
	} else if tool == "exec" || tool == "Bash" {
		return Action{}, fmt.Errorf("missing command")
	}
	return Action{tool, command}, nil
}

func (e *Engine) Evaluate(a Action) Decision {
	actionJSON, err := json.Marshal(struct {
		Tool    string `json:"tool"`
		Command string `json:"command"`
	}{a.Tool, a.Command})
	if err != nil {
		panic("fixed normalized action cannot fail JSON serialization")
	}
	actionDigest := sha256.Sum256(actionJSON)
	evidence := &Evidence{
		PolicySHA256: e.policySHA256,
		ActionSHA256: hex.EncodeToString(actionDigest[:]),
	}
	texts := [3]string{a.Tool, a.Command, a.Tool + "\n" + a.Command}
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
				return Decision{Decision: outcomes[i], Reason: r.reason, Rule: r.id, Evidence: evidence}
			}
		}
	}
	d := Result(e.fallback, "no explicit policy rule matched", "default")
	d.Evidence = evidence
	return d
}
