# Stock Settings metadata compatibility

The Press release candidate retains ERPNext v15.75.1 and removes eleven repeated
entries from this DocType's `field_order`. Each field's first occurrence and all
field definitions remain unchanged. This prevents `UniqueFieldnameError` when
Dafater synchronizes Stock Settings customizations during installation.

The previous Dafater Docker build applied the same de-duplication silently. The
candidate instead pins this reviewed source commit; it does not rewrite app
sources while building an image. The metadata modification timestamp ensures
migration reloads the corrected order on existing sites.

Tracking: [ERPNext #1](https://github.com/BusinessClouds/erpnext/issues/1),
[Press #456](https://github.com/BusinessClouds/dafater-saasmoney-v3/issues/456).
Actual fresh-install and upgrade results are recorded in the paired release
manifest and acceptance evidence; source inspection alone is not runtime proof.
