package repository

import (
	"strings"
	"testing"
)

const validConfigJSON = `{
	"schema_version":1,
	"expected_repository":"acme/widget",
	"expected_repository_id":123456,
	"expected_worktree_root":"/work/task",
	"expected_git_dir":"/repo/.git/worktrees/task",
	"expected_git_common_dir":"/repo/.git",
	"expected_branch":"feature/task"
}`

func TestLoadConfigUsesFailSafeRequirementDefaults(t *testing.T) {
	config, err := LoadConfig(strings.NewReader(validConfigJSON))
	if err != nil {
		t.Fatal(err)
	}
	if config.ExpectedRepository != "acme/widget" || len(config.SHA256) != 64 {
		t.Fatalf("unexpected config: %+v", config)
	}
	if !config.Requirements.RequireLinkedWorktree || !config.Requirements.RequirePullRequest ||
		!config.Requirements.BlockForcePush || !config.Requirements.RequiredStatusChecks {
		t.Fatalf("requirements were weakened by omission: %+v", config.Requirements)
	}
}

func TestLoadConfigAllowsOnlyTrustedExplicitRequirementChanges(t *testing.T) {
	config, err := LoadConfig(strings.NewReader(`{
			"schema_version":1,
			"expected_repository":"acme/widget",
			"expected_repository_id":123456,
			"expected_worktree_root":"/work/task",
			"expected_git_dir":"/repo/.git/worktrees/task",
			"expected_git_common_dir":"/repo/.git",
			"expected_branch":"feature/task",
			"requirements":{"required_status_checks":false}
		}`))
	if err != nil {
		t.Fatal(err)
	}
	if config.Requirements.RequiredStatusChecks || !config.Requirements.RequirePullRequest {
		t.Fatalf("unexpected requirements: %+v", config.Requirements)
	}
}

func TestLoadConfigRejectsAmbiguousOrInvalidPolicy(t *testing.T) {
	for _, raw := range []string{
		`{}`,
		`{"schema_version":2,"expected_repository":"acme/widget","expected_repository_id":123456,"expected_worktree_root":"/work/task","expected_git_dir":"/repo/.git/worktrees/task","expected_git_common_dir":"/repo/.git","expected_branch":"feature/task"}`,
		`{"schema_version":1,"expected_repository":"not-a-repository","expected_repository_id":123456,"expected_worktree_root":"/work/task","expected_git_dir":"/repo/.git/worktrees/task","expected_git_common_dir":"/repo/.git","expected_branch":"feature/task"}`,
		`{"schema_version":1,"expected_repository":"acme/widget","expected_repository_id":0,"expected_worktree_root":"/work/task","expected_git_dir":"/repo/.git/worktrees/task","expected_git_common_dir":"/repo/.git","expected_branch":"feature/task"}`,
		`{"schema_version":1,"expected_repository":"acme/widget","expected_repository_id":123456,"expected_worktree_root":"relative","expected_git_dir":"/repo/.git/worktrees/task","expected_git_common_dir":"/repo/.git","expected_branch":"feature/task"}`,
		`{"schema_version":1,"expected_repository":"acme/widget","expected_repository_id":123456,"expected_worktree_root":"/work/task","expected_git_dir":"relative","expected_git_common_dir":"/repo/.git","expected_branch":"feature/task"}`,
		`{"schema_version":1,"expected_repository":"acme/widget","expected_repository_id":123456,"expected_worktree_root":"/work/task","expected_git_dir":"/repo/.git/worktrees/task","expected_git_common_dir":"/repo/.git","expected_branch":"release..bad"}`,
		`{"schema_version":1,"expected_repository":"acme/widget","expected_repository_id":123456,"expected_worktree_root":"/work/task","expected_git_dir":"/repo/.git/worktrees/task","expected_git_common_dir":"/repo/.git","expected_branch":"feature/task","unknown":true}`,
		`{"schema_version":1,"expected_repository":"acme/widget","expected_repository_id":123456,"expected_worktree_root":"/work/task","expected_git_dir":"/repo/.git/worktrees/task","expected_git_common_dir":"/repo/.git","expected_branch":"feature/task","requirements":[]}`,
		`{"schema_version":1,"expected_repository":"acme/widget","expected_repository_id":123456,"expected_worktree_root":"/work/task","expected_git_dir":"/repo/.git/worktrees/task","expected_git_common_dir":"/repo/.git","expected_branch":"feature/task","requirements":{"require_pull_request":"yes"}}`,
		`{"schema_version":1,"expected_repository":"acme/widget","expected_repository_id":123456,"expected_worktree_root":"/work/task","expected_git_dir":"/repo/.git/worktrees/task","expected_git_common_dir":"/repo/.git","expected_branch":"feature/task","requirements":{"unknown":true}}`,
		`{"schema_version":1,"schema_version":1,"expected_repository":"acme/widget","expected_repository_id":123456,"expected_worktree_root":"/work/task","expected_git_dir":"/repo/.git/worktrees/task","expected_git_common_dir":"/repo/.git","expected_branch":"feature/task"}`,
	} {
		if _, err := LoadConfig(strings.NewReader(raw)); err == nil {
			t.Errorf("accepted invalid repository policy: %s", raw)
		}
	}
}
