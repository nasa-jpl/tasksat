# JPL Internal Development Workflow

## Getting the Code

### For JPL Users

```bash
# Clone from JPL GitHub
git clone https://github.jpl.nasa.gov/pass/tasksat.git
cd tasksat

# Check out JPL version
git checkout jpl-internal

# Verify jpl/ folder exists
ls jpl/
```

### For Public Users

```bash
# Clone from public GitHub
git clone https://github.com/nasa-jpl/tasksat.git
# jpl/ folder does not exist
```

## Daily Workflow

### Working on Open Source Code

```bash
# Switch to main branch
git checkout main

# Make changes to src/, tests/, doc/, etc.
git add <files>
git commit -m "Update core TaskSAT"

# Push to both public and internal
git push origin main
git push internal main
```

### Working on JPL Code

```bash
# Switch to jpl-internal branch
git checkout jpl-internal

# Make changes to jpl/
git add jpl/
git commit -m "Update MEXEC translator"

# Push to internal only (hook prevents pushing to origin)
git push internal jpl-internal
```

### Syncing Changes from Main

```bash
# Regularly merge main into jpl-internal to get open source updates
git checkout jpl-internal
git merge main

# Resolve any conflicts
git push internal jpl-internal
```

## Branch Structure

- **main**: Open source code (no jpl/ folder) - pushed to both public and internal repos
- **jpl-internal**: Open source code + jpl/ folder - **only on internal repo**

## Safety Features

- **Pre-push hook**: Prevents accidentally pushing jpl-internal branch to public origin
- **Branch configuration**: jpl-internal is configured to only push to internal remote
- **Auto-merge**: GitHub Actions automatically merges main → jpl-internal to keep JPL code in sync

## Notes

- Never push jpl-internal to the public repository (github.com/nasa-jpl/tasksat)
- The jpl/ folder contains JPL-internal MEXEC integration work
- Public users only see the main branch and have no knowledge of jpl/
