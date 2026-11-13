# Original Live2D candidate packaging

`scripts/package_live2d_character.py` is a publisher-side, offline tool. It packages explicitly selected bytes into a runtime ZIP and an editable-source ZIP. It does not build a rig, download SDKs, run Core, or decide artistic acceptance. Python and the application's existing dependencies, including Pillow, must already be available.

The tool always writes `candidate`, `core_passed_by_packager: false` and `full_character_claimed: false`. Passing the actual application's `AssetStore.import_live2d` proves import format and normalization only. Even a synthetic MOC envelope can pass this check. True Core execution, animation quality, Editor reopening, Windows execution and the user's final acceptance require separate evidence.

## Invocation

```sh
python scripts/package_live2d_character.py \
  --root /absolute/path/to/project \
  --spec /absolute/path/to/project/review/original-live2d-package-spec.json \
  --output-dir /absolute/path/to/output
```

The spec must be beneath `--root`. Every input is relative to that root, except the runtime references (relative to `model3.json`) and the layer manifest's PNG references (relative to that manifest). Use forward slashes. The chosen output names must not exist; the tool never replaces them.

The following is a schema example, **not a ready-to-run spec**. Replace every SHA placeholder with the final selected file's actual SHA-256. Do not take pins while the authoring/export processes are still writing.

```json
{
  "format": "original-live2d-package-spec-v1",
  "identity": "original-character-r4",
  "origin": "project-original-authoring",
  "runtime_model": {"path": "export/character.model3.json", "sha256": "<64 lowercase hex>"},
  "runtime_files": {
    "character.moc3": "<64 lowercase hex>",
    "character.4096/texture_00.png": "<64 lowercase hex>",
    "character.physics3.json": "<64 lowercase hex>",
    "character.cdi3.json": "<64 lowercase hex>",
    "expressions/smile.exp3.json": "<64 lowercase hex>",
    "motions/idle.motion3.json": "<64 lowercase hex>"
  },
  "source_manifest": {"path": "art/layers.json", "sha256": "<64 lowercase hex>"},
  "psd": {"path": "authoring/character.psd", "sha256": "<64 lowercase hex>"},
  "cmo3": {"path": "authoring/character.cmo3", "sha256": "<64 lowercase hex>"},
  "can3": {"path": "authoring/character.can3", "sha256": "<64 lowercase hex>"},
  "project": {"path": "authoring/character.psd2live", "sha256": "<64 lowercase hex>"},
  "rig_recipe": {"path": "authoring/recipe.json", "sha256": "<64 lowercase hex>"},
  "notice": {"path": "authoring/NOTICE.txt", "sha256": "<64 lowercase hex>"},
  "original_sources": [
    {"path": "art/head/original.png", "sha256": "<64 lowercase hex>", "relative": "sources/head/original.png"}
  ],
  "source_manifests": [
    {"path": "art/head/part-manifest.json", "sha256": "<64 lowercase hex>", "relative": "sources/head/part-manifest.json"}
  ],
  "acceptance_index": {"path": "review/final-character-index.json", "sha256": "<64 lowercase hex>"}
}
```

`identity` is an internal packaging identifier, not a product name. `origin` records the author's attestation; the packager cannot independently prove authorship or licensing. Known local official-sample MOC hashes and known vendor directories are rejected; that is not a complete detector for renamed third-party models. The publisher must review provenance.

`runtime_files` must exactly cover the model's reference closure, excluding the model3 document itself and the separate notice. Supported references are MOC, PNG textures, physics, display-info, pose, expressions and motions. Unsupported references, including model audio and user-data, fail rather than being silently deleted. Nothing else from the export directory is collected.

`original_sources`, `source_manifests`, `can3` and `acceptance_index` are optional. List the independent head/body/hand source PNGs and their manifests explicitly when preparing the real source delivery. Additional source manifests must use `original-live2d-layers-v1`; they are retained byte-for-byte, without recursively collecting their neighbors. The primary layer manifest must use that format and pin every selected RGBA layer with `file` and `sha256`. Recipe format is `original-live2d-recipe-v1`.

The PSD canvas must match the primary layer manifest. The PSD2Live archive must have its own exact member manifest and embed the **same PSD SHA** as the selected external PSD. Its members are restricted to the observed PSD2Live source/document/history/rig/asset structure, with PNG/JSON assets and `PRIO` rig objects. PSD/CMO header checks do not substitute for opening them in the official Editor. Optional `can3` requires an explicitly pinned `.can3` path and a `CAFF` header, is preserved only as `source/character.can3`, and does not claim official Animator reopening. No neighboring `.can3` files are automatically collected.

An optional acceptance index has this minimal contract:

```json
{
  "moc_sha256": "<actual selected MOC SHA-256>",
  "evidence": [
    {"path": "review/actual-core-check.json", "sha256": "<actual evidence SHA-256>"}
  ]
}
```

Each referenced evidence file must exist under the explicit root with its pinned bytes. The index itself is included in the source ZIP. **Evidence media/reports are indexed by SHA and size, not copied into that ZIP**; ship approved evidence separately if needed. Any author-supplied acceptance decision remains an external claim. This tool records `decision_by_packager: not_performed` and cannot promote a candidate.

## Outputs and safeguards

- `<identity>-candidate-runtime.zip`: only the model3 document, its exact runtime references and the selected project's `NOTICE.txt`. Import this ZIP through the existing character importer; it contains no Core or Framework.
- `<identity>-candidate-source.zip`: the same runtime under `runtime/`; pinned PNGs/manifests under `source/art/`; the PSD, CMO3, PSD2Live project and recipe under `source/`; optional acceptance index under `validation/`; the input spec and member index at the root.
- `<identity>-candidate-report.json`: runtime/source ZIP SHA and size, every member SHA and size, actual AssetStore format result and explicit acceptance limitations. The embedded index excludes its own bytes; the external report also hashes the embedded index.

The source ZIP uses an explicit allowlist. It does not recursively archive `.build`, user data, downloaded dependencies or the whole project. SDK/Core/Framework, official sample paths, rejected 3D paths, model weights and executables are outside the supported inputs. Selected paths reject symlinks/junctions, traversal, external URLs, Windows device names, alternate streams and case aliases. Nested PSD2Live files are also inspected; placing a vendor script or an arbitrary weight binary inside that archive fails.

Runtime resources are capped at 32 MiB each and 96 MiB expanded in total; the actual application importer also imposes its 64 MiB compressed ZIP limit. Source files are capped at 256 MiB each, except the explicitly selected `project` field's `.psd2live` archive, which is capped at **320 MiB**. That exception is passed explicitly at the field's pinned-input call; another `.psd2live` filename does not automatically raise the generic source-file limit. Selected source bytes remain capped at **512 MiB** in total. PNG sides are capped at 8192. The tool streams ZIP writes and rechecks pinned input bytes after writing, so source drift fails without a successful receipt.

The nested PSD2Live archive permits at most 8192 entries and **2 GiB expanded**. Only the exact path `document/nodes/journal/[a-f0-9]{64}.json` may contain up to **64 MiB**. Its lowercase 64-hex filename stem must equal the SHA-256 of the actual streamed payload, and the separate project manifest must also match. All other nested JSON members, and all external specs, recipes, indices and JSON evidence, remain limited to **8 MiB**. Similar path prefixes, malformed hashes and revisions outside that journal directory receive no exception.

Observed PSD2Live portable v2 checkpoints also contain `history/revisions/[a-f0-9]{64}.json`. These exact paths are allowed at the ordinary **8 MiB** limit and remain bound to the independent manifest's payload SHA. Their revision identifiers are **not** payload SHA values: all 127 observed rolling-C entries had matching manifest SHA but different filename stems. The journal content-address rule therefore does not extend to history revisions. This observation and the original allowlist rejection are retained as separate reports rather than silently replacing the failed preflight.

These exceptions belong only to the maintainer's **offline source packaging tool**. Append-only authoring journals can exceed 8 MiB even when the current rig is legitimate; they are hashed in 1 MiB chunks and never parsed or executed by this exception. The explicit project-field limit of 320 MiB gives approximately 19% headroom over the measured final archive's 281,235,238 bytes; it is not a promise that future projects fit. Reading the complete project still costs decompression I/O up to the declared aggregate limit, and outer source-ZIP CRC checks read it again. Run this work outside the live companion process and reserve disk for both staged ZIPs and the source archive. No application upload/parser budget, runtime renderer budget, owner installer or program updater limit is increased. If the final project exceeds 2 GiB expanded, 320 MiB compressed in the project field, 256 MiB for any other source file, or the full selected-source 512 MiB cap, stop and report the actual sizes rather than increasing limits automatically.

Outputs publish using exclusive hard links on the destination filesystem. Normal errors remove only this invocation's published links, preserving existing or racing files. The three-file publish is **not a crash-atomic transaction**: a killed process can leave a partial candidate set. Do not release until all three outputs are present and match the sidecar hashes. Filesystems without hard-link support fail instead of falling back to overwrite.

## Verification status

Run the dedicated tests with:

```sh
python -m unittest discover -s tests -p test_package_live2d_character.py -v
```

These tests use deliberately synthetic MOC/PSD/CMO envelopes and a manifest-bound project ZIP. They exercise real AssetStore import, explicit source preservation, hash drift, embedded PSD mismatch, nested vendor/weight rejection, links/path escapes, output races and interrupted source writes. They are **not** evidence that an actual character plays or reopens in an Editor.

Journal tests stream compressed fixtures at 8 MiB + 1 byte, exactly 64 MiB and 64 MiB + 1 byte; they also check non-journal JSON, deceptive paths, content-address mismatch, independent manifest mismatch and CRC corruption. The 2 GiB aggregate rejection uses ZIP metadata fixtures, avoiding a giant 2 GiB test file. Actual rolling-authoring preflight reports bind before/after project SHA; drift remains a failed observation. Such a preflight validates only that observed project archive, not final character delivery or Core acceptance. The original 8 MiB rejection is retained in `review/live2d-packager-c15360-old-budget-red.json`; its historical filename does not assert the current completed-cell count.

Outer-project boundary tests use sparse, valid ZIPs and mock only outer-file hashing to avoid reading hundreds of MiB of empty fixture holes: 256 MiB + 1 byte reaches the actual project checker, exactly 320 MiB is accepted by the explicit field gate, and 320 MiB + 1 byte is rejected. Generic PSD/PNG and a generic project pin still reject above 256 MiB. Real final-file SHA, member CRC and SHA are checked separately without that mock; the preserved old-size rejection is `review/live2d-final-project-old-256m-red.json`.

See `review/live2d-character-packager-check.json` for the executed results and source hashes. The evolving r4 authoring directories are not packaged by the test suite. Final real packaging remains pending final authoring freeze and independent Core/visual review; packaging success alone must never be described as a completed Live2D character.

The later journal-budget change is separately bound by `review/live2d-packager-budget-update-check.json` and `review/live2d-packager-source-freeze.json`. Actual project preflight timing and peak RSS are in `review/live2d-packager-rolling-c-budget-preflight.json`; its observed SHA is a rolling checkpoint, not a frozen final character. Earlier reports retain their historical source hashes.

The subsequent explicit project-field size change is bound by `review/live2d-packager-project-field-limit-check.json` and the current source-freeze report. The actual final project (281,235,238 bytes, SHA `1dd382af309e1ee15292cc628361e93d52bf9d83cf077fec1c5ab96379202d70`) is checked separately in `review/live2d-final-project-size-and-format-preflight.json`. That gate covers its outer size/SHA and full nested member closure; the full selected-source sum and actual two-ZIP delivery still need their own packaging result.
