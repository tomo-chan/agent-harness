package repository

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"
	"time"
)

const githubAPI = "https://api.github.com"

// Metadata contains the authoritative GitHub repository fields used by the
// posture decision. The API response digest is retained separately as Evidence.
type Metadata struct {
	FullName      string `json:"full_name"`
	DefaultBranch string `json:"default_branch"`
	Archived      bool   `json:"archived"`
	Disabled      bool   `json:"disabled"`
}

// GitHub supplies current GitHub state. Implementations must authenticate to
// GitHub itself and must not accept repository-selected API endpoints.
type GitHub interface {
	Repository(context.Context, string) (Metadata, string, error)
	EffectiveRuleTypes(context.Context, string, string) (map[string]bool, string, error)
}

// APIClient reads authoritative state from the fixed public GitHub API. It does
// not honor proxy environment variables or redirects. A deployment-supplied
// token changes access, but cannot select the server or weaken validation.
type APIClient struct {
	client  *http.Client
	token   string
	baseURL string
}

// NewGitHubClient constructs the production GitHub client. The token should be
// short-lived and repository-scoped; an absent or insufficient token may cause
// protected-repository queries to fail closed.
func NewGitHubClient(token string) *APIClient {
	transport := http.DefaultTransport.(*http.Transport).Clone()
	transport.Proxy = nil
	return &APIClient{
		client: &http.Client{
			Transport: transport,
			Timeout:   10 * time.Second,
			CheckRedirect: func(_ *http.Request, _ []*http.Request) error {
				return fmt.Errorf("GitHub API redirect refused")
			},
		},
		token:   token,
		baseURL: githubAPI,
	}
}

func (c *APIClient) get(ctx context.Context, path string, target any) (string, error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, c.baseURL+path, nil)
	if err != nil {
		return "", err
	}
	req.Header.Set("Accept", "application/vnd.github+json")
	req.Header.Set("X-GitHub-Api-Version", "2022-11-28")
	req.Header.Set("User-Agent", "agent-harness")
	if c.token != "" {
		req.Header.Set("Authorization", "Bearer "+c.token)
	}
	response, err := c.client.Do(req)
	if err != nil {
		return "", fmt.Errorf("GitHub API request failed: %w", err)
	}
	defer response.Body.Close()
	if response.StatusCode < 200 || response.StatusCode >= 300 {
		return "", fmt.Errorf("GitHub API returned HTTP %d", response.StatusCode)
	}
	b, err := io.ReadAll(io.LimitReader(response.Body, 1<<20+1))
	if err != nil {
		return "", fmt.Errorf("GitHub API response read failed: %w", err)
	}
	if len(b) > 1<<20 {
		return "", fmt.Errorf("GitHub API response exceeds size limit")
	}
	decoder := json.NewDecoder(strings.NewReader(string(b)))
	if err := decoder.Decode(target); err != nil {
		return "", fmt.Errorf("invalid GitHub API JSON: %w", err)
	}
	if decoder.Decode(new(any)) != io.EOF {
		return "", fmt.Errorf("trailing GitHub API JSON")
	}
	digest := sha256.Sum256(b)
	return hex.EncodeToString(digest[:]), nil
}

func repositoryPath(name string) (string, error) {
	parts := strings.Split(name, "/")
	if len(parts) != 2 || !repositoryName.MatchString(name) {
		return "", fmt.Errorf("invalid repository identity")
	}
	return "/repos/" + url.PathEscape(parts[0]) + "/" + url.PathEscape(parts[1]), nil
}

// Repository gets canonical identity and default-branch metadata from GitHub.
func (c *APIClient) Repository(ctx context.Context, name string) (Metadata, string, error) {
	path, err := repositoryPath(name)
	if err != nil {
		return Metadata{}, "", err
	}
	var metadata Metadata
	digest, err := c.get(ctx, path, &metadata)
	if err != nil {
		return Metadata{}, "", err
	}
	if !repositoryName.MatchString(metadata.FullName) || metadata.DefaultBranch == "" {
		return Metadata{}, "", fmt.Errorf("GitHub metadata omitted required identity or default branch")
	}
	return metadata, digest, nil
}

// EffectiveRuleTypes gets the current rule types GitHub reports as applying to
// the named branch. It does not infer rules from repository-controlled files.
func (c *APIClient) EffectiveRuleTypes(ctx context.Context, name, branch string) (map[string]bool, string, error) {
	path, err := repositoryPath(name)
	if err != nil {
		return nil, "", err
	}
	var rules []struct {
		Type string `json:"type"`
	}
	digest, err := c.get(ctx, path+"/rules/branches/"+url.PathEscape(branch), &rules)
	if err != nil {
		return nil, "", err
	}
	types := make(map[string]bool, len(rules))
	for _, rule := range rules {
		if rule.Type != "" {
			types[rule.Type] = true
		}
	}
	return types, digest, nil
}
