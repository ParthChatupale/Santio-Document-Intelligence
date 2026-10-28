"""Load a registered native index for query; no indexing side effects."""
from pathlib import Path
from _common import connection

def load_config(folder):
    import yaml
    from graphrag.config.models.graph_rag_config import GraphRagConfig
    folder = Path(folder).resolve()
    model, base, _ = connection()
    data = yaml.safe_load((folder / "settings.yaml").read_text(encoding="utf-8"))
    data["completion_models"]["default_completion_model"].update(model=model, api_base=base)
    for key in ["input_storage", "output_storage", "update_output_storage", "reporting"]:
        data[key]["base_dir"] = str(folder / data[key]["base_dir"])
    data["cache"]["storage"]["base_dir"] = str(folder / data["cache"]["storage"]["base_dir"])
    data["vector_store"]["db_uri"] = str(folder / data["vector_store"]["db_uri"])
    if (folder / "prompts/extract_graph.txt").exists():
        data["extract_graph"]["prompt"] = str(folder / "prompts/extract_graph.txt")
    return GraphRagConfig.model_validate(data)
