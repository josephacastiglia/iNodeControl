# Reproduce the review package

From the repository root, choose a different output name if this one exists. These commands only read the recorded builds and write a review package:

```powershell
python tools/stage_release.py stage --repo . --out output/staging/offline-review-20261012 --console-build analysis/wall-freshness-20261012/console-build --console-manifest analysis/wall-freshness-20261012/console-manifest.json --kernel-build analysis/frame-freshness-20261012/kernel-build --kernel-manifest analysis/frame-freshness-20261012/kernel-manifest.json --receiver-exe analysis/receiver-memory-20261012/patched-build/build/uxplay.exe --receiver-record analysis/receiver-memory-20261012/patched-build/comparison.json --receiver-source tools/airplay/uxplay --guide docs/RELEASE-STAGING.md
python tools/stage_release.py verify --bundle output/staging/offline-review-20261012
```

Changed source or build bytes require a new build and record. Do not rewrite historical manifests to claim a different build matches. No build or hardware command is invoked by these tools.
