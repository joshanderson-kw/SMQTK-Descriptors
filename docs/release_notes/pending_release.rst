Pending Release Notes
=====================

Updates / New Features
----------------------

CI

* Added workflow to inherit the smqtk-core publish workflow.

* Updated CI unittests workflow to include codecov reporting.
  Reduced CodeCov report submission by skipping this step on scheduled runs.

Miscellaneous

* Added a wrapper script to pull the versioning/changelog update helper from
  smqtk-core to use here without duplication.

Misc.

* Added PyTorch descriptor generator implementation.

Testing

* Updated pytest configuration to cover package + tests and added report output
  options.

* Removed or no-cover mark dead lines of code.

Documentation

* Updated CONTRIBUTING.md to reference smqtk-core's CONTRIBUTING.md file.

Fixes
-----

CI

* Modified CI unittests workflow to run for PRs targetting branches that match
  the `release*` glob.

Dependency Versions

* Updated the locked version of urllib3 to address a security vulnerability.

* Updated the locked version of pillow to address a security vulnerability.

* Updated the developer dependency and locked version of ipython to address a
  security vulnerability.

* Removed `jedi = "^0.17.2"` requirement since recent `ipython = "^7.17.3"`
  update appropriately addresses the dependency.
