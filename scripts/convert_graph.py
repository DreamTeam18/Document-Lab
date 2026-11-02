"""Convert the sample's nodes_chunked.jsonl + edges_chunked.csv to ingestion JSON."""

import argparse
import csv
import json
from pathlib import Path
from uuid import UUID

from app.models import Document


def convert(nodes, edges, document_id, title, edition):
    by_id = {node["uid"]: node for node in nodes}
    if len(by_id) != len(nodes):
        raise ValueError("Duplicate node UID in source graph")
    parents, references = {}, {}
    for edge in edges:
        source, target = edge["start_node_uid"], edge["end_node_uid"]
        if source not in by_id or target not in by_id:
            raise ValueError("Graph edge references a missing node")
        relation = edge["relationship_type"]
        if relation in ("CONTAINS", "HAS_CHUNK"):
            # Older exports have Passage -> parent HAS_CHUNK edges.
            if relation == "HAS_CHUNK" and by_id[source]["label"] == "Passage":
                source, target = target, source
            if target in parents and parents[target] != source:
                raise ValueError("Multiple parents require manual hierarchy normalization")
            parents[target] = source
        elif relation == "REFERENCES":
            references.setdefault(source, []).append(target)
    sections = []
    kinds = {"Chapter": "chapter", "Table": "table", "Math": "equation", "Diagram": "diagram"}
    for uid, node in by_id.items():
        props = node.get("properties", {})
        parent = parents.get(uid)
        if not parent and props.get("parent_uid") in by_id:
            parent = props["parent_uid"]
        text = props.get("text") or props.get("description") or props.get("latex") or ""
        if node["label"] == "Table":
            # Preserve structured cells, including units, rather than dropping table data.
            text = json.dumps(
                {k: props[k] for k in ("title", "headers", "rows", "notes") if k in props},
                ensure_ascii=False,
            )
        number = props.get("number") or props.get("table_id")
        if not number and parent:
            number = by_id[parent].get("properties", {}).get("number")
        page = props.get("page") or props.get("page_number")
        page = int(page) if str(page).isdigit() and int(page) > 0 else None
        sections.append(
            {
                "id": uid,
                "number": str(number or uid),
                "title": str(props.get("title") or node["label"]),
                "kind": kinds.get(node["label"], "section"),
                "parent_id": parent,
                "text": str(text or props.get("title") or node["label"]),
                "page": page,
                "references": references.get(uid, []),
            }
        )
    return Document.model_validate(
        {"id": document_id, "title": title, "edition": edition, "sections": sections}
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("nodes", type=Path)
    parser.add_argument("edges", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--document-id", type=UUID, required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--edition", required=True)
    args = parser.parse_args()
    nodes = [json.loads(line) for line in args.nodes.read_text().splitlines() if line.strip()]
    with args.edges.open(newline="") as stream:
        edges = list(csv.DictReader(stream))
    document = convert(nodes, edges, args.document_id, args.title, args.edition)
    # Do not overwrite a curated conversion by accident.
    with args.output.open("x") as stream:
        stream.write(document.model_dump_json(indent=2))
    print(f"Converted {len(document.sections)} content records")


if __name__ == "__main__":
    main()
