"""Optional source-focused configuration of native Basic/Local Search.

No paper facts, entity names or reference answers are inserted. Native retrieval
still selects the context. Every tuned prompt is saved with the answer.
"""
from pathlib import Path
from _common import digest

POLICY = """
---Paper evidence policy---
Answer every explicit part of the question, concisely, using only the supplied
paper evidence. Do not fill gaps with general knowledge. If a requested part is
not supported by this context, identify that missing part explicitly.
Prefer the original Sources passages over generated entity, relationship or
report descriptions when they differ. Those descriptions are retrieval aids,
not independently verified facts.
Preserve roles, ownership and scope. Authors may describe a compared baseline,
an evaluation procedure or dataset construction rather than their proposed
method. Distinguish a training dataset, an evaluation benchmark and a generator
used to construct evaluation scenes. Do not transfer a baseline's implementation
or prompts to the proposed method.
Keep separate taxonomies and lists separate. If names or labels are requested,
copy their exact names from a supporting Source; do not combine similar lists.
Empirical improvements and intended goals are not formal guarantees. Do not say
the method always prevents errors or ensures correctness unless the supplied
evidence explicitly establishes that guarantee.
Distinguish instructions in a quoted prompt from demonstrated implementation or
observed results. Do not add unneeded examples or mechanisms that the question
does not require. Cite actual provided record IDs and do not fabricate quotations.
"""


def apply_profile(config, mode, output, profile):
    if profile == 'native':
        return {'query_profile': 'native'}
    if profile != 'source-focused' or mode not in {'local', 'basic'}:
        raise ValueError('Source-focused profile supports native Basic/Local Search only.')
    if mode == 'local':
        from graphrag.prompts.query.local_search_system_prompt import LOCAL_SEARCH_SYSTEM_PROMPT
        prompt = LOCAL_SEARCH_SYSTEM_PROMPT.replace('and incorporating any relevant general knowledge.',
                                                   'using only the supplied paper evidence.')
        cfg = config.local_search
        cfg.max_context_tokens, cfg.top_k_entities, cfg.top_k_relationships = 10000, 12, 24
        cfg.text_unit_prop, cfg.community_prop = .65, .05
        settings = {k: getattr(cfg, k) for k in ['max_context_tokens', 'top_k_entities', 'top_k_relationships',
                                               'text_unit_prop', 'community_prop']}
    else:
        from graphrag.prompts.query.basic_search_system_prompt import BASIC_SEARCH_SYSTEM_PROMPT
        prompt, cfg = BASIC_SEARCH_SYSTEM_PROMPT, config.basic_search
        cfg.max_context_tokens, cfg.k = 10000, 10
        settings = {'max_context_tokens': cfg.max_context_tokens, 'k': cfg.k}
    path = Path(output) / 'query_prompt.txt'
    path.write_text(prompt + '\n' + POLICY, encoding='utf-8')
    cfg.prompt = str(path.resolve())
    return {'query_profile': profile, 'query_prompt_sha256': digest(path), 'query_settings': settings,
            'development_note': 'Profile tuned on source-backed development cases; not a held-out accuracy result.'}
