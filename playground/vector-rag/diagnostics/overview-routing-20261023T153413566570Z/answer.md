Question: Tell me about the paper ?

Status: answered

Tetris3D is a generative framework for single-image 3D scene reconstruction that recovers objects which are physically and geometrically coherent as a scene. [S1]

> We propose Tetris3D, a generative framework for single-image 3D scene reconstruction that recovers objects which are physically and geometrically coherent as a scene.

[S1] Pages 1; chunk `c7cca5c7618d084c-00001`; refs: #/texts/20, #/texts/21

Existing methods often generate objects independently or couple them implicitly, providing limited guidance for ensuring fine-grained spatial compatibility between neighboring objects that interact with one another. [S1]

> Existing methods often generate objects independently or couple them implicitly, providing limited guidance for ensuring fine-grained spatial compatibility between neighboring objects that interact with one another.

[S1] Pages 1; chunk `c7cca5c7618d084c-00001`; refs: #/texts/20, #/texts/21

Tetris3D explicitly conditions the generation of each object on the geometry of surrounding objects and their physical relationships, guiding its shape and pose to remain geometrically and physically plausible within the scene. [S1]

> To address this, we explicitly condition the generation of each object on the geometry of surrounding objects and their physical relationships, guiding its shape and pose to remain geometrically and physically plausible within the scene.

[S1] Pages 1; chunk `c7cca5c7618d084c-00001`; refs: #/texts/20, #/texts/21

The authors introduce ComOb, a physics simulation-based dataset of 1.2M scenes featuring physical interactions across diverse object categories, with per-object meshes and pairwise physical relation annotations. [S1]

> Moreover, we introduce ComOb, a physics simulation-based dataset of 1.2M scenes featuring physical interactions across diverse object categories, with per-object meshes and pairwise physical relation annotations.

[S1] Pages 1; chunk `c7cca5c7618d084c-00001`; refs: #/texts/20, #/texts/21

Comprehensive experiments on synthetic and real-world scenes show that Tetris3D recovers coherent object shapes and poses even when interacting regions are occluded, and achieves state-of-the-art performance in both generation quality and physical stability. [S1]

> Comprehensive experiments on synthetic and realworld scenes show that Tetris3D recovers coherent object shapes and poses even when interacting regions are occluded, and achieves state-of-the-art performance in both generation quality and physical stability.

[S1] Pages 1; chunk `c7cca5c7618d084c-00001`; refs: #/texts/20, #/texts/21

The framework generates objects autoregressively, using previously generated neighbors as interaction context, with a VLM inferring a physical dependency hierarchy to derive the generation order. [S5]

> Specifically, we reconstruct the scene by generating objects autoregressively, using previously generated neighbors as interaction context. We use a vision-language model (VLM) to infer a physical dependency hierarchy and derive the generation order by topologically sorting this hierarchy.

[S5] Pages 2; chunk `c7cca5c7618d084c-00003`; refs: #/texts/28, #/texts/29

Interaction conditions are encoded on the same 3D grid used for generation and injected into corresponding tokens, building on TRELLIS.2's voxel-based generative backbone. [S5]

> To inject these conditions in a manner spatially aligned with generation, we build on TRELLIS.2's voxel-based generative backbone (Xiang et al., 2026). These interaction conditions are encoded on the same 3D grid used for generation and injected into the corresponding tokens, providing local guidance for generating each object shape that is spatially compatible with neighboring surfaces.

[S5] Pages 2; chunk `c7cca5c7618d084c-00003`; refs: #/texts/28, #/texts/29

Limitations include that physical conditions provide learned guidance rather than hard physical constraints, so they do not guarantee physically valid configurations in every case, and the inference pipeline relies on off-the-shelf models whose errors can propagate through the autoregressive process. [S4]

> However, these conditions provide learned guidance rather than hard physical constraints, and therefore do not guarantee physically valid configurations in every case. Our inference pipeline relies on off-the-shelf models for depth and camera estimation, object segmentation, and physical relation reasoning. Although these modules enable reconstruction from a single RGB image, their errors can affect the conditions used for generation.

[S4] Pages 22, 23, 24, 25, 26; chunk `c7cca5c7618d084c-00083`; refs: #/texts/411, #/texts/414, #/texts/426, #/texts/437, #/texts/448

Citations identify source chunks; listed pages/refs can cover more than the exact quotation.
Exact-quote checks do not independently verify a claim's meaning or factual correctness.
