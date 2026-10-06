# Controlled development/CI release candidate

This is preparation only. No publication, credential configuration or tag push is automated.
Version remains 0.1.0: the distribution has not yet been published. Candidate means
controlled testing of production applications with disposable fixtures, not production safety.

1. Review the source commit and proposed `v<pyproject version>` tag. Update the version
   and lockfile together if a new version is explicitly selected. Never overwrite an existing release.
2. Run the validation guide and the Windows/Linux × Python 3.12/3.13 CI matrix on
   that exact commit. The manual release-candidate workflow validates proposed tag/version
   agreement and invokes the same matrix; if selected from a tag it also checks the actual tag name.
3. Retain wheel, sdist, SHA-256 build evidence, runtime requirements, audit JSON and
   recovery artifacts from all jobs. CI retention is seven days; archive approved evidence
   elsewhere before expiry. Confirm identical artifacts from repeated local builds.
4. Inspect metadata, public namespace, typing marker and packaged contents. Confirm fresh
   wheel and sdist installs outside the repository, with no Git or dev dependencies;
   install pytest separately for example tests. Review locked and newly resolved advisories.
   Confirm the distribution is `fracture-recovery` while both import and CLI are
   `fracture`; use an isolated environment without the unrelated `fracture` distribution.
5. Record unresolved risks: synthetic integration is not independent adoption, transitive
   versions resolve over time, replay needs matching source/environment and trusted targets.
6. Obtain explicit maintainer approval naming the source commit, version/tag, artifact
   hashes and publication destination before publishing, configuring credentials or pushing tags.
   Publication requires a separate authorized workflow; this repository has no publishing job.
7. Obtain separate authorization for a **TestPyPI rehearsal**, naming TestPyPI as the
   destination, the reviewed source commit, version and exact wheel/sdist SHA-256 hashes.
   Upload only those reviewed artifacts after approval; do not rebuild for upload.
   Rehearsal approval does not authorize PyPI publication or credential configuration.
8. From that TestPyPI publication, check installation, `import fracture`, installed
   distribution metadata/version and the actual `fracture --help` console command in
   a fresh supported environment outside the checkout. Run the shipped example campaign
   and replay with disposable data; retain logs and the downloaded artifact hash.
   Use an explicit dependency-source strategy: install the complete reviewed, pinned
   third-party runtime requirements from **PyPI only** (excluding this project), then
   download the exact `fracture-recovery` version from **TestPyPI only** with `--no-deps`
   and a single TestPyPI `--index-url`. Verify its hash against the approved artifact,
   install that local file with `--no-deps`, and run `python -m pip check` before smoke
   checks. Clear inherited index settings; never use an unrestricted `--extra-index-url`
   fallback combining TestPyPI and PyPI. Investigate any missing dependency instead.
9. Obtain **separate PyPI approval** naming PyPI as the destination, the source commit,
   version and exact artifact hashes. Require successful exact-commit matrix evidence
   and the approved TestPyPI rehearsal results. Publish only the approved bytes.
10. After publication, download from **PyPI only** into a fresh environment, verify the
    artifact hash and metadata, and repeat install/import/CLI smoke checks and the
    shipped example campaign/replay. Confirm the release tag still identifies the
    approved source commit and retain the publication URL, logs and hashes.
    On failure, **stop further rollout**, communicate the affected version and failure,
    and obtain explicit authorization before any yank. Prepare and validate a corrected
    **new version**, with fresh approvals. Never replace published files, reuse a
    published version or move an existing release tag.

Do not silently waive failing checks or unavailable audit services. They block release approval
until the failure is resolved or a maintainer explicitly documents an accepted risk.

These publication and communication steps are a checklist, not actions authorized by
preparing this candidate. No publishing credentials or jobs are added. The revised
remote matrix is still pending; saved baseline CI results do not validate these changes.
Local byte comparisons establish identical artifacts only for the recorded successive
builds in that environment, not reproducibility across platforms, time or resolver changes.

After explicit push authorization and successful remote CI, the next milestone remains
one licensed, separately authored LangGraph application with existing durable business
writes and inspectable commit evidence. Record its revision/license, isolate adapter
changes, measure integration effort, execute meaningful corrected and negative controls,
and document blockers. Do not alter an external application to manufacture suitable
behavior. Defer UI work until genuine integration demonstrates a need.
