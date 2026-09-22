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
	"path/filepath"
	"regexp"
	"strings"

	"github.com/tomo-chan/agent-harness/internal/policy"
)

// ConfigFilename is the only repository policy name accepted in the trusted
// root. A repository checkout cannot select another file at runtime.
const ConfigFilename = "repository-security.json"

const (
	// AuthoritySourceGitHubRules uses the effective Rules API and can evidence
	// pull-request, force-push, and required-status-check requirements.
	AuthoritySourceGitHubRules = "github_rules"
	// AuthoritySourceGitHubBranchMetadata uses the broadly available branch
	// metadata API to determine whether the exact current branch is protected.
	// It cannot evidence detailed default-branch protection requirements.
	AuthoritySourceGitHubBranchMetadata = "github_branch_metadata"
)

var repositoryName = regexp.MustCompile(`^[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_.-]*$`)
var branchName = regexp.MustCompile(`^[A-Za-z0-9][A-Za-z0-9._/-]*$`)

// Requirements are trusted minimum posture requirements. False values may be
// selected only in the trusted file; repository-controlled overlays are not
// loaded by this implementation.
type Requirements struct {
	RequireLinkedWorktree bool
	RequirePullRequest    bool
	BlockForcePush        bool
	RequiredStatusChecks  bool
}

// Config is the validated task-specific repository authority configuration.
// AuthoritySource prevents an unavailable API from silently selecting a weaker
// source. Repository ID, worktree root, per-worktree Git directory, Git common
// directory, and branch prevent mutable local origin metadata from establishing
// identity by itself. SHA256 binds posture evidence to the exact trusted bytes.
type Config struct {
	SchemaVersion        int
	AuthoritySource      string
	ExpectedRepository   string
	ExpectedRepositoryID int64
	ExpectedWorktreeRoot string
	ExpectedGitDir       string
	ExpectedGitCommonDir string
	ExpectedBranch       string
	Requirements         Requirements
	SHA256               string
}

// validAbsoluteBoundary rejects relative, non-canonical, and filesystem-root
// bindings before any repository-controlled path is observed.
func validAbsoluteBoundary(path string) bool {
	return filepath.IsAbs(path) && filepath.Clean(path) == path && path != string(filepath.Separator)
}

// validBranch deliberately accepts a conservative subset of Git ref names for
// the experimental trusted configuration schema.
func validBranch(value string) bool {
	return branchName.MatchString(value) && value != "HEAD" &&
		!strings.Contains(value, "..") && !strings.Contains(value, "//") &&
		!strings.Contains(value, "@{") && !strings.HasSuffix(value, "/") &&
		!strings.HasSuffix(value, ".") && !strings.HasSuffix(value, ".lock")
}

// LoadConfig validates the experimental v1 repository policy schema. Unknown
// fields, duplicate keys, ambiguous types, and missing identity fail closed.
// The authority source is explicit; there is no runtime fallback between APIs.
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
		case "schema_version", "authority_source", "expected_repository", "expected_repository_id", "expected_worktree_root", "expected_git_dir", "expected_git_common_dir", "expected_branch", "requirements":
		default:
			return nil, fmt.Errorf("unknown repository policy field %q", key)
		}
	}

	version, ok := m["schema_version"].(json.Number)
	if !ok || version.String() != "1" {
		return nil, fmt.Errorf("schema_version must be 1")
	}
	authoritySource, ok := m["authority_source"].(string)
	if !ok || (authoritySource != AuthoritySourceGitHubRules && authoritySource != AuthoritySourceGitHubBranchMetadata) {
		return nil, fmt.Errorf("authority_source must be github_rules or github_branch_metadata")
	}
	expected, ok := m["expected_repository"].(string)
	if !ok || !repositoryName.MatchString(expected) {
		return nil, fmt.Errorf("expected_repository must be owner/repository")
	}
	repositoryID, ok := m["expected_repository_id"].(json.Number)
	if !ok {
		return nil, fmt.Errorf("expected_repository_id must be a positive integer")
	}
	expectedID, err := repositoryID.Int64()
	if err != nil || expectedID <= 0 {
		return nil, fmt.Errorf("expected_repository_id must be a positive integer")
	}
	expectedWorktreeRoot, ok := m["expected_worktree_root"].(string)
	if !ok || !validAbsoluteBoundary(expectedWorktreeRoot) {
		return nil, fmt.Errorf("expected_worktree_root must be a clean absolute path other than root")
	}
	expectedGitDir, ok := m["expected_git_dir"].(string)
	if !ok || !validAbsoluteBoundary(expectedGitDir) {
		return nil, fmt.Errorf("expected_git_dir must be a clean absolute path other than root")
	}
	expectedGitCommonDir, ok := m["expected_git_common_dir"].(string)
	if !ok || !validAbsoluteBoundary(expectedGitCommonDir) {
		return nil, fmt.Errorf("expected_git_common_dir must be a clean absolute path other than root")
	}
	expectedBranch, ok := m["expected_branch"].(string)
	if !ok || !validBranch(expectedBranch) {
		return nil, fmt.Errorf("expected_branch must be a conservative Git branch name")
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
	if authoritySource == AuthoritySourceGitHubBranchMetadata &&
		(requirements.RequirePullRequest || requirements.BlockForcePush || requirements.RequiredStatusChecks) {
		return nil, fmt.Errorf("github_branch_metadata cannot evidence detailed default-branch protection requirements")
	}

	digest := sha256.Sum256(b)
	return &Config{
		SchemaVersion:        1,
		AuthoritySource:      authoritySource,
		ExpectedRepository:   expected,
		ExpectedRepositoryID: expectedID,
		ExpectedWorktreeRoot: expectedWorktreeRoot,
		ExpectedGitDir:       expectedGitDir,
		ExpectedGitCommonDir: expectedGitCommonDir,
		ExpectedBranch:       expectedBranch,
		Requirements:         requirements,
		SHA256:               hex.EncodeToString(digest[:]),
	}, nil
}
