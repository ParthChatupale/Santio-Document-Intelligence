# Graph room visual redesign

24 October 2026. Sandbox only; main website migration awaits review of this version.

Open http://127.0.0.1:8775/ and reload once if an older page is open.
The existing `tetris-full-validated-v14` run is served without re-indexing.
All 334 native entities and 425 native relationships remain available by default.
The extraction, prompts, embeddings, provider adapters and stored graph are unchanged.

## Presentation and interaction

- Full-canvas plum background, consistent rose/teal/lavender/blue category styling.
- Layered nodes with category glyphs, bounded connectivity sizing and selection rings.
- Deterministic packed community layout with local spacing and finite settling.
- Curved connections, curve-aware picking, and direction arrows derived exclusively
  from the existing directed assertion evidence; native undirected endpoint order
  never creates direction.
- Camera transitions, zoom, fit, reset, optional labels, community outlines,
  clickable overview map and fullscreen presentation control.
- Floating entity navigator and collapsible Details/Ask inspector. Every entity
  is available in the searchable list; there is no initial node-count cutoff.
- Relationship card, exact supporting quotations and original PDF page previews.
  Review warnings remain visible. Occurrence weights are confined to metadata
  and are explicitly distinguished from confidence.
- Saved answers/citations and original question endpoints are retained. Answer
  highlighting maps actual cited record IDs, excluding merely retrieved records.
- Narrow layouts close the navigator when the inspector opens, avoid horizontal
  overflow and show independently scrollable passage/PDF sections in the dialog.
- Rendering is event-driven after layout/camera settling, with capped DPR, bounded
  motion, reduced-motion support and no animated shader behind the graph.

## Verification

- 49 GraphRAG sandbox Python regression checks passed in its Python 3.13 environment.
- The Docling preparation contract passed separately in the existing main environment,
  where Docling is installed (the graph environment does not contain docling_core).
- Eight JavaScript checks cover repeatable layout, preserved identities, pinning,
  arrow provenance, curved picking, camera framing, counts, sizing and cited-only
  highlighting. `node --check` also passed.
- Live browser: full 334/425 counts; dataset filter gives 29 nodes and one internal
  connection; search DINOv3; inspect TRELLIS.2 -> USES -> DINOv3; open original PDF
  page 2; verify the 980-pixel page preview loaded; node drag/camera interaction;
  fullscreen enter/exit; saved question UI; desktop 1440x900 and narrow 390x844.
- At 390 pixels the document has no horizontal overflow. Temporary browser viewport
  overrides were reset after verification.
- `verification/ui-redesign-20261024/scope-check.json` confirms the native graph
  payload remained identical and none of 35 fingerprinted main-app/provider files
  changed during this work.
- No new model requests or graph extraction were made for these UI checks; saved
  answers were used to verify citation rendering. This is UI verification, not a
  new semantic accuracy evaluation.

Screenshots, scope proof and Python test output are in
`verification/ui-redesign-20261024/`.

## Review before main-site migration

Review this sandbox's appearance and interactions first. Integrating the graph
feature into the main app remains a separate step. The existing graph's documented
semantic limitations still apply; the visual redesign does not verify graph claims.
