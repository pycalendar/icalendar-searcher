#!/usr/bin/env bash
# Script to create a new release and trigger automatic PyPI publishing
#
# Usage: ./scripts/release.sh [version] [release message]
# Example: ./scripts/release.sh 1.0.4 "Fix undef filter bugs"
#
# Flow:
#   1. Validate inputs and local state (branch, uncommitted changes, CHANGELOG)
#   2. Run tests and linter locally
#   3. Push branch to origin
#   4. Wait for the CI workflow to pass on GitHub
#   5. Create a signed git tag
#   6. Push the tag (triggers the publish-to-PyPI workflow)

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

if [ -z "$1" ]; then
    echo -e "${RED}Error: Version argument required${NC}"
    echo "Usage: $0 <version> [release message]"
    echo "Example: $0 1.0.4"
    exit 1
fi

VERSION="$1"
TAG="v${VERSION}"
RELEASE_MESSAGE="$2"

echo -e "${GREEN}=== Creating release ${TAG} ===${NC}"

# Check if we're on main/master branch
CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
if [[ "$CURRENT_BRANCH" != "main" && "$CURRENT_BRANCH" != "master" ]]; then
    echo -e "${YELLOW}Warning: You're on branch '${CURRENT_BRANCH}', not 'main' or 'master'${NC}"
    read -p "Continue anyway? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Check for uncommitted changes
if ! git diff-index --quiet HEAD --; then
    echo -e "${RED}Error: You have uncommitted changes${NC}"
    git status --short
    exit 1
fi

# Verify CHANGELOG has an entry for this version dated today
TODAY=$(date +%F)
EXPECTED_HEADER="## [${VERSION}] - ${TODAY}"
if ! grep -qF "$EXPECTED_HEADER" CHANGELOG.md; then
    echo -e "${RED}Error: CHANGELOG.md is missing the expected header:${NC}"
    echo "  ${EXPECTED_HEADER}"
    echo -e "${RED}Please update CHANGELOG.md before releasing.${NC}"
    exit 1
fi
echo -e "${GREEN}✓ CHANGELOG.md contains '${EXPECTED_HEADER}'${NC}"

# Check if tag already exists
if git rev-parse "$TAG" >/dev/null 2>&1; then
    echo -e "${RED}Error: Tag $TAG already exists${NC}"
    exit 1
fi

# Pull latest changes
echo -e "${GREEN}Pulling latest changes...${NC}"
git pull --rebase

# Run tests
echo -e "${GREEN}Running tests...${NC}"
python -m pytest || {
    echo -e "${RED}Tests failed! Aborting release.${NC}"
    exit 1
}

# Run ruff checks
echo -e "${GREEN}Running ruff checks...${NC}"
python -m ruff check . || {
    echo -e "${RED}Ruff checks failed! Aborting release.${NC}"
    exit 1
}

# Push branch to origin to trigger CI
echo -e "${GREEN}Pushing branch to origin...${NC}"
git push origin "$CURRENT_BRANCH"

# Find and watch the CI run for this commit
COMMIT_SHA=$(git rev-parse HEAD)
echo -e "${GREEN}Waiting for CI run on commit ${COMMIT_SHA:0:8}...${NC}"

RUN_ID=""
for i in {1..24}; do
    RUN_ID=$(gh run list \
        --commit "$COMMIT_SHA" \
        --workflow CI \
        --json databaseId \
        --jq '.[0].databaseId' 2>/dev/null || true)
    if [ -n "$RUN_ID" ] && [ "$RUN_ID" != "null" ]; then
        break
    fi
    echo "  Waiting for CI run to appear... (${i}/24)"
    sleep 5
done

if [ -z "$RUN_ID" ] || [ "$RUN_ID" = "null" ]; then
    echo -e "${RED}Error: Could not find a CI run for commit ${COMMIT_SHA}${NC}"
    echo -e "${RED}Check GitHub Actions manually before tagging.${NC}"
    exit 1
fi

echo -e "${GREEN}Found CI run ${RUN_ID}, watching...${NC}"
gh run watch "$RUN_ID" --exit-status || {
    echo -e "${RED}CI failed! Aborting release. Fix the issues and try again.${NC}"
    exit 1
}
echo -e "${GREEN}✓ CI passed${NC}"

# Create and push tag
echo -e "${GREEN}Creating tag ${TAG}...${NC}"
git tag -sa "$TAG" -m "Release $TAG" -m "$RELEASE_MESSAGE"

echo -e "${YELLOW}About to push tag ${TAG} to origin.${NC}"
echo -e "${YELLOW}This will trigger automatic publishing to PyPI!${NC}"
read -p "Continue? (y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo -e "${YELLOW}Aborting. Removing local tag.${NC}"
    git tag -d "$TAG"
    exit 1
fi

echo -e "${GREEN}Pushing tag to origin...${NC}"
git push origin "$TAG"

echo -e "${GREEN}✓ Release ${TAG} created and pushed!${NC}"
echo -e "${GREEN}✓ GitHub Actions will now run tests and publish to PyPI${NC}"
echo -e "${GREEN}✓ Check progress at: https://github.com/pycalendar/icalendar-searcher/actions${NC}"
