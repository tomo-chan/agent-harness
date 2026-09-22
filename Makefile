.PHONY: build check release-check release-snapshot

build:
	go build ./...

check:
	go test ./...
	go test -race ./...
	go vet ./...
	go build ./...

release-check:
	GITHUB_REPOSITORY_OWNER=$${GITHUB_REPOSITORY_OWNER:-local} \
	GITHUB_REPOSITORY_NAME=$${GITHUB_REPOSITORY_NAME:-agent-harness} \
	goreleaser check

release-snapshot:
	GITHUB_REPOSITORY_OWNER=$${GITHUB_REPOSITORY_OWNER:-local} \
	GITHUB_REPOSITORY_NAME=$${GITHUB_REPOSITORY_NAME:-agent-harness} \
	goreleaser release --snapshot --clean
