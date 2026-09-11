package policy

import (
	"os"
	"strings"
	"testing"
)

func TestPythonS1Vectors(t *testing.T) {
	f, err := os.Open("../../reference/policies/policy.example.json")
	if err != nil {
		t.Fatal(err)
	}
	defer f.Close()
	e, err := Load(f)
	if err != nil {
		t.Fatal(err)
	}
	for _, tc := range []struct{ command, want string }{
		{"git status", "allow"}, {"git diff", "allow"},
		{"git push --force origin feature/x", "deny"},
		{"git push origin main", "deny"},
		{"gh pr merge 42 --squash", "ask"},
		{"some-new-tool --mutate", "ask"},
	} {
		t.Run(tc.command, func(t *testing.T) {
			if d := e.Evaluate(Action{"exec", tc.command}); d.Decision != tc.want {
				t.Fatalf("got %+v, want %s", d, tc.want)
			}
		})
	}
}

func TestPriorityAndPredicates(t *testing.T) {
	for _, tc := range []struct{ p, want, rule string }{
		{`{"allow":[{"id":"a"}],"ask":[{"id":"q"}],"deny":[{"id":"d"}]}`, "deny", "d"},
		{`{"allow":[{}],"ask":[{"id":"q"}]}`, "ask", "q"},
		{`{"deny":[{"id":"first"},{"id":"second"}]}`, "deny", "first"},
		{`{"allow":[{"id":"all","tool_regex":"^exec$","command_regex":"^git status$","action_regex":"^exec\\ngit status$"}]}`, "allow", "all"},
		{`{"deny":[{"tool_regex":"Bash","command_regex":"git status"}]}`, "ask", "default"},
		{`{}`, "ask", "default"},
		{`{"default":"deny"}`, "deny", "default"},
		{`{"default":"allow"}`, "allow", "default"},
	} {
		e, err := Load(strings.NewReader(tc.p))
		if err != nil {
			t.Fatal(err)
		}
		d := e.Evaluate(Action{"exec", "git status"})
		if d.Decision != tc.want || d.Rule == nil || *d.Rule != tc.rule {
			t.Fatalf("%s: %+v", tc.p, d)
		}
	}
}

func TestDecisionEvidenceIdentifiesPolicyAndNormalizedAction(t *testing.T) {
	e, err := Load(strings.NewReader(`{"default":"ask"}`))
	if err != nil {
		t.Fatal(err)
	}
	d := e.Evaluate(Action{"exec", "git status"})
	if d.Evidence == nil || len(d.Evidence.PolicySHA256) != 64 || len(d.Evidence.ActionSHA256) != 64 {
		t.Fatalf("missing evidence: %+v", d)
	}
	if other := e.Evaluate(Action{"Bash", "git status"}); other.Evidence.ActionSHA256 == d.Evidence.ActionSHA256 {
		t.Fatal("tool identity must be part of normalized action evidence")
	}
	e2, err := Load(strings.NewReader("{\n\"default\":\"ask\"}"))
	if err != nil {
		t.Fatal(err)
	}
	if other := e2.Evaluate(Action{"exec", "git status"}); other.Evidence.PolicySHA256 == d.Evidence.PolicySHA256 {
		t.Fatal("exact policy bytes must identify policy evidence")
	}
}

func TestInvalidPolicies(t *testing.T) {
	for _, p := range []string{
		`null`, `[]`, `{`, `{} {}`, `{"default":"permit"}`, `{"default":null}`,
		`{"allow":null}`, `{"deny":{}}`, `{"ask":[null]}`, `{"allow":[3]}`,
		`{"unknown":true}`, `{"allow":[{"unknown":"x"}]}`,
		`{"deny":[{"command_regex":"["}]}`, `{"allow":[{"tool_regex":1}]}`,
		`{"allow":[{"id":null}]}`, `{"allow":[{"reason":false}]}`,
		`{"default":"deny","default":"allow"}`, `{"allow":[{"id":"a","id":"b"}]}`,
		`{"deny":[{"command_regex":"(?=python-only)"}]}`,
		strings.Repeat(" ", MaxJSON+1),
		`{"x":` + strings.Repeat("[", 66) + strings.Repeat("]", 66) + `}`,
		string([]byte{'{', '"', 'x', '"', ':', '"', 0xff, '"', '}'}),
	} {
		if _, err := Load(strings.NewReader(p)); err == nil {
			t.Errorf("accepted invalid policy %.100s", p)
		}
	}
}

func TestHookParsing(t *testing.T) {
	for _, raw := range []string{
		`{"tool":"exec","input":{"command":"git status"}}`,
		`{"tool_name":"exec","tool_input":{"command":["git","status"]},"cwd":"/untrusted"}`,
	} {
		a, err := ParseHook(strings.NewReader(raw))
		if err != nil || a != (Action{"exec", "git status"}) {
			t.Fatalf("%+v %v", a, err)
		}
	}
	if _, err := ParseHook(strings.NewReader(`{"tool":"Read","input":{"path":"x"}}`)); err != nil {
		t.Fatal(err)
	}
	for _, raw := range []string{
		`null`, `[]`, `{}`, `{"tool":3,"input":{}}`, `{"tool":"","input":{}}`,
		`{"tool":"exec","input":null}`, `{"tool":"exec","input":{}}`,
		`{"tool":"exec","input":{"command":null}}`,
		`{"tool":"exec","input":{"command":["git",2]}}`,
		`{"tool":"exec","tool_name":"Bash","input":{"command":"x"}}`,
		`{"tool":"exec","input":{},"tool_input":{}}`,
		`{"tool":"exec","input":{"command":"x","command":"y"}}`,
		`{"tool":"exec","input":{"command":"x"},"policy":"evil"}`,
		`{"tool":"exec","input":{"command":"x"}} false`,
	} {
		if _, err := ParseHook(strings.NewReader(raw)); err == nil {
			t.Errorf("accepted %s", raw)
		}
	}
}
