# Stock Settings metadata compatibility

The Press release candidate merges ERPNext v15.102.0, upstream commit
`1d14ba16398db3a220873509565c60f2932bed81`, into `press-dev` history. This tag already
removes the eleven repeated entries in this DocType's `field_order` that the
earlier v15.75.1 candidate corrected. The merged metadata retains every upstream
field and its order, including the new material-transfer validation and batch
negative-stock settings. This prevents `UniqueFieldnameError` when Dafater
synchronizes Stock Settings customizations during installation.

The previous Dafater Docker build applied the same de-duplication silently. The
candidate instead pins this reviewed source commit; it does not rewrite app
sources while building an image. The metadata modification timestamp is newer
than the earlier fork correction so migration also reloads the new upstream
fields on sites that already installed that correction.

The tag continues to declare Frappe `>=15.40.4,<16.0.0` and Python `>=3.10`,
with unchanged Python and JavaScript package dependencies. Frappe 15.102.1 also
supports the hourly/daily maintenance scheduler frequencies used by this tag.
The source revision is pinned alongside HRMS v15.58.5 and Lending v1.5.4 in the
companion [Docker upgrade](https://github.com/BusinessClouds/dafater5-docker/issues/12).

Tracking: [ERPNext #1](https://github.com/BusinessClouds/erpnext/issues/1),
[ERPNext #3](https://github.com/BusinessClouds/erpnext/issues/3),
[Press #456](https://github.com/BusinessClouds/dafater-saasmoney-v3/issues/456).
Actual fresh-install and upgrade results are recorded in the paired release
manifest and acceptance evidence; source inspection alone is not runtime proof.
