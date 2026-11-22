# Shared v15 source contract

Tracking: [ERPNext #6](https://github.com/BusinessClouds/erpnext/issues/6), AB#33816.

Companion reviews: [Frappe #37](https://github.com/BusinessClouds/frappe-dafater/pull/37),
[Dafater5 #452](https://github.com/BusinessClouds/dafater5/pull/452) and
[Docker #17](https://github.com/BusinessClouds/dafater5-docker/pull/17).
The initial paired image used ERPNext's validated runtime pin
`6983865cb71fc4b6becdb0fbc1e6272036fc98b1`. The later branch-policy and documentation
commits kept its runtime bytes unchanged. The setup-wizard correction below
changes JavaScript and requires a new reviewed application release and image build.

Use `develop-v15` as the shared BusinessClouds ERPNext v15 development branch for
both SaaS engines. PR #7 and new shared-product work target this branch. It starts
at the reviewed v15.102.0-based source `e4eb8022d0d9b631ef5ad462cb572d19ea2233d1`,
preserving the complete existing history without changing the validated runtime.
Engine selection belongs to Dafater5's per-site contract.

The prior `press-dev` reference is retained for transition and rollback, not as a
parallel development line. No new product work should target it. Existing deployment
references and immutable pins stay in place until their ordinary reviewed rollout;
creating this branch does not switch any tenant or controller source.

The initial branch-policy change added validation and documentation without
changing ERPNext runtime code. The subsequent setup-wizard correction updates
the chart loader; dependencies, DocType metadata and tenant configuration remain
unchanged.

## Baseline recorded on 2026-11-17

| Source | Commit | Role |
| --- | --- | --- |
| Upstream v15.102.0 | `1d14ba16398db3a220873509565c60f2932bed81` | Reviewed upstream product release |
| New `develop-v15` baseline | `e4eb8022d0d9b631ef5ad462cb572d19ea2233d1` | Shared engine-neutral v15 development target |
| Historical `press-dev` and `press-prod` | `e4eb8022d0d9b631ef5ad462cb572d19ea2233d1` | Same baseline retained for transition/rollback; no runtime merge is needed |
| Existing candidate manifest's ERPNext pin | `50abb892ec7b93abf408d942e0dcb8eb66deac4c` | Two commits behind the shared baseline |
| Earlier v15.75.1 metadata correction | `ddc14ab7f6c6bfd2ac23feb0b03f0b31f322e9c5` | Historical migration input |

The fork's existing `develop` is v17 development. Its moving `version-15` branch was
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
node --test tests/js/*.js
python -m unittest discover -s tests -p 'test_shared_v15_*.py' -v
```

Use Node 18 or newer and Python 3.10 or newer. The focused workflow runs these on
PRs targeting `develop-v15` when their source, tests or workflow change. The
existing local branch guard also protects this shared branch from direct commits.
The focused workflow checks:

- callback behavior, asynchronous field handlers, error recovery, retries and
  stale requests;
- identical native permission-denial and retry behavior with an absent engine
  selector, explicit `legacy_v2`, and explicit `press`;
- unique and complete Stock Settings field ordering, a newer migration timestamp,
  and unchanged opt-in defaults for stock-policy controls;
- the documentation guard's fork repository lookup and unchanged failure rules.

Local verification on 2026-11-17 passed all 22 JavaScript cases on Node 18.20.8
and Node 22.22.0, plus all three metadata and six documentation-guard cases on
Python 3.10. The configured
pre-commit checks passed using the installed Node 22 through a temporary
`default_language_version.node: system` setting. The unchanged default Node
installer failed while parsing a Node 27 prerelease version; no applicable hook was bypassed
and no repository toolchain setting was changed. Workflow YAML parsing and
`git diff --check` also passed.

The branch-policy follow-up verifies that `develop-v15` starts at the exact
recorded baseline, PR #7 targets it, and the focused workflow and local branch
guard use that same name. All 22 JavaScript cases, nine Python cases and applicable
pre-commit hooks pass again. At that branch-policy follow-up, runtime files and
dependency declarations were byte-identical to the validated image pin, so its
native receipts remained applicable. That historical receipt does not validate
the later setup-wizard correction.

## Setup-site correction on 2026-11-22

Dafater5's Eirady organization slide hides the chart selector. Frappe therefore
creates its Select control without an HTML input, and the native chart-loader
callback previously failed while setting `selectedIndex`. The loader now updates
the control's options and value through its API, including when it is hidden.
It keeps the first returned chart selected and ignores responses for an older
request, country or rebuilt control. See [setup-wizard notes](../erpnext/setup/setup_wizard/README.md).

Validation passes with Node 22.22.0: 32 JavaScript cases (22 existing Payment Entry
and 10 chart-loader cases), plus nine existing Python metadata/documentation cases.
The configured pre-commit checks also pass using the installed Node 22 through
a temporary `default_language_version.node: system` setting. No hook was bypassed.
Publish a new app release and rebuild the candidate image with the paired Frappe
and Dafater5 corrections before testing the complete browser setup flow. Existing
image receipts and a code-only test do not establish that rebuilt-image acceptance.

The inherited documentation workflow queried `frappe/erpnext` using this fork's
PR number and failed with `Pull Request Not Found`. It now passes GitHub's
`GITHUB_REPOSITORY` to the helper. Feature documentation rules, recognized domains
and API-failure behavior are unchanged. A local helper call without the optional
repository argument intentionally retains its historical upstream default.

Inherited full ERPNext CI remains enabled. Its installer derives upstream Frappe
and Payments branches from the PR base, which cannot resolve a fork-only
`develop-v15` line. Retargeting does not repair that dependency-source contract;
historical failures named the former `press-dev` base. These source/reporting
limitations are tracked separately in
[ERPNext #5](https://github.com/BusinessClouds/erpnext/issues/5). A passing focused
workflow does not replace full ERP/database/consumer acceptance or authorize a
deployment, production-branch update or mainline merge.
