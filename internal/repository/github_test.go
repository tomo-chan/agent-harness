package repository

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestAPIClientReadsMetadataAndEffectiveRules(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("Authorization") != "Bearer test-token" {
			t.Errorf("missing authorization header")
		}
		switch r.URL.Path {
		case "/repos/acme/widget":
			_, _ = w.Write([]byte(`{"id":123456,"full_name":"acme/widget","default_branch":"main","archived":false,"disabled":false}`))
		case "/repos/acme/widget/branches/feature/task":
			_, _ = w.Write([]byte(`{"name":"feature/task","protected":false}`))
		case "/repos/acme/widget/git/ref/heads/feature/task":
			_, _ = w.Write([]byte(`{"ref":"refs/heads/feature/task","object":{"type":"commit","sha":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}}`))
		case "/repos/acme/widget/rules/branches/main":
			_, _ = w.Write([]byte(`[{"type":"pull_request"},{"type":"non_fast_forward"}]`))
		default:
			http.NotFound(w, r)
		}
	}))
	defer server.Close()

	client := NewGitHubClient("test-token")
	client.baseURL = server.URL
	metadata, metadataDigest, err := client.Repository(context.Background(), "acme/widget")
	if err != nil || metadata.ID != 123456 || metadata.FullName != "acme/widget" || metadataDigest == "" {
		t.Fatalf("metadata=%+v digest=%q err=%v", metadata, metadataDigest, err)
	}
	branch, branchDigest, err := client.Branch(context.Background(), "acme/widget", "feature/task")
	if err != nil || branch.Name != "feature/task" || branch.Protected || branchDigest == "" {
		t.Fatalf("branch=%+v digest=%q err=%v", branch, branchDigest, err)
	}
	head, headDigest, err := client.BranchHead(context.Background(), "acme/widget", "feature/task")
	if err != nil || head != "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa" || headDigest == "" {
		t.Fatalf("head=%q digest=%q err=%v", head, headDigest, err)
	}
	rules, rulesDigest, err := client.EffectiveRuleTypes(context.Background(), "acme/widget", "main")
	if err != nil || !rules["pull_request"] || !rules["non_fast_forward"] || rulesDigest == "" {
		t.Fatalf("rules=%+v digest=%q err=%v", rules, rulesDigest, err)
	}
}

func TestAPIClientBranchHeadFailsClosedOnMismatchedRefOrObject(t *testing.T) {
	for _, body := range []string{
		`{"ref":"refs/heads/other","object":{"type":"commit","sha":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}}`,
		`{"ref":"refs/heads/feature/task","object":{"type":"tag","sha":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}}`,
		`{"ref":"refs/heads/feature/task","object":{"type":"commit","sha":"invalid"}}`,
		`{"ref":"refs/heads/feature/task","object":{"type":"commit"}}`,
	} {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
			_, _ = w.Write([]byte(body))
		}))
		client := NewGitHubClient("")
		client.baseURL = server.URL
		if _, _, err := client.BranchHead(context.Background(), "acme/widget", "feature/task"); err == nil {
			t.Errorf("accepted malformed GitHub branch ref: %s", body)
		}
		server.Close()
	}
}

func TestAPIClientRejectsMissingBranchProtectionState(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		_, _ = w.Write([]byte(`{"name":"feature/task"}`))
	}))
	defer server.Close()
	client := NewGitHubClient("")
	client.baseURL = server.URL
	if _, _, err := client.Branch(context.Background(), "acme/widget", "feature/task"); err == nil {
		t.Fatal("accepted GitHub branch metadata without protected state")
	}
}

func TestAPIClientBranchFailsClosedOnUnavailableSource(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusForbidden)
		_, _ = w.Write([]byte(`{"message":"unavailable"}`))
	}))
	defer server.Close()
	client := NewGitHubClient("")
	client.baseURL = server.URL
	if _, _, err := client.Branch(context.Background(), "acme/widget", "feature/task"); err == nil {
		t.Fatal("unavailable GitHub branch authority source was accepted")
	}
}

func TestAPIClientFailsClosedOnStatusAndInvalidResponse(t *testing.T) {
	for _, tc := range []struct {
		status int
		body   string
	}{
		{http.StatusForbidden, `{}`},
		{http.StatusOK, `{`},
		{http.StatusOK, `{"full_name":"acme/widget"}`},
		{http.StatusOK, `{"id":123456,"full_name":"acme/widget","default_branch":"main"}`},
		{http.StatusOK, `{"id":123456,"full_name":"acme/widget","default_branch":"main","archived":false}`},
	} {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
			w.WriteHeader(tc.status)
			_, _ = w.Write([]byte(tc.body))
		}))
		client := NewGitHubClient("")
		client.baseURL = server.URL
		if _, _, err := client.Repository(context.Background(), "acme/widget"); err == nil {
			t.Errorf("accepted status=%d body=%q", tc.status, tc.body)
		}
		server.Close()
	}
}

func TestAPIClientRejectsRuleWithoutType(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		_, _ = w.Write([]byte(`[{}]`))
	}))
	defer server.Close()
	client := NewGitHubClient("")
	client.baseURL = server.URL
	if _, _, err := client.EffectiveRuleTypes(context.Background(), "acme/widget", "feature/task"); err == nil {
		t.Fatal("accepted GitHub rule without type")
	}
}
