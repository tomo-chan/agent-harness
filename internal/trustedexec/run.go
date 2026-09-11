// Package trustedexec binds the generic adapter and policy location to this
// executable. Deployment MUST keep the installation and its ancestors immutable
// to the repository/agent and invoke the genuine binary with trusted environment.
// Path checks cannot prove ownership, mount immutability, or prevent replacement
// races by an actor who can write the trusted installation.
package trustedexec

import (
	"encoding/json"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strings"

	"github.com/tomo-chan/agent-harness/internal/policy"
)

// PolicyPath requires an absolute root matching the canonical executable parent.
// policy.json is the only policy location; there is no repository fallback.
func PolicyPath(executable, configured string) (string, error) {
	if !filepath.IsAbs(configured) {
		return "", fmt.Errorf("absolute trusted root required")
	}
	root, err := filepath.EvalSymlinks(configured)
	if err != nil {
		return "", err
	}
	exe, err := filepath.EvalSymlinks(executable)
	if err != nil {
		return "", err
	}
	if filepath.Dir(exe) != root {
		return "", fmt.Errorf("trusted root mismatch")
	}
	p, err := filepath.EvalSymlinks(filepath.Join(root, "policy.json"))
	if err != nil {
		return "", err
	}
	rel, err := filepath.Rel(root, p)
	if err != nil || rel == ".." || strings.HasPrefix(rel, ".."+string(filepath.Separator)) || filepath.IsAbs(rel) {
		return "", fmt.Errorf("policy outside trusted root")
	}
	info, err := os.Stat(p)
	if err != nil {
		return "", err
	}
	if !info.Mode().IsRegular() {
		return "", fmt.Errorf("policy must be a regular file")
	}
	return p, nil
}

func evaluate(in io.Reader, args []string) (policy.Decision, string) {
	if len(args) != 0 {
		return policy.Decision{}, "unexpected-arguments"
	}
	// The Python launcher's customization points are deliberately unavailable.
	if os.Getenv("AGENT_HARNESS_TRUSTED_ADAPTER") != "" || os.Getenv("AGENT_HARNESS_TRUSTED_POLICY") != "" {
		return policy.Decision{}, "unsupported-override"
	}
	exe, err := os.Executable()
	if err != nil {
		return policy.Decision{}, "trusted-path-error"
	}
	p, err := PolicyPath(exe, os.Getenv("AGENT_HARNESS_TRUSTED_ROOT"))
	if err != nil {
		return policy.Decision{}, "trusted-path-error"
	}
	f, err := os.Open(p)
	if err != nil {
		return policy.Decision{}, "policy-error"
	}
	defer f.Close()
	e, err := policy.Load(f)
	if err != nil {
		return policy.Decision{}, "policy-error"
	}
	a, err := policy.ParseHook(in)
	if err != nil {
		return policy.Decision{}, "input-error"
	}
	return e.Evaluate(a), ""
}

// Run emits one decision. A valid allow/ask/deny exits 0; configuration/input
// errors emit deny and exit 2. Output failure exits 2. The caller must deny on
// nonzero exit, missing/malformed output, crash or timeout; ask is not permission.
func Run(in io.Reader, out io.Writer, args []string) int {
	d, failure := evaluate(in, args)
	code := 0
	if failure != "" {
		d = policy.Result("deny", "S1 evaluation failed: "+failure, failure)
		code = 2
	}
	if err := json.NewEncoder(out).Encode(d); err != nil {
		return 2
	}
	return code
}
