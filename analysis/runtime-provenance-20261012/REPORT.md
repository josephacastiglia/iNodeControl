# Native dependency notices and provenance

12 October 2026 work, completed across midnight UTC. Offline package preparation;
public source archives were downloaded over verified HTTPS. No rack or desktop
control, receiver launch, installation, deployment or push.

## Result

- The runtime stager now preserves package-listed `COPYING`, `COPYRIGHT`,
  `LICENSE`, `LICENCE` and `NOTICE` files under `share/doc`, as well as the
  existing `share/licenses` path. This recovers zimg's actual installed notice.
  Translation dictionaries and unrelated/unlisted documents are not substitutes.
- All **91 exact cached binary packages** have valid detached signatures against
  the selected local MSYS2 public keyring. **229 archived members** match the
  staged bytes: 126 runtime files and 103 package-local notices.
- For the remaining **23 packages** lacking local notices, **22 exact source
  archives** were obtained and their signatures verified. Every `PKGBUILD`
  checksum matches the corresponding signed binary's `.BUILDINFO` record.
- **55 source notice files** were preserved and mapped to those 23 packages.
  Archive sources were checked against the recorded upstream checksums. For
  x264 and rtmpdump, pinned source commits were read from signed Git objects in
  newly created inert object databases, without importing configuration/hooks.
- A new capsule adds these records and notices, with the **same 126 runtime
  binaries**. Local notice gaps remain separately recorded; none is silently
  reclassified as legal clearance.

## Verification and limits

The signature result establishes a match to the selected locally installed
public keyring, not a fresh revocation or trust-chain review. No private key was
used. The ASCII-armored public keyring was converted to binary in an isolated
scratch GPG home; original and converted hashes are recorded.

The binary audit checks exact package name, version, architecture, declared
licenses, build-recipe hash and actual member bytes. It preserves original
archives/signatures and refuses changed inputs or an existing output folder.
It never installs a package or executes its contents.

Source checks link the recorded recipe and recognized notice files to the
selected version. They do not reproduce every dependency build, verify the
makepkg VCS checksum algorithm, audit every copyright header, establish which
of several alternative licenses applies to a configured binary, or establish
complete corresponding-source coverage for all 91 packages. Source archives
were collected for the 23 notice gaps only. Runtime redistribution remains
uncleared. No release gate was advanced.

The normal extraction path has a post-capture member-size check; it is not a
streaming memory limit. This run reads known signed local/public archives and
does not run scripts within them.

## Tool checks

- Runtime staging: **22 passed**, including missing document notices,
  unlisted files, receipt/count-summary tampering and standalone verification
  without writing inside the package.
- Package provenance: **14 passed**, covering signature refusal, expiry/revocation
  status, exact versions, payload/notice mismatch, changed evidence and unsafe
  archive paths.
- Existing release staging: **22 passed**.

Results are saved alongside this report. These checks do not open a console
window or require a service. Product source and binaries were not changed in
this pass; the earlier 348 console / 179 kernel checks are historical evidence,
not rerun counts for this tooling change.

The first full package's standalone runtime verifier exposed a Python cache
write into the capsule, which then correctly failed strict integrity checking.
The verifier now disables bytecode before importing local helpers. A child-
process regression reproduced the fault under normal permissions and passes
twice without changing a single package byte after the repair. The first
sandboxed negative check passed because its filesystem restrictions masked the
cache write; that result is retained but not used as the regression proof.
Final runtime/release tests ran on temporary fixtures with normal permissions.

## Records and packages

- `output/provenance/native-packages-20261012`: all 91 binary archives,
  signatures, metadata, signature output and checksums.
- `output/provenance/native-sources-20261012`: 22 source archives/signatures,
  exact build recipes and download provenance.
- `output/provenance/source-notices-final-20261012`: notices and their source
  mappings. The earlier extraction is retained: x264's empty `depends = ` line
  was initially rejected after trimming its trailing space. The parser input
  was corrected and all 22 sources were read into a new output folder.
- `output/staging/native-runtime-provenance-final-20261012`: 520 inventoried files
  plus `runtime.json`, including source notices and compact provenance records.
- `output/staging/combined-runtime-provenance-final-20261012`: consolidated review
  package; see `package-result.json` for verification. Latest cleanup console,
  unchanged persistence kernel and preserved patched receiver. Never launched.
- `archive-verification.json`: external preservation receipt once completed.

Runtime capsule creation initially refused a mismatched receiver path before
creating output. Python HTTPS fetching failed on local DNS/certificate handling;
Windows curl then downloaded through the official MSYS2 mirror with normal
certificate checking and HTTPS-only redirects. No TLS check was bypassed.

## Upstream references

The package layout and metadata limitations were checked against the official
[MSYS2 package-licensing guidance](https://www.msys2.org/dev/package-licensing/),
[license record guidance](https://www.msys2.org/license/) and
[keyring documentation](https://www.msys2.org/dev/keyring/).

## Remaining acceptance

The package stays local-test/review-only. Clean-PC dependency loading, complete
release obligations, physical controls/video/recovery, rack scale and endurance
remain open. The typing investigation stays deferred. The installed app,
operator settings and previous review packages are preserved unchanged.
