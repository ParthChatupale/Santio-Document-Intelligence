"""Assemble Docling Graph's upstream viewer assets omitted from its wheel.

No extraction or graph construction happens here. The input is the exported
nodes/edges JSON. The upstream v1.9.1 template gets small presentation changes
for entity names, relationship arrows, and escaped detail values.
"""

import json
from pathlib import Path


ASSETS = Path(__file__).resolve().parent / "vendor" / "docling-graph"


def render_viewer(graph_data, output):
    template = (ASSETS / "interactive_template.html").read_text(encoding="utf-8")
    scripts = {
        "<!-- Cytoscape core - EMBEDDED_CYTOSCAPE_PLACEHOLDER -->": "cytoscape.min.js",
        "<!-- Dagre layout extension - EMBEDDED_DAGRE_PLACEHOLDER -->": "dagre.min.js",
        "<!-- Cytoscape-Dagre extension - EMBEDDED_CYTOSCAPE_DAGRE_PLACEHOLDER -->": "cytoscape-dagre.js",
    }
    for marker, filename in scripts.items():
        if marker not in template:
            raise ValueError(f"Upstream viewer placeholder missing: {filename}")
        template = template.replace(marker, "<script>\n" + (ASSETS / filename).read_text(encoding="utf-8") + "\n</script>")
    elements = {
        "nodes": [{"data": {**node, "id": str(node["id"]), "display_name": str(node.get("name") or node.get("title") or node.get("statement") or node.get("label") or node["id"])[:65]}}
                  for node in graph_data["nodes"]],
        "edges": [{"data": {**edge, "source": str(edge["source"]), "target": str(edge["target"]), "id": f"edge-{i}", "display_relation": str(edge.get("label", "related to")).replace("_", " ").lower()}}
                  for i, edge in enumerate(graph_data["edges"])],
    }
    payload = json.dumps(elements, ensure_ascii=False, allow_nan=False)
    for character, escaped in [("<", "\\u003c"), (">", "\\u003e"), ("&", "\\u0026"), ("\u2028", "\\u2028"), ("\u2029", "\\u2029")]:
        payload = payload.replace(character, escaped)
    template = template.replace("/* ELEMENTS_DATA_PLACEHOLDER */", f"const graphElements = {payload};")
    template = template.replace("'label': 'data(label)'", "'label': 'data(display_name)', 'text-wrap': 'wrap', 'text-max-width': 150")
    template = template.replace("'target-arrow-shape': 'none'", "'target-arrow-shape': 'triangle', 'label': 'data(display_relation)', 'font-size': 9, 'text-background-color': '#1e2428', 'text-background-opacity': 0.9")
    template = template.replace("minZoom: 0.1", "minZoom: 0.01")
    template = template.replace("const neighborhood = node.neighborhood().add(node);", "const neighborhood = node.neighborhood().add(node);\n            cy.animate({fit: {eles: neighborhood, padding: 60}, duration: 250});")
    template = template.replace('<label for="layout-select">Layout Algorithm</label>', '<label for="entity-search">Find an entity</label><input id="entity-search" list="entity-options" placeholder="Method, experiment or metric" style="box-sizing:border-box;width:100%;padding:9px;margin:0 0 12px;background:#2d333b;color:#f2f2f2;border:1px solid #586069;border-radius:6px"><datalist id="entity-options"></datalist><label for="layout-select">Layout Algorithm</label>')
    # Source-derived strings must be escaped before upstream's details HTML.
    template = template.replace("// Node click handler - show details and highlight", "const escapeHtml = value => String(value).replace(/[&<>\"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',\"'\":'&#39;'}[c]));\n        // Node click handler - show details and highlight")
    template = template.replace("displayValue = JSON.stringify(value, null, 2);", "displayValue = escapeHtml(JSON.stringify(value, null, 2));")
    template = template.replace("? String(value).substring(0, 100) + '...'\n                            : value;", "? escapeHtml(String(value).substring(0, 100)) + '...'\n                            : escapeHtml(value);")
    template = template.replace("displayValue.length > 200", "displayValue.length > 3000").replace("displayValue.substring(0, 200)", "displayValue.substring(0, 3000)")
    template = template.replace("String(value).length > 100", "String(value).length > 1500").replace("String(value).substring(0, 100)", "String(value).substring(0, 1500)")
    search_script = """<script>
    const entitySearch = document.getElementById('entity-search');
    const entityOptions = document.getElementById('entity-options');
    if (entitySearch && entityOptions) {
      [...new Set(graphElements.nodes.map(n => n.data.display_name))].sort().forEach(name => {
        const option = document.createElement('option'); option.value = name; entityOptions.appendChild(option);
      });
      const focusEntity = () => {
        const query = entitySearch.value.trim().toLowerCase(); if (!query) return;
        let matches = cy.nodes().filter(n => String(n.data('display_name')).toLowerCase() === query);
        if (!matches.length) matches = cy.nodes().filter(n => String(n.data('display_name')).toLowerCase().includes(query));
        if (matches.length) matches.first().emit('tap');
      };
      entitySearch.addEventListener('change', focusEntity);
      entitySearch.addEventListener('keydown', e => { if (e.key === 'Enter') focusEntity(); });
    }
    </script>"""
    template = template.replace("</body>", search_script + "</body>")
    output.write_text(template, encoding="utf-8")
    return output
