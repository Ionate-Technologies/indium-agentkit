---
name: infrastructure-as-code
description: "Write or change infrastructure-as-code in Terraform or OpenTofu by default, or Pulumi or CDK, following the repository's existing layout: pinned providers and modules, remote locked state, secrets kept out of code and outputs, deletion protection, least-privilege IAM, and a plan-only workflow where every replace or destroy is read and apply waits for approval. Use when adding or changing cloud resources, modules, IAM, networking, or state, or importing existing resources. Not for reviews (use the infrastructure-review skill) or workload manifests (use the kubernetes-workloads skill)."
---

# Infrastructure as Code

Change cloud infrastructure through reviewed code so that nothing is created,
replaced, or destroyed by surprise. The stance is **plan, read, then ask**:
format, validate, and plan against environments the user allows, read every
planned action, and run `apply` only after the user approves that exact plan.

## When to use

- Adding or changing cloud resources, modules, IAM policies, networking, DNS, or
  managed services in Terraform, OpenTofu, Pulumi, or CDK.
- Bringing manually created resources under management, renaming or moving
  resources and modules, or splitting state.
- Pinning providers and modules, moving to remote state, or adding drift checks.

## When not to use

- Reviewing an infrastructure change: use the `infrastructure-review` skill, or
  delegate to the `infrastructure-reviewer` subagent.
- Kubernetes manifests, Helm charts, or Kustomize overlays for a workload: use
  the `kubernetes-workloads` skill. Code that builds the cluster itself belongs here.
- Dockerfiles and images: use the `containerize-service` skill.
- Rolling an application release through environments: use the
  `deployment-safety` skill. CI workflows that run plan and apply: use the
  `ci-pipeline` skill.
- How the application loads its configuration and secrets: use the
  `config-and-secrets` skill.
- A secret already sits in state, a plan file, or git history: use the
  `secret-leak-response` skill.

## Inputs to gather

Discover these from the repository first. Ask only about what remains ambiguous.

- Tool and version: `required_version`, `.terraform-version`, `.tool-versions`,
  CI images; `Pulumi.yaml` and stack files; `cdk.json`.
- Layout: root modules per environment (for example `envs/prod/`), workspaces
  (`terraform.workspace` in code), Terragrunt (`terragrunt.hcl`), shared
  modules, and how environments differ (tfvars files, stack configuration).
- Backend: the `backend` block or `-backend-config` files, its locking, and who
  can read the state.
- Provider and module sources, the lock file, and how CI runs plan and apply
  (which job, which credentials, who approves).
- Conventions: naming, required tags, policy-as-code (OPA or Conftest,
  Sentinel), and static checks in CI or pre-commit hooks.
- Which environments you may plan against and with which credentials. A plan
  reads live state, calls provider APIs, and takes the state lock.

## Workflow

1. **Follow the existing layout.** Put the change where similar resources live,
   reuse the repository's modules, and match its naming and variables. Do not
   introduce workspaces into a directory-per-environment repository (or the
   reverse) or a new tool as part of a feature change; propose that separately.
2. **Pin versions.**
   - `required_version` for the CLI and a constraint for every provider in
     `required_providers` (for example `version = "~> 5.40"`).
   - Commit `.terraform.lock.hcl`. It records provider versions and checksums,
     not module versions. If CI and developers use different platforms, record
     hashes for each with `terraform providers lock -platform=linux_amd64 -platform=darwin_arm64`.
   - Pin modules yourself: registry modules with an exact `version`, git
     sources with `?ref=` set to a tag or commit SHA, never a branch.
   - Upgrade providers and modules in their own change and plan every
     environment; upgrades can change defaults and force replacements.
   - Pulumi and CDK: pin packages in the language lockfile. For CDK, commit
     `cdk.context.json` so lookups stay deterministic.
3. **Keep state remote, locked, and private.** Shared infrastructure uses a
   remote backend with locking: S3 (recent Terraform versions support
   `use_lockfile = true`; older setups use a DynamoDB table; check your version's
   backend docs), GCS, azurerm, or HCP Terraform; for Pulumi, Pulumi Cloud or a
   self-managed bucket backend. Encrypt the storage, enable versioning so a bad
   state can be recovered, and limit access to the deploy role and a few
   people. Never use local state for shared
   infrastructure, and never commit `*.tfstate`, `*.tfstate.backup`,
   `.terraform/`, or saved plan files. Migrating a backend
   (`terraform init -migrate-state`) moves state and needs approval.
4. **Keep secrets out of code, variables files, and outputs.**
   - No secret values in `.tf` files, `*.tfvars`, variable defaults, CDK
     context, or Pulumi stack files (except values set with
     `pulumi config set --secret`, which are encrypted).
   - Prefer references: create the secret container in code and let the
     workload read the value at runtime from the secret manager by name, or let
     the service manage the credential (for example
     `manage_master_user_password = true` on `aws_db_instance`).
   - Mark secret-bearing variables and outputs `sensitive = true`. That only
     hides them in CLI output: values Terraform reads or generates
     (`random_password`, data sources, provider attributes) are still stored in
     state in plain text, which is why step 3 matters. Recent Terraform
     versions add ephemeral values and write-only arguments, and OpenTofu 1.7
     and later can encrypt state; check your version before relying on either.
   - Output a secret's identifier, not its value.
5. **Protect stateful resources** (databases, buckets with data, keys, volumes,
   DNS zones):
   - Turn on the provider's deletion protection where it exists (for example
     `deletion_protection = true` on `aws_db_instance`). The cloud API enforces
     it, so it survives tooling mistakes.
   - Add `lifecycle { prevent_destroy = true }`. It guards only while the
     resource block stays in configuration; deleting the block deletes the guard.
   - Pulumi: the `protect` resource option. CDK: `RemovalPolicy.RETAIN` and
     stack termination protection.
   - Confirm backups or snapshots exist before a change that can touch data.
6. **Grant least privilege and avoid exposure.**
   - IAM: name the actions and resources the workload needs. No `"*"` actions or
     resources unless a comment says why and the reviewer accepts it. Prefer
     policy documents built in code (`aws_iam_policy_document`) and workload
     identity or OIDC federation over static access keys.
   - Storage: block public access (for example `aws_s3_bucket_public_access_block`
     with all four settings `true`) and enable encryption.
   - Network: no `0.0.0.0/0` or `::/0` ingress except on an intentionally public
     load balancer port, and never for SSH, RDP, or database ports.
   - Anything public on purpose gets a comment next to the resource and a line
     in the report.
7. **Tag consistently.** Apply the required tags (owner, environment, service,
   cost center) through provider defaults where available (`default_tags` in the
   AWS provider, or the equivalent) and merge resource-specific tags.
8. **Rename, move, and import without replacement.**
   - Renaming a resource or module, switching `count` to `for_each`, or moving
     a resource into a module reads as destroy-and-create. Add a `moved` block
     so the plan shows a move. Pulumi uses `aliases`; in CDK, keep construct
     IDs stable, because a new logical ID means a new resource.
   - `moved` blocks cannot cross state files. Between root modules, use a
     `removed` block with `lifecycle { destroy = false }` (Terraform 1.7 and
     later) in the source and an `import` block in the target, or state
     commands with approval.
   - Adopt existing resources with `import` blocks (Terraform 1.5 and later,
     OpenTofu). `terraform plan -generate-config-out=generated.tf` can draft the
     configuration; edit it until the plan shows the import and no changes.
   - `terraform state mv`, `state rm`, and the `import` command change state
     without a reviewable plan; they need approval like an apply.
9. **Format, validate, and check** (commands under Verification): `fmt`,
   `init`, `validate`, `terraform test` when the module has test files, and the
   static checks the project uses or has installed (`tflint`, `trivy config`,
   `checkov`). Fix findings; never suppress one without a recorded reason.
10. **Plan to a file outside the repository and read every line.**
    - Compare the summary line (`Plan: 1 to add, 2 to change, 0 to destroy.`)
      with what the change should do. An unexpected count blocks progress.
    - Stop on every `must be replaced`, `will be destroyed`, and
      `# forces replacement`. Common causes: a renamed address (add `moved`), a
      changed immutable attribute (name, identifier, region, zone, engine,
      encryption), a provider upgrade, or a shifted `count` index. Remove the
      cause, or explain the replacement, its data impact, and the backup, and
      get explicit approval for it.
    - Read in-place changes to IAM, security groups, and routing as carefully as
      replacements. `create_before_destroy` changes ordering, not the fact of
      replacement.
    - Changes to resources you did not touch come from drift or an upgrade;
      investigate them (step 11) instead of ignoring them.
    - Pulumi: `pulumi preview --diff`. CDK: `cdk diff`. Read them the same way.
11. **Detect drift.** `terraform plan -refresh-only` shows changes made outside
    Terraform without proposing configuration changes, and
    `terraform plan -detailed-exitcode` exits 0 for no changes, 2 for changes,
    and 1 for errors, which suits a scheduled CI job. Decide with the owner
    whether to codify or revert drift; never fold it into an unrelated change.
12. **Apply only with approval of that exact plan.** Present the summary, each
    replace and destroy with its cause, IAM and network changes, and the
    environment. After approval, apply the saved plan file, which applies what
    was reviewed or fails if state moved on; any new plan needs a new review.
    Where CI owns applies, use that path. If an apply fails midway, stop, plan
    again, and report the partial state instead of retrying blindly.

## Worked example: a rename that would destroy a database (illustrative)

A refactor renamed `aws_db_instance.main` to `aws_db_instance.orders`. The plan:

```text
  # aws_db_instance.main will be destroyed
  # (because aws_db_instance.main is not in configuration)
  - resource "aws_db_instance" "main" {
  ...
  # aws_db_instance.orders will be created
  + resource "aws_db_instance" "orders" {
  ...
Plan: 1 to add, 0 to change, 1 to destroy.
```

`prevent_destroy` on the old block did not help: the block is gone. Deletion
protection on the instance would make the apply fail at the API, but the plan
is already wrong. Record the move instead:

```hcl
moved {
  from = aws_db_instance.main
  to   = aws_db_instance.orders
}
```

The new plan shows `# aws_db_instance.main has moved to aws_db_instance.orders`
and `Plan: 0 to add, 0 to change, 0 to destroy.` Keep the `moved` block until
every environment and every caller of the module has applied it.

To list destructive actions from a saved plan without printing values:

```bash
PLAN_DIR="$(mktemp -d)"   # plan files hold sensitive values; keep them out of the repo
terraform plan -out="$PLAN_DIR/tfplan"
terraform show -json "$PLAN_DIR/tfplan" \
  | jq -r '.resource_changes[] | select(any(.change.actions[]; . == "delete")) | "\(.change.actions | join(",")) \(.address)"'
```

A replacement appears as `delete,create` or `create,delete`; a plain destroy as
`delete`. The JSON form contains sensitive values in plain text, so never save
it into the repository or a public CI artifact.

## Guardrails

- Revert or delete only files you created or changed in this session, and say
  so. Never discard someone else's uncommitted work.
- Ask before destructive, irreversible, outward-facing, or production actions:
  `apply`, `destroy`, the `import` command, `state mv`, `state rm`,
  `state push`, `force-unlock`, `init -migrate-state`, `pulumi up`,
  `pulumi refresh`, and `cdk deploy`. Mark such lines `# requires approval`.
- Never apply a plan the user has not reviewed, and never use `-auto-approve`
  outside a pipeline that already has an approval gate. Use `-target` only for
  approved recovery, not as a routine way to skip unrelated changes.
- Never edit state by hand, and never `force-unlock` a lock without confirming
  the run that holds it has stopped.
- Never print state, `terraform output` of sensitive values, or JSON plans into
  chat, logs, or the repository. Report where secret material is, never what it is.
- Never remove `prevent_destroy` or deletion protection, widen IAM, or open a
  network rule to make a plan or apply succeed without explicit approval.
- Never weaken a test, check, or threshold to make work pass, including blanket
  scanner suppressions.

## Verification

Use the project's own commands from `AGENTS.md`, `CLAUDE.md`, the `Makefile`,
or CI. Run each check separately and report its real result; never chain
alternatives with `||`. Illustrative Terraform commands (OpenTofu uses `tofu`):

```bash
PLAN_DIR="$(mktemp -d)"
terraform fmt -check -recursive
terraform init -backend=false -lockfile=readonly   # enough for validate; drop -lockfile=readonly when changing providers
terraform validate
tflint --init
tflint
trivy config .
checkov -d . --framework terraform
terraform plan -out="$PLAN_DIR/tfplan"              # needs a full init with the backend and allowed credentials
terraform show "$PLAN_DIR/tfplan"
terraform apply "$PLAN_DIR/tfplan"                  # requires approval
```

Flags differ across versions; check `<tool> --help`. `terraform test` creates
real infrastructure unless its runs use `command = plan` or mocked providers, so
treat it like an apply unless you have confirmed that.

- Formatting, validation, and static checks pass, or each finding has a fix or
  a recorded reason.
- Each allowed environment has a saved plan whose counts match the intent, with
  every replace and destroy explained.
- `git status` shows no state, plan, `.terraform/`, or secret-bearing tfvars files.

## Report

- **Change:** what was added or changed, in which layout location and environments.
- **Plan per environment:** counts, each replace or destroy with cause and
  approval status, IAM and network changes, moves and imports.
- **Versions:** CLI, providers, modules pinned, and lock file changes.
- **State and secrets:** backend, sensitive outputs, and secret values that
  still land in state.
- **Checks:** each command and its result.
- **Apply status:** not applied, or which saved plan was applied after whose approval.
- **Not verified:** environments not planned, checks that could not run, and why.

## Optional delegation

The `infra-builder` subagent can implement a bounded slice and return its plan
as evidence. The `infrastructure-reviewer` subagent can review the diff and plan
independently; re-check its findings before acting. The `docs-researcher`
subagent can confirm which arguments force replacement in your provider version.
The workflow above stays complete for a single agent.
