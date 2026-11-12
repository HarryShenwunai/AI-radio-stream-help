# Original character source

**The 3D reconstruction was rejected by the user on 2026-11-12. The selected direction is 2D.**

After the user reattached the portrait on 2026-11-12, the parent agent generated
`reference-guidance.png` from that fresh attachment. It is a multi-view design aid,
not a pre-existing 3D model or proof of fidelity. The unseen back, charcoal trousers
and pale shoes are explicitly new design inferences. The raw chat attachment is
not currently present as an independent local file; its derivative is readable.

Rejected source geometry, its builder and rendered images are isolated under the ignored
`.build/rejected-3d-reference/` audit directory. They are not product assets, not previews,
and must not be added to Git, a release or an installation package.

`contract.json` records this rejection. A new 2D layer contract will define actual imported
RGBA layers, anchors, draw order and bounded motion. A static PNG is not a Live2D model;
no `.moc3` or Cubism rig is claimed. Existing self-service PNG imports remain supported.
Reference files and renders should retain their actual provenance and usage terms; do not assign
CC0 or an invented artist identity. Do not copy official Live2D examples into this source.

Current assets and measured limitations: `assets/character-2d/README.md` and
`docs/implementation/avatar-2d-layers.md`. The optional layer parser is working,
but the selected character has no accepted independently cut layer set yet.
