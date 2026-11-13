# 2D character images

These are four full-character transparent PNG states generated from the user's
reattached reference. They are not independently separated layers, a Live2D model,
a mesh, or evidence of actual eye tracking.

Prefer the delivered `*.companion.json` single-file package: import it in Character
Studio to preview, then explicitly activate it. The package includes the selected
eye/mouth animation regions; preview never changes the active appearance.

For manual PNG imports, use `import-selection.json` for state mapping and the same
`animation_regions` metadata, using this mapping:

| App state | File |
|---|---|
| `idle` | `idle.png` |
| `talk` | `talking.png` |
| `blink` | `blink.png` |
| `talk_blink` | `talking_blink.png` |

All canvases are 1070 × 1470 RGBA. The four originals are copied byte-for-byte;
their SHA256 and lineage are in `source-provenance.json`. The application strips
metadata and safely normalizes imported PNG encoding through its existing importer.

`png-states-source.zip` is an extraction bundle: extract it and choose the four
PNG files in the uploader. It is **not** a Live2D or layered-2d ZIP and must not be
offered to either of those importers.

`runtime-import-check.json` records actual isolated application import/get/resolve.
`state-alignment-measurement.json` records read-only pixel differences. Facial
states have measurable changes outside eyes and mouth. The supplied region metadata
keeps idle as the base and updates only the eyes/mouth. Real Chrome synthetic-audio
acceptance recorded zero changed body RGBA components and both voiced/silent mouth
states (`review/png-region-stage-browser.json`). Final real-model playback and
human art acceptance remain separate checks.
No Windows/RTX 4060, eye-tracking hardware, or final art acceptance is claimed here.
