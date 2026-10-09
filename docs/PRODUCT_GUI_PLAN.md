# Product GUI direction

Date: 9 October 2026. Status: React/local PDF import and model-assisted paper-understanding workflows implemented. Live model evaluation awaits a connection key.

This plan uses the existing application and the Waves shader supplied in chat.
`Architecture_Final.pptx` is unrelated and excluded. The user authorized the React
implementation and then requested ordinary user input. PDF upload, isolated
Docling processing, persistent job stages and automatic library registration
were included. Run instructions and verification are in [GUI usage](GUI_USAGE.md).

## Current status

The local app supports uploads and processing with read-only evidence review;
it remains a prototype, not a finished hosted product. The
Python package is version 0.3.0. The service responds at
`http://127.0.0.1:8765`. The current implementation passes 81 Python tests, five frontend tests and browser
checks. Those checks cover implemented behavior, not product readiness or
scientific extraction accuracy.

| Capability | Actual status |
|---|---|
| Docling ingestion and structured exports | Implemented through the existing conversion CLI |
| Reusable Python library and RAG chunk exports | Implemented, with an optional LangChain bridge |
| Original PDF viewer, highlights, source navigation, crops | Implemented |
| Result inspector and attribution findings | Implemented for nine provisional curated Tetris3D annotations |
| Review queue | Implemented as a read-only view; two annotations need review |
| Comparison screen | Provisional result browser; compatibility assessment and ranking absent |
| Waves WebGL background | Implemented with the supplied shader and packed uniforms |
| Polished library/home screen | Implemented in React with actual PDF thumbnails and search |
| PDF upload and conversion jobs in the GUI | Implemented with cancellation, errors, and persistent registration |
| arXiv import in the GUI | Pending; the existing download CLI is available |
| Saved corrections, reviewer decisions and revision history | Not implemented |
| Automatic semantic experiment extraction | Not implemented |
| Figure interpretation and equation transcription | Not implemented; region detection exists |
| Cited paper overview and semantic relationships | Implemented with a pluggable model; NVIDIA preset, compatible APIs and local Ollama |
| Default AI service | Server-configured NVIDIA Nemotron 3 Super; optional runtime custom connection; requires app-owner credentials |
| Extracted reading view and full Markdown download | Implemented without a model dependency |
| Retrieval-backed question answering | Implemented per paper with up to three search rounds; real model quality remains unevaluated |
| Hosted multi-user product | Not implemented |

There are three converted papers and one unconverted parser reference. Only
Tetris3D has result annotations. Seven annotations pass limited attribution
checks. That is not independent human review or evidence of fair comparisons.
The current navigation prioritizes **Overview, Relationships, Read, Ask**, followed
by **Evidence, Issues, Results**. Inspection supports the understanding workflow.
See [paper understanding](PAPER_UNDERSTANDING.md) for provider setup and remaining limits.

## Visual direction

Create a calm research application with a deep plum shell, rose accents and
warm cream typography. The moving Waves field supplies the background identity.
Content surfaces provide stable contrast. The original PDF remains visually
unchanged, including its white page and original colors.

Use the shader most visibly on the library's welcome area and in the margins
around the application panels. Navigation can use a restrained translucent
surface. Reading panels use almost opaque surfaces so the requested grain and
flow cannot interfere with labels, tables or source text. Do not place animated
colors behind the PDF itself or small evidence text.

Use one consistent type scale, generous spacing and clearly differentiated
primary/secondary actions. Limit decorative elements. Keep controls visibly
interactive, with readable focus and selection states. No invented accuracy
scores, fake activity or placeholder success states.

## Screens and hierarchy

### Library: default entry

Open to a library instead of immediately placing the user in a dense PDF form.
Show a short welcome line, such as "Explore your papers," followed by recent
documents and existing projects when project persistence is implemented.

Each document card shows its title, a real cover thumbnail, corpus role and
processing state. Clicking it opens the document workspace. Keep filenames and
fingerprints inside document details. Provide search and filters only when they
operate on the actual library.

The finished import flow should offer PDF upload and an arXiv URL/ID, then show
real conversion stages, cancellation/error recovery and the resulting paper.
That flow requires backend work. Until it exists, the redesigned library opens
the current manifest documents without pretending an import action is active.

### Document workspace: focused reading

Use a compact navigation rail and document header with a back-to-library action,
paper title, task switcher and export action. The source page occupies most of
the screen. A resizable evidence panel stays beside it on a wide display.

Replace the current pair of generic dropdowns with a visible content switcher:
Results, Tables, Figures, Equations and Text. Within a category, show a readable
list with page labels and source previews. Selecting a row opens the evidence
inspector. Keep a compact picker where the viewport is too narrow for a list.

The inspector presents the selected value or region first, then its source,
method/dataset/metric, conditions, findings and supporting passages. Technical
JSON belongs in collapsed details. Separate machine check status from human
review status.

Keep the source toolbar small: page navigation, zoom and a detections toggle.
Put individual overlay categories in a local control panel instead of permanently
filling the header. Show related source boxes on selection; avoid outlining every
cell by default. Source selection must scroll the PDF pane without jumping the
whole application page.

### Review: an actionable workflow when persistence exists

Use a queue beside a source/detail view. Make the raw extraction and proposed
correction distinguishable. A reviewer should be able to retain ambiguity,
correct a mapping or reject a result, with a recorded reason and audit history.
These controls become available only after the persistence layer is implemented.

The current two merged F1 examples are suitable acceptance cases. Never replace
their pair of values with one number merely to make the interface look complete.

### Compare: experiment context before ranking

Use a matrix grouped by benchmark and metric, with source-linked values and
visible conditions. Show compatible, incompatible and pending assessments with
their reasons once the comparison engine exists. Keep incomplete groups clearly
pending and outside ranked views.

The existing comparison screen can be visually improved as a provisional result
browser. Its data must not be marketed as a validated cross-paper leaderboard.

### Integrations and exports

Provide a compact export panel that previews the data scope, review state and
provenance. Keep existing evidence JSON, result JSON/CSV/Markdown, checks and RAG
JSONL downloads. Explain Python usage separately from the researcher workflow.
The optional UI stays over the reusable SDK.

## Narrow Codex panel and mobile

The live GUI also runs inside a narrow Codex browser panel. Its current stacked
PDF/inspector layout requires substantial scrolling and gives dense PDF tables
too little space.

For the redesign, use a document picker and Source / Evidence tabs at narrow
widths. Preserve selection across those tabs. Offer an expanded source view and
keep zoom reachable. Avoid repeating all desktop navigation and metadata above
the paper. The background remains visible in small shell areas while content
fills the useful reading width.

Validate the layout in the actual Codex panel as well as at 390px, 768px and a
large desktop width. Check long titles, dense tables and review findings, rather
than testing only an empty home screen.

## Exact Waves shader contract

Use the complete fragment shader supplied by the user without editing its GLSL.
Render a fullscreen triangle through a plain WebGL1 context. Do not introduce
Three.js, a shader library, or an approximate CSS animation.

The named slider values are descriptive. Feed the supplied packed uniforms
directly rather than inventing a different percentage-to-uniform mapping.

| Uniform | Required value |
|---|---|
| First four `u_colors` entries | `(0.102, 0.078, 0.137)`, `(0.718, 0.365, 0.412)`, `(0.918, 0.804, 0.761)`, `(1.000, 0.961, 0.922)` |
| `u_scene` | `(canvas width, canvas height, elapsed seconds * -0.67, 4.0)` |
| `u_shape` | `(1.32, 0.49, 0.84, 0.01)` |
| `u_surface` | `(1.73, 1.08, 0.07, 2.00)` |
| `u_finish` | `(2.27, 0.00, 0.040, 0.35)` |
| `u_transform` | `(4984.0, 3.37, 0.40, 1.0)` |
| `u_space` | `(-0.13, 0.05, 0.0, 0.0)` with cursor off |
| `u_cursor` | `(0.0, 3.0, 0.54, 0.56)` |

The colors correspond to the user's low-to-high recipe `#1A1423`, `#B75D69`,
`#EACDC2`, `#FFF5EB`. Keep the shader's OKLab toggle enabled and its supplied hue
rotation. The resulting rendered colors include its postprocessing; do not
silently remove the hue rotation to force the output to match raw swatches.

Mount the canvas absolutely inside a positioned application shell, behind the
content, with `pointer-events: none` and no cursor event handling. Supply actual
drawing-buffer dimensions to `u_scene`. Cap devicePixelRatio at 2 and update
buffer size/viewport on resize. Pause requestAnimationFrame while the tab is
hidden and resume without accumulating hidden-time jumps.

Provide a static plum background when WebGL is unavailable or context creation
fails. Handle context loss and clean up the animation/GL resources on teardown.
Respect reduced-motion preferences by rendering a still frame, without changing
the shader source. A user-accessible motion toggle can override animation locally.

## Delivery order (original plan; implementation update above)

1. **Design review.** Present the Library and Document workspace in the new visual
   direction, using the supplied shader and current real paper data in a clearly
   identified design preview. Review this before replacing the live interface.
2. **Visual implementation.** Integrate the exact shader, shell, new library and
   evidence navigation with current APIs. Preserve existing viewer/export behavior
   and test the narrow Codex panel. This produces a polished read-only prototype.
3. **Functional product work.** Add GUI ingestion jobs, saved reviews and revision
   history. Evaluate semantic extraction and compatibility before enabling ranked
   comparisons. Add retrieval-backed answers only with source-grounding checks.
4. **Release readiness.** Validate full workflows with intended users, harden
   persistence and recovery, and choose local versus hosted deployment. A hosted
   version also needs authentication and isolation between users' documents.

A beautiful shader background does not complete the intelligence layer or make
the application product-ready. Library and document workspace are now implemented;
saved review decisions, semantic extraction, comparison compatibility and grounded
question answering remain functional milestones.
