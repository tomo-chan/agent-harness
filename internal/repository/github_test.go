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
			_, _ = w.Write([]byte(`{"full_name":"acme/widget","default_branch":"main","archived":false,"disabled":false}`))
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
	if err != nil || metadata.FullName != "acme/widget" || metadataDigest == "" {
		t.Fatalf("metadata=%+v digest=%q err=%v", metadata, metadataDigest, err)
	}
	rules, rulesDigest, err := client.EffectiveRuleTypes(context.Background(), "acme/widget", "main")
	if err != nil || !rules["pull_request"] || !rules["non_fast_forward"] || rulesDigest == "" {
		t.Fatalf("rules=%+v digest=%q err=%v", rules, rulesDigest, err)
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
