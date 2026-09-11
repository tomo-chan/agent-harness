package main

import (
	"encoding/json"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"

	"github.com/tomo-chan/agent-harness/internal/policy"
	"github.com/tomo-chan/agent-harness/internal/repository"
)

// Exercise the actual distributable, with no Python or PATH and hostile cwd.
func TestSingleBinary(t *testing.T) {
	root := t.TempDir()
	binary := filepath.Join(root, "agent-harness")
	build := exec.Command("go", "build", "-o", binary, ".")
	if out, err := build.CombinedOutput(); err != nil {
		t.Fatalf("build: %s %v", out, err)
	}
	cwd := t.TempDir()
	evil := filepath.Join(cwd, "policy.json")
	if err := os.WriteFile(evil, []byte(`{"default":"allow"}`), 0600); err != nil {
		t.Fatal(err)
	}
	valid := `{"default":"ask","allow":[{"command_regex":"^git status$"}],"deny":[{"command_regex":"danger"}]}`
	repositoryConfig := `{"schema_version":1,"expected_repository":"acme/widget"}`
	input := `{"tool":"exec","input":{"command":"git status"}}`
	for _, tc := range []struct {
		name, config, input, want          string
		env                                []string
		args                               []string
		noRoot, missing, missingRepository bool
		code                               int
	}{
		{name: "unrelated cwd and poisoned Python paths", config: valid, input: input, want: "allow"},
		{name: "ask", config: valid, input: `{"tool":"Read","input":{"path":"README.md"}}`, want: "ask"},
		{name: "policy deny", config: valid, input: `{"tool":"exec","input":{"command":"danger"}}`, want: "deny"},
		{name: "missing root", config: valid, input: input, noRoot: true, want: "deny", code: 2},
		{name: "missing policy despite repository fallback", missing: true, input: input, want: "deny", code: 2},
		{name: "missing repository policy", config: valid, missingRepository: true, input: input, want: "deny", code: 2},
		{name: "invalid policy", config: `{"default":"permit"}`, input: input, want: "deny", code: 2},
		{name: "invalid input", config: valid, input: `[]`, want: "deny", code: 2},
		{name: "truncated input", config: valid, input: `{`, want: "deny", code: 2},
		{name: "oversized input", config: valid, input: strings.Repeat(" ", policy.MaxJSON+1), want: "deny", code: 2},
		{name: "policy override", config: valid, input: input, env: []string{"AGENT_HARNESS_TRUSTED_POLICY=" + evil}, want: "deny", code: 2},
		{name: "adapter override", config: valid, input: input, env: []string{"AGENT_HARNESS_TRUSTED_ADAPTER=" + evil}, want: "deny", code: 2},
		{name: "repository policy override", config: valid, input: input, env: []string{"AGENT_HARNESS_TRUSTED_REPOSITORY_SECURITY_POLICY=" + evil}, want: "deny", code: 2},
		{name: "expected repository override", config: valid, input: input, env: []string{"AGENT_HARNESS_EXPECTED_REPOSITORY=evil/repository"}, want: "deny", code: 2},
		{name: "posture mode override", config: valid, input: input, env: []string{"AGENT_HARNESS_MINIMUM_POSTURE_MODE=warn"}, want: "deny", code: 2},
		{name: "arbitrary cli path", config: valid, input: input, args: []string{evil}, want: "deny", code: 2},
		{name: "legacy policy ignored", config: `{"default":"deny"}`, input: input, want: "deny"},
	} {
		t.Run(tc.name, func(t *testing.T) {
			p := filepath.Join(root, "policy.json")
			if tc.missing {
				if err := os.Remove(p); err != nil && !os.IsNotExist(err) {
					t.Fatal(err)
				}
			} else if err := os.WriteFile(p, []byte(tc.config), 0600); err != nil {
				t.Fatal(err)
			}
			rp := filepath.Join(root, repository.ConfigFilename)
			if tc.missingRepository {
				if err := os.Remove(rp); err != nil && !os.IsNotExist(err) {
					t.Fatal(err)
				}
			} else if err := os.WriteFile(rp, []byte(repositoryConfig), 0o600); err != nil {
				t.Fatal(err)
			}
			cmd := exec.Command(binary, tc.args...)
			cmd.Dir = cwd
			cmd.Env = []string{
				"PATH=/nonexistent",
				"PYTHONPATH=" + cwd,
				"PYTHONHOME=" + cwd,
				"AGENT_POLICY=" + evil,
				"AGENT_HARNESS_POLICY=" + evil,
				"GIT_DIR=" + cwd,
				"GH_HOST=evil.invalid",
				"GITHUB_API_URL=https://evil.invalid",
				"HTTPS_PROXY=http://evil.invalid",
			}
			if !tc.noRoot {
				cmd.Env = append(cmd.Env, "AGENT_HARNESS_TRUSTED_ROOT="+root)
			}
			cmd.Env = append(cmd.Env, tc.env...)
			cmd.Stdin = strings.NewReader(tc.input)
			out, err := cmd.Output()
			code := 0
			if err != nil {
				if e, ok := err.(*exec.ExitError); ok {
					code = e.ExitCode()
				} else {
					t.Fatal(err)
				}
			}
			var d policy.Decision
			if err := json.Unmarshal(out, &d); err != nil {
				t.Fatalf("invalid output %q: %v", out, err)
			}
			if code != tc.code || d.Decision != tc.want || d.Reason == "" {
				t.Fatalf("code=%d decision=%+v", code, d)
			}
			if code == 0 && d.Evidence == nil {
				t.Fatal("valid decision omitted evidence")
			}
		})
	}
}
