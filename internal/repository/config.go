// Package repository derives repository posture and mutation authority from a
// trusted configuration, local Git observations, and current GitHub state.
//
// The package does not classify publication operations, approve changes, or
// replace GitHub server-side authorization. Callers must supply configuration
// selected by a trusted runtime and must fail closed when Assess returns an
// error or a non-READY report.
package repository

import (
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"regexp"

	"github.com/tomo-chan/agent-harness/internal/policy"
)

// ConfigFilename is the only repository policy name accepted in the trusted
// root. A repository checkout cannot select another file at runtime.
const ConfigFilename = "repository-security.json"

var repositoryName = regexp.MustCompile(`^[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_.-]*$`)

// Requirements are trusted minimum posture requirements. False values may be
// selected only in the trusted file; repository-controlled overlays are not
// loaded by this implementation.
type Requirements struct {
	RequireLinkedWorktree bool
	RequirePullRequest    bool
	BlockForcePush        bool
	RequiredStatusChecks  bool
}

// Config is the validated repository authority configuration. SHA256 binds
// posture evidence to the exact trusted bytes used for the evaluation.
type Config struct {
	SchemaVersion      int
	ExpectedRepository string
	Requirements       Requirements
	SHA256             string
}

// LoadConfig validates the experimental v1 repository policy schema. Unknown
// fields, duplicate keys, ambiguous types, and missing identity fail closed.
// Requirements default to true so omission cannot silently weaken posture.
func LoadConfig(r io.Reader) (*Config, error) {
	b, err := io.ReadAll(io.LimitReader(r, policy.MaxJSON+1))
	if err != nil {
		return nil, err
	}
	if len(b) > policy.MaxJSON {
		return nil, fmt.Errorf("repository policy exceeds size limit")
	}
	m, err := policy.Object(bytes.NewReader(b))
	if err != nil {
		return nil, err
	}
	for key := range m {
		switch key {
		case "schema_version", "expected_repository", "requirements":
		default:
			return nil, fmt.Errorf("unknown repository policy field %q", key)
		}
	}

	version, ok := m["schema_version"].(json.Number)
	if !ok || version.String() != "1" {
		return nil, fmt.Errorf("schema_version must be 1")
	}
	expected, ok := m["expected_repository"].(string)
	if !ok || !repositoryName.MatchString(expected) {
		return nil, fmt.Errorf("expected_repository must be owner/repository")
	}

	requirements := Requirements{
		RequireLinkedWorktree: true,
		RequirePullRequest:    true,
		BlockForcePush:        true,
		RequiredStatusChecks:  true,
	}
	if raw, exists := m["requirements"]; exists {
		fields, ok := raw.(map[string]any)
		if !ok {
			return nil, fmt.Errorf("requirements must be an object")
		}
		for key, rawValue := range fields {
			value, ok := rawValue.(bool)
			if !ok {
				return nil, fmt.Errorf("requirement %q must be boolean", key)
			}
			switch key {
			case "require_linked_worktree":
				requirements.RequireLinkedWorktree = value
			case "require_pull_request":
				requirements.RequirePullRequest = value
			case "block_force_push":
				requirements.BlockForcePush = value
			case "required_status_checks":
				requirements.RequiredStatusChecks = value
			default:
				return nil, fmt.Errorf("unknown repository requirement %q", key)
			}
		}
	}

	digest := sha256.Sum256(b)
	return &Config{
		SchemaVersion:      1,
		ExpectedRepository: expected,
		Requirements:       requirements,
		SHA256:             hex.EncodeToString(digest[:]),
	}, nil
}
