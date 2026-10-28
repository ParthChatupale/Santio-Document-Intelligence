# Isolated-node extraction audit

Offline replay of saved model output. No model calls or graph edits.

- Native graph: 334 entities / 425 edges.
- Actual isolated entities: 71.
- Citation-like isolates: 24; structure-like: 2.
- Matched responses replayed: 352; replay differences: 0.
- Same-source prior-declaration experiment: 100 candidate occurrences pass existing checks; semantic correctness is NOT established.
- Candidate pairs absent from current graph: 47; isolates touched: 14.

Counts of occurrences, candidate pairs and true scientific facts are different quantities.

| Isolated entity | Type | PDF pages | Rejected candidate occurrences | Declaration experiment candidates |
| --- | --- | --- | ---: | ---: |
| 3D GENERATION | CONCEPT | 2 | 1 | 0 |
| 3D SCENE GENERATION FROM AN IMAGE | CONCEPT | 2 | 1 | 0 |
| AMODAL GENERATION METHODS COMBINED WITH POSE ESTIMATION | METHOD | 7 | 1 | 0 |
| ARDELEAN ET AL., 2025 | ORGANIZATION | 15, 16 | 0 | 0 |
| ASSETS | CONCEPT | 15, 16 | 2 | 1 |
| AUTOREGRESSIVE CO-GENERATION | TOOL | 15, 16 | 2 | 1 |
| AZINOVI´C ET AL., 2022 | ORGANIZATION | 15, 16 | 0 | 0 |
| BOXES | CONCEPT | 17 | 1 | 1 |
| CHAMFER DISTANCE | METRIC | 21 | 2 | 0 |
| CHAMFER DISTANCE (CD-S, CD-O) | METRIC | 20 | 0 | 0 |
| CHEN ET AL., 2026A | ORGANIZATION | 15, 16 | 0 | 0 |
| CHEN ET AL., 2026B | ORGANIZATION | 15, 16 | 0 | 0 |
| COMPLETE IMAGES WITHOUT OCCLUSION | DATASET | 16, 17 | 3 | 0 |
| CONES | CONCEPT | 17 | 1 | 1 |
| COVERAGE (COV) | METRIC | 21 | 2 | 0 |
| CYLINDERS | CONCEPT | 17 | 1 | 1 |
| DAHNERT ET AL., 2024 | ORGANIZATION | 15, 16 | 0 | 0 |
| DAI ET AL., 2017 | ORGANIZATION | 15, 16 | 0 | 0 |
| DAI ET AL., 2024 | ORGANIZATION | 15, 16 | 0 | 0 |
| EEVEE | TOOL | 18 | 2 | 0 |
| F-SCORE | METRIC | 20 | 2 | 0 |
| FLOATING | CONCEPT | 15, 16 | 2 | 0 |
| FU ET AL., 2021 | ORGANIZATION | 15, 16 | 0 | 0 |
| GENERATION ORDER | CONCEPT | 27 | 1 | 0 |
| HUANG ET AL., 2025 | ORGANIZATION | 15, 16 | 0 | 0 |
| IMAGES OCCLUDED BY THE PRIMITIVES | DATASET | 16, 17 | 3 | 0 |
| IMAGES WITH SYNTHETIC OCCLUSION | DATASET | 16, 17 | 3 | 0 |
| INDOOR ROOMS | DATASET | 15, 16 | 2 | 0 |
| INPUT IMAGE | CONCEPT | 23 | 0 | 0 |
| KAIST AI | ORGANIZATION | 1 | 0 | 0 |
| LI ET AL., 2026A | ORGANIZATION | 15, 16 | 0 | 0 |
| LI ET AL., 2026C | ORGANIZATION | 15, 16 | 0 | 0 |
| LIN ET AL., 2026A | ORGANIZATION | 15, 16 | 0 | 0 |
| LIN ET AL., 2026B | ORGANIZATION | 15, 16 | 0 | 0 |
| LIU ET AL., 2022 | ORGANIZATION | 15, 16 | 0 | 0 |
| MENG ET AL., 2026 | ORGANIZATION | 15, 16 | 0 | 0 |
| MINIMUMMATCHING DISTANCE (MMD) | METRIC | 21 | 2 | 0 |
| MULTIPLE INSTANCES | CONCEPT | 15, 16 | 2 | 1 |
| NIU ET AL., 2026 | ORGANIZATION | 15, 16 | 0 | 0 |
| OBJECT INTERACTIONS | CONCEPT | 3, 15, 16 | 2 | 1 |
| OBJECT-CENTRIC 3D SCENE RECONSTRUCTION FROM A SINGLE IMAGE | CONCEPT | 3 | 0 | 0 |
| OPEN-SET DATA | DATASET | 15, 16 | 2 | 0 |
| OURS (GT) | METHOD | 22 | 28 | 1 |
| PENETRATION | CONCEPT | 15, 16 | 2 | 0 |
| PHYSICAL DEPENDENCY ORDER | CONCEPT | 3 | 0 | 0 |
| PHYSICAL SIMULATION | CONCEPT | 2 | 1 | 0 |
| PLANKS | CONCEPT | 17 | 1 | 1 |
| PRECΤ | METRIC | 20 | 0 | 0 |
| PRETRAINED CROSS-ATTENTION | METHOD | 16 | 2 | 0 |
| RECΤ | METRIC | 20 | 0 | 0 |
| ROBOTIC MANIPULATION | CONCEPT | 2 | 1 | 0 |
| SCENE DATASETS | DATASET | 15, 16 | 2 | 0 |
| SCENE GENERATION BASELINES | METHOD | 7 | 1 | 0 |
| SCENE-LEVEL GENERATION | CONCEPT | 15, 16 | 2 | 0 |
| SHAPE AND POSE | CONCEPT | 15, 16 | 2 | 1 |
| SHI ET AL., 2026 | ORGANIZATION | 15, 16 | 0 | 0 |
| SLAT | CONCEPT | 2, 3 | 0 | 0 |
| SPHERES | CONCEPT | 17 | 1 | 1 |
| STACKING | DATASET | 17 | 1 | 0 |
| TAB. 1 | CONFIGURATION | 7 | 1 | 0 |
| TAB. 2 | CONFIGURATION | 7 | 1 | 0 |
| TANG ET AL., 2024 | ORGANIZATION | 15, 16 | 0 | 0 |
| TANG ET AL., 2026 | ORGANIZATION | 15, 16 | 0 | 0 |
| TODOROV ET AL., 2012 | TOOL | 2 | 0 | 0 |
| TORI | CONCEPT | 17 | 1 | 1 |
| VR/AR | CONCEPT | 2 | 1 | 0 |
| WEDGES | CONCEPT | 17 | 1 | 1 |
| XIA ET AL., 2026; SIDDIQUI ET AL., 2026 | DATASET | 15 | 2 | 1 |
| YAO ET AL., 2025 | ORGANIZATION | 15, 16 | 0 | 0 |
| ZHANG ET AL., 2026 | ORGANIZATION | 15, 16 | 0 | 0 |
| ZHAO ET AL., 2025A | ORGANIZATION | 15, 16 | 0 | 0 |

Full request hashes, quotations, rejection reasons, source text and replay candidates are in audit.json.
The source-backed interpretation and repair priorities are documented separately in ISOLATION_AUDIT.md.
