#!/bin/bash
# Sync jpl-internal to public main, excluding jpl/ directory

set -e

echo "=== Syncing jpl-internal to public main ==="

# Save current branch
CURRENT_BRANCH=$(git branch --show-current)

# Ensure we're up to date
git checkout jpl-internal
git pull internal jpl-internal || true

# Switch to main and merge
git checkout main
git pull origin main || true

# Merge jpl-internal (this brings in jpl/)
git merge jpl-internal --no-edit

# Remove jpl/ if it was added
if [ -d "jpl" ]; then
    echo "Removing jpl/ directory..."
    git rm -r jpl/
    git commit --amend --no-edit
fi

# Push to public GitHub only
echo "Pushing to public GitHub..."
git push origin main

# Return to original branch
git checkout "$CURRENT_BRANCH"

echo "=== Sync complete! ==="
echo "Public: origin/main (no jpl/)"
echo "Internal: internal/jpl-internal (with jpl/)"
