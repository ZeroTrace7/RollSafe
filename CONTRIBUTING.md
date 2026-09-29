# Contributing to RollSafe

Thank you for contributing to RollSafe. This guide walks through the exact workflow for forking the repository, setting up your local environment, keeping your fork synchronized, and submitting changes.

---

## 1. Forking & Cloning the Repository

### Step 1: Fork on GitHub
1. Open the upstream repository: [https://github.com/shourya2101/RollSafe](https://github.com/shourya2101/RollSafe)
2. Click the **Fork** button in the top-right corner.
3. Choose your personal account (e.g. `ZeroTrace7`) and create the fork.

### Step 2: Clone Your Fork Locally
Clone your fork to your local workstation:

```bash
git clone https://github.com/ZeroTrace7/RollSafe.git
cd RollSafe
```

### Step 3: Configure Upstream Remote
To keep your fork in sync with new commits pushed to the main repository, add the upstream remote:

```bash
git remote add upstream https://github.com/shourya2101/RollSafe.git
git fetch upstream
```

Verify your remotes are configured correctly:

```bash
git remote -v
```

You should see:
- `origin` pointing to your fork (`github.com/ZeroTrace7/RollSafe.git`)
- `upstream` pointing to the main project (`github.com/shourya2101/RollSafe.git`)

---

## 2. Syncing Your Fork With Upstream

Before starting any new branch or feature, always pull the latest changes from upstream:

```bash
git checkout main
git pull upstream main
git push origin main
```

---

## 3. Development Workflow

### Step 1: Create a Feature Branch
Always work in a dedicated branch rather than directly on `main`:

```bash
git checkout -b feat/your-feature-name
```

### Step 2: Local Verification & Testing
Before committing, verify that your changes run without issues:

- **Zero-Dependency Python Demo** (runs anywhere without Docker):
  ```bash
  python deploy/run_local_demo.py
  ```
- **Go Microservice Core**:
  ```bash
  cd core
  go run main.go
  ```
- **Containerized Stack** (if Docker is installed):
  ```bash
  docker-compose -f deploy/docker-compose.yml up --build
  ```

### Step 3: Granular Commits
Commit small, verified changes. Follow standard conventional commit prefixes (`feat:`, `fix:`, `docs:`, `test:`, `refactor:`).

When collaborating on shared features, include co-author trailers:

```bash
git commit -m "feat(telemetry): add response time percentile tracking" -m "Co-authored-by: ZeroTrace7 <ZeroTrace7@users.noreply.github.com>"
```

### Step 4: Push to Your Fork
Push your branch to your GitHub fork:

```bash
git push origin feat/your-feature-name
```

---

## 4. Submitting a Pull Request

1. Go to your fork on GitHub: `https://github.com/ZeroTrace7/RollSafe`
2. You will see a banner prompting you to open a **Pull Request**. Click **Compare & pull request**.
3. Target `base repository: shourya2101/RollSafe` and `base: main`.
4. Provide a clear summary of what was changed and how you tested it.
5. Submit the PR. Code owners (`@shourya2101` and `@ZeroTrace7`) are automatically notified for review.
