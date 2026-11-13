# Original Live2D development evidence

Updated 2026-11-13 UTC. This is a development record, not a release acceptance statement.
The user-rejected 3D assets remain excluded and are not linked as previews.

The current original source has 42 independent layers: head, cloth, palms, ten fingers,
and a separate mug. Technical attachment meshes reuse that same mug artwork with permanent
zero opacity; only one mug is drawn. These are ordinary authored mesh/deformer/glue objects,
not a runtime image overlay or two visible character states.

Genuine PSD2Live projects, CMO3, MOC3, model3, physics, expressions and motions have been
exported locally. The owner-provided actual Cubism Core accepted the original model.
Opening the CMO3 in the official Windows Cubism Editor remains untested.

Verified technical evidence:

- Continuous shoulder/elbow geometry: actual Core tested eight extrema, twelve joint
  combinations and fourteen interior poses without triangle winding flips. Maximum measured
  edge stretch was 1.223. Visible coverage still needs a separate artistic review.
- Ten actual nonrigid finger controls: root/palm contact, tip displacement, joint bending
  and Procrustes checks reject the earlier rigid-rotation counterexample.
- A flattened six-axis cup-follow approximation failed independent interior tests and is
  retained as a rejected regression case. Its generator now requires explicit experimental use.
- The native attachment revision copies the actual body and arm deformer chain into an
  independent cup branch. In actual Core, 512 regression poses and a separately sealed 1000-pose
  set stayed within the predeclared one-source-pixel grip budget; the worst new-set error was
  0.005954 pixels. Detached mug geometry remained exactly independent of body motion.
- Product tests of this attachment revision verified actual HTTP import, manual translation
  and rotation, hidden technical meshes, visibility, and unchanged physical character meshes.
  Full four-action and final-art acceptance are separate checks.

Primary local reports are `review/hand-cup-native-glue-shared-root-seed1000.json`,
`review/hand-cup-native-glue-shared-root-v2-product-probe.json` and the continuous-cloth
reports. Screenshot/video evidence remains under `dist/evidence-original-character-*`.
These reports bind their actual source hashes and must not be reused for a later model.

Remaining work includes the final eye meshes from corrected atlas extraction, the selected
half-lidded eye key and lip thickness, dynamic underpaint coverage and ordering, four complete
hand/mug actions, and a single formally synchronized source PSD/editable project/runtime
revision. Texture-only development probes do not prove that their ancestor PSD was updated.
Windows 4060, physical hardware, and official Editor reopening are not claimed as tested.
