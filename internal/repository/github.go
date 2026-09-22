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
// posture decision. ID is the immutable identity bound by trusted policy. The
// API response digest is retained separately as Evidence.
type Metadata struct {
	ID            int64  `json:"id"`
	FullName      string `json:"full_name"`
	DefaultBranch string `json:"default_branch"`
	Archived      bool   `json:"archived"`
	Disabled      bool   `json:"disabled"`
}

// BranchMetadata contains the authoritative branch fields available from the
// general branch endpoint. Protected is narrower than effective Rules details:
// it supports current-branch exclusion but not rule-parameter assertions.
type BranchMetadata struct {
	Name      string
	Protected bool
}

// GitHub supplies current GitHub state. Implementations must authenticate to
// GitHub itself and must not accept repository-selected API endpoints.
type GitHub interface {
	Repository(context.Context, string) (Metadata, string, error)
	Branch(context.Context, string, string) (BranchMetadata, string, error)
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
	var response struct {
		ID            *int64 `json:"id"`
		FullName      string `json:"full_name"`
		DefaultBranch string `json:"default_branch"`
		Archived      *bool  `json:"archived"`
		Disabled      *bool  `json:"disabled"`
	}
	digest, err := c.get(ctx, path, &response)
	if err != nil {
		return Metadata{}, "", err
	}
	if response.ID == nil || *response.ID <= 0 || !repositoryName.MatchString(response.FullName) || response.DefaultBranch == "" || response.Archived == nil || response.Disabled == nil {
		return Metadata{}, "", fmt.Errorf("GitHub metadata omitted required identity, state, or default branch")
	}
	return Metadata{
		ID:            *response.ID,
		FullName:      response.FullName,
		DefaultBranch: response.DefaultBranch,
		Archived:      *response.Archived,
		Disabled:      *response.Disabled,
	}, digest, nil
}

// Branch gets the exact branch's protected flag from GitHub's general branch
// metadata endpoint. Missing or malformed state fails closed; this method does
// not infer detailed protection rules from the boolean.
func (c *APIClient) Branch(ctx context.Context, name, branch string) (BranchMetadata, string, error) {
	path, err := repositoryPath(name)
	if err != nil {
		return BranchMetadata{}, "", err
	}
	if !validBranch(branch) {
		return BranchMetadata{}, "", fmt.Errorf("invalid branch identity")
	}
	var response struct {
		Name      string `json:"name"`
		Protected *bool  `json:"protected"`
	}
	digest, err := c.get(ctx, path+"/branches/"+url.PathEscape(branch), &response)
	if err != nil {
		return BranchMetadata{}, "", err
	}
	if response.Name == "" || response.Protected == nil {
		return BranchMetadata{}, "", fmt.Errorf("GitHub branch metadata omitted required name or protected state")
	}
	return BranchMetadata{Name: response.Name, Protected: *response.Protected}, digest, nil
}

// BranchHead returns the exact GitHub branch ref and its commit object ID for
// Publication Guard. The repository name comes from fresh Repository
// Authority evidence, while this method independently fails closed on a
// missing ref, a symbolic/non-commit object, or malformed identity.
func (c *APIClient) BranchHead(ctx context.Context, name, branch string) (string, string, error) {
	path, err := repositoryPath(name)
	if err != nil {
		return "", "", err
	}
	if !validBranch(branch) {
		return "", "", fmt.Errorf("invalid branch identity")
	}
	var response struct {
		Ref    string `json:"ref"`
		Object struct {
			Type string `json:"type"`
			SHA  string `json:"sha"`
		} `json:"object"`
	}
	digest, err := c.get(ctx, path+"/git/ref/heads/"+url.PathEscape(branch), &response)
	if err != nil {
		return "", "", err
	}
	if response.Ref != "refs/heads/"+branch || response.Object.Type != "commit" || !validGitObjectID(response.Object.SHA) {
		return "", "", fmt.Errorf("GitHub branch ref omitted or mismatched required commit identity")
	}
	return response.Object.SHA, digest, nil
}

// EffectiveRuleTypes gets the current rule types GitHub reports as applying to
// the named branch. It does not infer rules from repository-controlled files.
func (c *APIClient) EffectiveRuleTypes(ctx context.Context, name, branch string) (map[string]bool, string, error) {
	path, err := repositoryPath(name)
	if err != nil {
		return nil, "", err
	}
	var rules []struct {
		Type *string `json:"type"`
	}
	digest, err := c.get(ctx, path+"/rules/branches/"+url.PathEscape(branch), &rules)
	if err != nil {
		return nil, "", err
	}
	types := make(map[string]bool, len(rules))
	for _, rule := range rules {
		if rule.Type == nil || *rule.Type == "" {
			return nil, "", fmt.Errorf("GitHub rule omitted required type")
		}
		types[*rule.Type] = true
	}
	return types, digest, nil
}
