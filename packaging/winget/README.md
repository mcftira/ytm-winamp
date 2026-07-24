# winget manifests (DRAFT — not yet submitted)

[microsoft/winget-pkgs](https://github.com/microsoft/winget-pkgs)-style manifests for
`winget install mcftira.ytm-winamp`. The `manifests/` tree mirrors the winget-pkgs
layout, so the `m/mcftira` directory can be copied into a fork of winget-pkgs as-is.

Status: **draft**. `InstallerSha256` matches the published v0.8.0
`ytm-winamp-setup.exe` release asset. Nothing has been submitted or published.

To submit for a new release (requires a fork of microsoft/winget-pkgs):

1. Update `InstallerSha256` (hash of the new release asset), `InstallerUrl`,
   `ReleaseDate`, and rename the `0.8.0` folder / bump every `PackageVersion`.
2. Validate locally: `winget validate --manifest packaging\winget\manifests\m\mcftira\ytm-winamp\<version>`
3. Smoke-test install: `winget install --manifest packaging\winget\manifests\m\mcftira\ytm-winamp\<version>`
4. Open the PR against microsoft/winget-pkgs from the fork
   (`wingetcreate submit packaging\winget\manifests\m\mcftira\ytm-winamp\<version>` does steps 2-4).
