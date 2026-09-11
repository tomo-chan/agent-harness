package repository

import (
	"strings"
	"testing"
)

func TestLoadConfigUsesFailSafeRequirementDefaults(t *testing.T) {
	config, err := LoadConfig(strings.NewReader(`{"schema_version":1,"expected_repository":"acme/widget"}`))
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
		`{"schema_version":2,"expected_repository":"acme/widget"}`,
		`{"schema_version":1,"expected_repository":"not-a-repository"}`,
		`{"schema_version":1,"expected_repository":"acme/widget","unknown":true}`,
		`{"schema_version":1,"expected_repository":"acme/widget","requirements":[]}`,
		`{"schema_version":1,"expected_repository":"acme/widget","requirements":{"require_pull_request":"yes"}}`,
		`{"schema_version":1,"expected_repository":"acme/widget","requirements":{"unknown":true}}`,
		`{"schema_version":1,"schema_version":1,"expected_repository":"acme/widget"}`,
	} {
		if _, err := LoadConfig(strings.NewReader(raw)); err == nil {
			t.Errorf("accepted invalid repository policy: %s", raw)
		}
	}
}
