# Preserve the shared v15 contract and support hidden setup chart fields

Use `develop-v15` as the shared ERPNext branch for both SaaS engines. It retains
the reviewed v15.102.0-based history, Payment Entry recovery and Stock Settings
migration correction; the existing `develop` remains v17.

The first consolidated Press canary exposed a chart loader that assumes every
field has an HTML input. Eirady intentionally hides this field. The loader now
updates the Frappe control's options and value, preserving visible first-option
selection and ignoring stale country/field/request callbacks. This is shared
field behavior and introduces no SaaS-engine selection in ERPNext.

Validation: 32 JavaScript cases and nine focused Python cases pass; applicable
configured source hooks, workflow parsing and diff checks pass. The ten new
chart cases cover visible/hidden/missing controls, empty results, stale callbacks
and unchanged behavior across absent, legacy and Press selectors.

Pair with [Frappe #37](https://github.com/BusinessClouds/frappe-dafater/pull/37) and
[Dafater5 #452](https://github.com/BusinessClouds/dafater5/pull/452), then create a
new App Release and Release Group build. The earlier immutable image receipt in
[Docker #17](https://github.com/BusinessClouds/dafater5-docker/pull/17) retains its
old runtime pins and does not qualify this follow-up. Roll back the paired build
through the normal process while preserving site ownership and customer data.

The inherited full ERP/database CI dependency selection remains tracked in #5;
focused checks do not replace full native ERP acceptance. Actual unchanged v2
VM/controller provisioning and credential delivery remain release gates.
[Source contract and reproduction](https://github.com/BusinessClouds/erpnext/blob/task/6-shared-v15-source-contract/docs/shared-v15-source.md).

Closes #6. AB#33816.
