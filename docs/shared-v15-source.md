# Shared v15 source contract

Tracking: [ERPNext #6](https://github.com/BusinessClouds/erpnext/issues/6), AB#33816.

Use the existing `press-dev` line as the reviewed BusinessClouds ERPNext v15.102
development source for both SaaS engines. The branch retains its historical name;
engine selection belongs to Dafater5's per-site contract, not ERPNext. A later
branch rename can follow consumer inventory and release acceptance.

This change adds validation and documentation. It does not change ERPNext runtime
code, dependencies, DocType metadata, tenant configuration or deployment pins.

## Baseline recorded on 2026-11-17

| Source | Commit | Role |
| --- | --- | --- |
| Upstream v15.102.0 | `1d14ba16398db3a220873509565c60f2932bed81` | Reviewed upstream product release |
| `press-dev` and `press-prod` before this PR | `e4eb8022d0d9b631ef5ad462cb572d19ea2233d1` | Same source; no branch merge is needed |
| Existing candidate manifest's ERPNext pin | `50abb892ec7b93abf408d942e0dcb8eb66deac4c` | Two commits behind the shared baseline |
| Earlier v15.75.1 metadata correction | `ddc14ab7f6c6bfd2ac23feb0b03f0b31f322e9c5` | Historical migration input |

The fork's `develop` is v17 development. Its moving `version-15` branch was
v15.121.3 at review time. Neither is the target or an approved dependency upgrade
for this task. All current refs were checked without changing either mainline.

Five commits beyond upstream v15.102.0, including merge commits, produce five net
files. They contain two generic corrections, independent of SaaS ownership:

- Payment Entry retains the native Bank Account lookup and permissions while
  releasing its recursion guard after errors and ignoring stale asynchronous
  results. Its README and regression suite document that behavior.
- Stock Settings retains upstream's complete field definitions, field order and
  defaults. Only its modification timestamp differs from v15.102.0, making the
  metadata newer than the earlier v15.75.1 fork correction; its README explains
  the migration. Upstream v15.102.0 already removes the repeated field-order keys.

## Consumer pins and compatibility

1. Pin the exact reviewed PR head or resulting merge commit in each consumer's
   source manifest. Record that commit and the resulting immutable image digest.
   Do not substitute upstream `v15.102.0`, which lacks the Payment Entry recovery,
   or a moving `version-15`/`develop` branch.
2. Review the companion Dafater5 and Frappe commits and the other app pins as one
   image. `BusinessClouds/dafater5-docker/sources.press.json` currently pins the
   older candidate above. That manifest is not updated by this PR.
3. Inventory the actual legacy VM/template pins before selecting the same image.
   The generic Docker build's upstream v15.75.1 default is not proof of deployed
   legacy versions. The v15.75.1-to-shared-line difference is 1,974 commits and 546
   files; adopting that version is a separate ERP upgrade, not an engine toggle.
4. Demonstrate the unchanged legacy provisioning and ordinary-release path,
   including its existing credential handoff, stored settings and customer
   workflows. Existing customers require no new selector, repair or migration
   procedure beyond the approved normal release. Verify Press provisioning and
   upgrades on the same final source pins separately.

The shared code keeps native payment permissions authoritative. It does not add
controller calls, subscription rules, a default Press mode or a fallback around
an access denial. Consumer acceptance must verify real native permissions and
database migration; offline tests alone do not establish those results.

## Focused validation

No tenant, database, credentials or package installation is required:

```sh
node --test tests/js/payment_entry_bank_account.test.js
python -m unittest discover -s tests -p test_shared_v15_metadata.py -v
```

Use Node 18 or newer and Python 3.10 or newer. The focused workflow runs these on
PRs targeting `press-dev` when their source, tests or workflow change. It checks:

- callback behavior, asynchronous field handlers, error recovery, retries and
  stale requests;
- identical native permission-denial and retry behavior with an absent engine
  selector, explicit `legacy_v2`, and explicit `press`;
- unique and complete Stock Settings field ordering, a newer migration timestamp,
  and unchanged opt-in defaults for stock-policy controls.

Local verification on 2026-11-17 passed all 22 JavaScript cases on Node 18.20.8
and Node 22.22.0, plus all three metadata cases on Python 3.10. The configured
pre-commit checks passed using the installed Node 22 through a temporary
`default_language_version.node: system` setting. The unchanged default Node
installer failed while parsing a Node 27 prerelease version; no applicable hook was bypassed
and no repository toolchain setting was changed. Workflow YAML parsing and
`git diff --check` also passed.

Inherited full ERPNext CI remains enabled. Its framework-source and reporting
limitations are tracked separately in
[ERPNext #5](https://github.com/BusinessClouds/erpnext/issues/5). A passing focused
workflow does not replace full ERP/database/consumer acceptance or authorize a
deployment, production-branch update or mainline merge.
