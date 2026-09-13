// Package publication classifies and validates directly observable source-code
// publication commands.
//
// The package deliberately recognizes a narrow autonomous normal form instead
// of implementing a general shell parser. Repository identity, worktree
// binding, branch protection, and default-branch authority come from a fresh
// repository.Report produced by Repository Authority / Posture. This package
// does not review control-plane diffs, authorize merges/releases/deployments,
// replace GitHub server-side rules, or prove that a vendor executor invokes the
// same executable and environment that were evaluated.
package publication

import (
	"context"
	"fmt"
	"sort"
	"strings"
	"time"
	"unicode"

	"github.com/tomo-chan/agent-harness/internal/policy"
	"github.com/tomo-chan/agent-harness/internal/repository"
)

// Kind identifies the direct publication meaning recognized in an action.
type Kind string

const (
	// KindGitPush is a recognizable direct Git push candidate.
	KindGitPush Kind = "git_push"
	// KindPullRequestCreate is a recognizable GitHub pull-request creation
	// candidate.
	KindPullRequestCreate Kind = "github_pull_request_create"
	// KindAmbiguous means multiple or unclear publication meanings were found.
	KindAmbiguous Kind = "ambiguous_publication"
)

// Classification separates publication candidates from ordinary repository
// mutation. Candidate detection is intentionally broader than the autonomous
// normal forms so compound or wrapped commands cannot inherit a lower policy's
// allow decision merely because canonical validation does not understand them.
type Classification struct {
	Candidate bool
	Kind      Kind
	Compound  bool
	Ambiguous bool
}

var shellTools = map[string]struct{}{"Bash": {}, "exec": {}}

// Classify recognizes observable git push and gh pr create text in fixed shell
// tools. False positives are safe because classification grants no authority;
// an unrecognized or syntactically ambiguous shell mutation remains governed
// by Repository Authority and the lower policy's non-allow result.
func Classify(action policy.Action) Classification {
	if _, ok := shellTools[action.Tool]; !ok {
		return Classification{}
	}
	command, err := policy.Command(action)
	if err != nil {
		return Classification{}
	}
	words := commandWords(command)
	push := containsOrdered(words, "git", "push")
	pr := containsOrdered(words, "gh", "pr", "create")
	classification := Classification{
		Candidate: push || pr,
		Compound:  strings.ContainsAny(command, ";&|<>\n\r"),
		Ambiguous: strings.ContainsAny(command, "'\"`\\$()") || (push && pr),
	}
	switch {
	case push && !pr:
		classification.Kind = KindGitPush
	case pr && !push:
		classification.Kind = KindPullRequestCreate
	case push || pr:
		classification.Kind = KindAmbiguous
	}
	return classification
}

func commandWords(command string) []string {
	return strings.FieldsFunc(strings.ToLower(command), func(r rune) bool {
		return !(unicode.IsLetter(r) || unicode.IsDigit(r) || r == '_' || r == '-')
	})
}

func containsOrdered(words []string, sequence ...string) bool {
	for start, word := range words {
		if word != sequence[0] {
			continue
		}
		matched := 1
		for i := start + 1; i < len(words) && matched < len(sequence); i++ {
			if words[i] == sequence[matched] {
				matched++
			}
		}
		if matched == len(sequence) {
			return true
		}
	}
	return false
}

// GitHub supplies the authoritative published branch head used for PR
// creation. Implementations must use a trusted fixed GitHub endpoint and fail
// closed on missing or malformed refs.
type GitHub interface {
	BranchHead(context.Context, string, string) (string, string, error)
}

type assessment struct {
	decision policy.Decision
	evidence *policy.PublicationEvidence
}

func newAssessment(result policy.Decision, classification Classification, report repository.Report, now time.Time) (*assessment, error) {
	if result.Evidence == nil {
		return nil, fmt.Errorf("policy evidence is required for publication")
	}
	evidence := &policy.PublicationEvidence{
		Kind:          string(classification.Kind),
		Repository:    report.Repository,
		Branch:        report.Branch,
		LocalHeadSHA:  report.HeadSHA,
		DefaultBranch: report.DefaultBranch,
		CheckedAt:     now.UTC().Format(time.RFC3339Nano),
	}
	result.Evidence.Publication = evidence
	return &assessment{decision: result, evidence: evidence}, nil
}

func (a *assessment) add(name, status, detail string) {
	a.evidence.Checks = append(a.evidence.Checks, policy.PublicationCheckEvidence{
		Name: name, Status: status, Detail: detail,
	})
}

func (a *assessment) decide(outcome, reason, rule string) policy.Decision {
	decision := policy.Result(outcome, reason, rule)
	decision.Evidence = a.decision.Evidence
	return decision
}

func (a *assessment) unknown(name, detail string, err error) (policy.Decision, error) {
	a.add(name, "unknown", detail)
	return a.decide("deny", "publication evidence is unavailable", "publication-evidence-error"), err
}

func sensitiveEnvironment(environment []string) []string {
	blocked := map[string]struct{}{
		"GH_CONFIG_DIR": {}, "GH_HOST": {}, "GH_REPO": {},
		"GIT_ALTERNATE_OBJECT_DIRECTORIES": {}, "GIT_ALLOW_PROTOCOL": {},
		"GIT_CEILING_DIRECTORIES": {}, "GIT_COMMON_DIR": {}, "GIT_CONFIG": {},
		"GIT_CONFIG_COUNT": {}, "GIT_CONFIG_GLOBAL": {}, "GIT_CONFIG_NOSYSTEM": {},
		"GIT_CONFIG_SYSTEM": {}, "GIT_DIR": {}, "GIT_DISCOVERY_ACROSS_FILESYSTEM": {},
		"GIT_EXEC_PATH": {}, "GIT_INDEX_FILE": {}, "GIT_NAMESPACE": {},
		"GIT_OBJECT_DIRECTORY": {}, "GIT_PROTOCOL_FROM_USER": {}, "GIT_PROXY_COMMAND": {},
		"GIT_REPLACE_REF_BASE": {}, "GIT_SHALLOW_FILE": {}, "GIT_SSH": {},
		"GIT_SSH_COMMAND": {}, "GIT_WORK_TREE": {},
	}
	found := map[string]struct{}{}
	for _, item := range environment {
		name, value, ok := strings.Cut(item, "=")
		if !ok || value == "" {
			continue
		}
		_, exact := blocked[name]
		generatedConfig := strings.HasPrefix(name, "GIT_CONFIG_KEY_") || strings.HasPrefix(name, "GIT_CONFIG_VALUE_")
		if exact || generatedConfig {
			found[name] = struct{}{}
		}
	}
	names := make([]string, 0, len(found))
	for name := range found {
		names = append(names, name)
	}
	sort.Strings(names)
	return names
}

func isSimpleCommand(command string) bool {
	return !strings.ContainsAny(command, ";&|<>\n\r'\"`\\$()")
}

func forceOrBulkPush(tokens []string) bool {
	for _, token := range tokens[2:] {
		if token == "-f" || token == "--force" || strings.HasPrefix(token, "--force=") ||
			strings.HasPrefix(token, "--force-with-lease") || strings.HasPrefix(token, "--force-if-includes") ||
			token == "--mirror" || token == "--all" || token == "--tags" || token == "--delete" ||
			strings.HasPrefix(token, "+") ||
			(strings.HasPrefix(token, "-") && !strings.HasPrefix(token, "--") && strings.Contains(token[1:], "f")) {
			return true
		}
	}
	return false
}

func hasPRTargetOverride(tokens []string) bool {
	// Scan the whole argv-shaped token list because gh/Cobra may accept
	// persistent flags before an intermediate subcommand as well as after
	// `create`. Canonical validation separately requires the exact command.
	for _, token := range tokens {
		if token == "--repo" || token == "--head" || token == "--base" || token == "-R" || token == "-H" || token == "-B" ||
			strings.HasPrefix(token, "--repo=") || strings.HasPrefix(token, "--head=") || strings.HasPrefix(token, "--base=") ||
			(strings.HasPrefix(token, "-R") && token != "-R") ||
			(strings.HasPrefix(token, "-H") && token != "-H") ||
			(strings.HasPrefix(token, "-B") && token != "-B") {
			return true
		}
	}
	return false
}

func configNames(ctx context.Context, git repository.Git, cwd string) ([]string, error) {
	// SystemGit already removes global/system configuration. Omitting a scope
	// here intentionally includes both common local and per-worktree config,
	// matching the repository-controlled sources the real Git/gh command could
	// observe. Include directives themselves are read but never expanded.
	raw, err := git.Run(ctx, cwd, "config", "--no-includes", "--name-only", "--list")
	if err != nil {
		return nil, err
	}
	if raw == "" {
		return nil, nil
	}
	return strings.Split(raw, "\n"), nil
}

func configIncludes(names []string) bool {
	for _, raw := range names {
		name := strings.ToLower(strings.TrimSpace(raw))
		if name == "include.path" || (strings.HasPrefix(name, "includeif.") && strings.HasSuffix(name, ".path")) {
			return true
		}
	}
	return false
}

func configHas(names []string, key string) bool {
	for _, name := range names {
		if strings.EqualFold(strings.TrimSpace(name), key) {
			return true
		}
	}
	return false
}

func (a *assessment) observeCommon(ctx context.Context, action policy.Action, report repository.Report, git repository.Git) ([]string, *policy.Decision, error) {
	branch, err := git.Run(ctx, action.CWD, "rev-parse", "--abbrev-ref", "HEAD")
	if err != nil {
		decision, queryErr := a.unknown("current_branch", "current branch query failed", err)
		return nil, &decision, queryErr
	}
	if branch != report.Branch || branch == "" || branch == "HEAD" {
		a.add("current_branch", "fail", "current branch changed after repository authority evaluation")
		decision := a.decide("deny", "current branch does not match fresh repository authority", "publication-branch")
		return nil, &decision, nil
	}
	a.add("current_branch", "pass", branch)

	head, err := git.Run(ctx, action.CWD, "rev-parse", "HEAD")
	if err != nil {
		decision, queryErr := a.unknown("local_head", "local HEAD query failed", err)
		return nil, &decision, queryErr
	}
	if head != report.HeadSHA {
		a.add("local_head", "fail", "local HEAD changed after repository authority evaluation")
		decision := a.decide("deny", "local HEAD does not match fresh repository authority", "publication-head")
		return nil, &decision, nil
	}
	a.evidence.LocalHeadSHA = head
	a.add("local_head", "pass", head)

	remoteValues, err := git.Run(ctx, action.CWD, "config", "--no-includes", "--get-all", "remote.origin.url")
	if err != nil {
		decision, queryErr := a.unknown("origin", "origin query failed", err)
		return nil, &decision, queryErr
	}
	remotes := nonemptyLines(remoteValues)
	if len(remotes) != 1 {
		a.add("origin", "fail", "canonical publication requires exactly one origin fetch URL")
		decision := a.decide("deny", "origin target is ambiguous", "publication-origin")
		return nil, &decision, nil
	}
	remote := remotes[0]
	a.evidence.Remote = remote
	remoteRepository, ok := repository.ParseGitHubRepository(remote)
	if !ok || !strings.EqualFold(remoteRepository, report.Repository) {
		a.add("origin", "fail", "origin does not match the repository authority identity")
		decision := a.decide("deny", "origin no longer matches fresh repository authority", "publication-origin")
		return nil, &decision, nil
	}
	a.add("origin", "pass", remoteRepository)

	names, err := configNames(ctx, git, action.CWD)
	if err != nil {
		decision, queryErr := a.unknown("local_git_config", "local Git config names cannot be inspected", err)
		return nil, &decision, queryErr
	}
	if configIncludes(names) {
		a.add("local_git_config", "fail", "repository-controlled Git include directives are not allowed for publication")
		decision := a.decide("deny", "included Git config can change publication semantics", "publication-git-config")
		return nil, &decision, nil
	}
	a.add("local_git_config", "pass", "repository-controlled config names inspected without includes")
	return names, nil, nil
}

func (a *assessment) validatePush(ctx context.Context, action policy.Action, report repository.Report, git repository.Git, tokens []string) (policy.Decision, error) {
	refspec := "HEAD:refs/heads/" + report.Branch
	normal := []string{"git", "push", "origin", refspec}
	first := []string{"git", "push", "--set-upstream", "origin", refspec}
	firstPublication := equalTokens(tokens, first)
	if !equalTokens(tokens, normal) && !firstPublication {
		if len(tokens) >= 4 && tokens[0] == "git" && tokens[1] == "push" {
			candidateRefspec := tokens[len(tokens)-1]
			if strings.Contains(candidateRefspec, ":") && candidateRefspec != refspec {
				a.evidence.Refspec = candidateRefspec
				a.add("refspec", "fail", "refspec does not publish current HEAD to the current feature branch")
				return a.decide("deny", "publication refspec does not match the current feature branch", "publication-refspec"), nil
			}
		}
		a.add("command_form", "fail", "push is outside the narrow autonomous normal form")
		return a.decide("ask", "noncanonical push requires external authorization", "noncanonical-publication"), nil
	}
	a.evidence.Refspec = refspec
	a.add("command_form", "pass", strings.Join(tokens, " "))
	a.add("refspec", "pass", refspec)

	names, decision, err := a.observeCommon(ctx, action, report, git)
	if decision != nil || err != nil {
		return *decision, err
	}

	pushURLs, err := git.Run(ctx, action.CWD, "remote", "get-url", "--push", "--all", "origin")
	if err != nil {
		return a.unknown("push_url", "effective push URL query failed", err)
	}
	urls := nonemptyLines(pushURLs)
	if len(urls) != 1 {
		a.add("push_url", "fail", "canonical push requires exactly one effective push URL")
		return a.decide("deny", "effective push target is ambiguous", "publication-push-target"), nil
	}
	a.evidence.PushURL = urls[0]
	pushRepository, ok := repository.ParseGitHubRepository(urls[0])
	if !ok || !strings.EqualFold(pushRepository, report.Repository) {
		a.add("push_url", "fail", "effective push URL does not match repository authority")
		return a.decide("deny", "effective push target does not match repository authority", "publication-push-target"), nil
	}
	a.add("push_url", "pass", pushRepository)

	if configHas(names, "remote.origin.mirror") {
		mirrorValues, err := git.Run(ctx, action.CWD, "config", "--no-includes", "--bool", "--get-all", "remote.origin.mirror")
		if err != nil {
			return a.unknown("mirror", "remote.origin.mirror cannot be evaluated", err)
		}
		mirrors := nonemptyLines(mirrorValues)
		if len(mirrors) != 1 || mirrors[0] != "false" {
			a.add("mirror", "fail", "remote.origin.mirror is enabled")
			return a.decide("deny", "mirror publication is not autonomous", "publication-mirror"), nil
		}
	}
	a.add("mirror", "pass", "origin is not a mirror remote")

	if configHas(names, "push.followTags") {
		followTagValues, err := git.Run(ctx, action.CWD, "config", "--no-includes", "--bool", "--get-all", "push.followTags")
		if err != nil {
			return a.unknown("follow_tags", "push.followTags cannot be evaluated", err)
		}
		values := nonemptyLines(followTagValues)
		if len(values) != 1 {
			a.add("follow_tags", "fail", "push.followTags has ambiguous values")
			return a.decide("deny", "implicit tag publication is ambiguous", "publication-follow-tags"), nil
		}
		if values[0] != "false" {
			a.add("follow_tags", "fail", "push.followTags enables implicit annotated-tag publication")
			return a.decide("deny", "implicit tag publication is prohibited from the autonomous path", "publication-follow-tags"), nil
		}
	}
	a.add("follow_tags", "pass", "implicit annotated-tag publication is disabled")

	remoteKey := "branch." + report.Branch + ".remote"
	mergeKey := "branch." + report.Branch + ".merge"
	if firstPublication {
		if configHas(names, remoteKey) || configHas(names, mergeKey) {
			a.add("upstream", "fail", "first-publication form cannot replace existing upstream config")
			return a.decide("deny", "--set-upstream is only allowed before an upstream exists", "publication-upstream"), nil
		}
		a.add("upstream", "pass", "no upstream is configured")
	} else {
		upstream, err := git.Run(ctx, action.CWD, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
		if err != nil {
			return a.unknown("upstream", "configured upstream cannot be resolved", err)
		}
		a.evidence.Upstream = upstream
		expected := "origin/" + report.Branch
		if upstream != expected {
			a.add("upstream", "fail", "upstream does not match origin/current branch")
			return a.decide("deny", "upstream does not match the publication branch", "publication-upstream"), nil
		}
		a.add("upstream", "pass", upstream)
	}
	return a.decision, nil
}

func (a *assessment) validatePullRequest(ctx context.Context, action policy.Action, report repository.Report, git repository.Git, github GitHub, tokens []string) (policy.Decision, error) {
	if hasPRTargetOverride(tokens) {
		a.add("target_override", "fail", "repository, head, or base override is present")
		return a.decide("deny", "autonomous PR creation cannot override repository, head, or base", "publication-pr-target"), nil
	}
	canonical := []string{"gh", "pr", "create", "--fill"}
	if !equalTokens(tokens, canonical) {
		a.add("command_form", "fail", "PR creation is outside the narrow autonomous normal form")
		return a.decide("ask", "noncanonical PR creation requires external authorization", "noncanonical-publication"), nil
	}
	a.add("command_form", "pass", strings.Join(tokens, " "))
	a.evidence.PullRequestBase = report.DefaultBranch

	names, decision, err := a.observeCommon(ctx, action, report, git)
	if decision != nil || err != nil {
		return *decision, err
	}

	mergeBaseKey := "branch." + report.Branch + ".gh-merge-base"
	if configHas(names, mergeBaseKey) {
		a.add("implicit_base", "fail", "repository-controlled branch gh-merge-base is configured")
		return a.decide("deny", "repository Git config can override the implicit PR base", "publication-pr-base"), nil
	}
	a.add("implicit_base", "pass", "no branch gh-merge-base override; fresh GitHub default branch is authoritative")

	upstream, err := git.Run(ctx, action.CWD, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
	if err != nil {
		return a.unknown("upstream", "configured upstream cannot be resolved", err)
	}
	a.evidence.Upstream = upstream
	expected := "origin/" + report.Branch
	if upstream != expected {
		a.add("upstream", "fail", "upstream does not match origin/current branch")
		return a.decide("deny", "PR head upstream does not match the current branch", "publication-upstream"), nil
	}
	a.add("upstream", "pass", upstream)

	githubHead, digest, err := github.BranchHead(ctx, report.Repository, report.Branch)
	if err != nil {
		return a.unknown("github_branch_head", "GitHub branch head is unavailable", err)
	}
	a.evidence.GitHubBranchHeadSHA = githubHead
	a.evidence.GitHubBranchSHA256 = digest
	if githubHead != report.HeadSHA {
		a.add("github_branch_head", "fail", "GitHub branch head does not match local HEAD")
		return a.decide("deny", "local HEAD is not the published GitHub branch head", "publication-github-head"), nil
	}
	a.add("github_branch_head", "pass", githubHead)
	return a.decision, nil
}

// Evaluate applies Publication Guard to a policy decision after a fresh READY
// repository report has been produced for the same action. Known dangerous
// target changes are denied; compound, ambiguous, and other noncanonical forms
// are downgraded to ask. Missing Git/GitHub state returns deny plus an error so
// the trusted runtime can preserve Evidence and exit nonzero.
func Evaluate(ctx context.Context, action policy.Action, result policy.Decision, classification Classification, report repository.Report, git repository.Git, github GitHub, environment []string, now time.Time) (policy.Decision, error) {
	if !classification.Candidate {
		return result, nil
	}
	a, err := newAssessment(result, classification, report, now)
	if err != nil {
		return policy.Decision{}, err
	}
	if report.State != "READY" || report.Repository == "" || report.Branch == "" || report.HeadSHA == "" || report.DefaultBranch == "" {
		a.add("repository_authority", "fail", "fresh READY repository evidence is required")
		return a.decide("deny", "repository authority does not permit publication", "repository-authority"), nil
	}
	a.add("repository_authority", "pass", "fresh READY repository posture supplied")
	if report.Branch == report.DefaultBranch {
		a.add("default_branch", "fail", "current branch is the authoritative default branch")
		return a.decide("deny", "default-branch publication is prohibited from the autonomous path", "publication-default-branch"), nil
	}
	a.add("default_branch", "pass", "current branch differs from the authoritative default branch")
	if git == nil || github == nil {
		return a.unknown("publication_provider", "Git and GitHub publication providers are required", fmt.Errorf("publication provider unavailable"))
	}
	if result.Decision == "deny" {
		return result, nil
	}
	command, err := policy.Command(action)
	if err != nil {
		return a.unknown("command", "publication command is invalid", err)
	}
	if selectors := sensitiveEnvironment(environment); len(selectors) != 0 {
		a.add("environment", "fail", "publication-sensitive selectors are set: "+strings.Join(selectors, ","))
		return a.decide("deny", "publication target or Git execution can be changed by inherited environment", "publication-environment"), nil
	}
	a.add("environment", "pass", "publication-sensitive target selectors are absent")
	tokens := strings.Fields(command)
	if classification.Compound || classification.Ambiguous || !isSimpleCommand(command) || classification.Kind == KindAmbiguous {
		a.add("command_form", "fail", "compound or ambiguous shell syntax is outside the autonomous normal form")
		return a.decide("ask", "compound or ambiguous publication requires external authorization", "noncanonical-publication"), nil
	}
	if classification.Kind == KindGitPush && forceOrBulkPush(tokens) {
		a.add("command_form", "fail", "force, mirror, bulk, tag, or delete push option detected")
		return a.decide("deny", "force or bulk publication is prohibited from the autonomous path", "publication-dangerous-push"), nil
	}
	switch classification.Kind {
	case KindGitPush:
		return a.validatePush(ctx, action, report, git, tokens)
	case KindPullRequestCreate:
		return a.validatePullRequest(ctx, action, report, git, github, tokens)
	default:
		a.add("command_form", "fail", "publication meaning is not canonical")
		return a.decide("ask", "unrecognized publication requires external authorization", "noncanonical-publication"), nil
	}
}

func equalTokens(left, right []string) bool {
	if len(left) != len(right) {
		return false
	}
	for i := range left {
		if left[i] != right[i] {
			return false
		}
	}
	return true
}

func nonemptyLines(raw string) []string {
	lines := make([]string, 0)
	for _, line := range strings.Split(raw, "\n") {
		if value := strings.TrimSpace(line); value != "" {
			lines = append(lines, value)
		}
	}
	return lines
}
