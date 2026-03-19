"""Export embeddings for semantic intent discovery."""

import json
from pathlib import Path
from typing import Any

from rdflib import Graph, Namespace


OC = Namespace("https://ontoskills.sh/ontology#")
MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_DIM = 384


def extract_intents_from_ontology(ontology_path: Path) -> list[dict[str, Any]]:
    """Extract all intents and source their associated skills from ontology.

    Args:
        ontology_path: Path to Turtle ontology file.

    Returns:
        List of dicts with 'intent' and 'skills' keys.
    """
    g = Graph()
    g.parse(ontology_path, format="turtle")

    query = """
    PREFIX oc: <https://ontoskills.sh/ontology#>

    SELECT ?skill ?intent
    WHERE {
        ?skill oc:resolvesIntent ?intent .
    }
    """

    intent_to_skills: dict[str, list[str]] = {}
    for row in g.query(query):
        skill_id = str(row.skill).split("#")[-1].split("/")[-1]
        intent = str(row.intent)

        if intent not in intent_to_skills:
            intent_to_skills[intent] = []
        if skill_id not in intent_to_skills[intent]:
            intent_to_skills[intent].append(skill_id)

    return [
        {"intent": intent, "skills": skills}
        for intent, skills in intent_to_skills.items()
    ]


def export_embeddings(
    ontology_root: Path,
    output_dir: Path,
) -> None:
    """Export ONNX model, tokenizer, and pre-computed intent embeddings.

    Args:
        ontology_root: Root directory containing ontology TTL files.
        output_dir: Directory to write embedding artifacts.
    """
    from sentence_transformers import SentenceTransformer
    from transformers import AutoTokenizer

    output_dir.mkdir(parents=True, exist_ok=True)

    # 1. Load model and export to ONNX
    print(f"Loading model: {MODEL_NAME}")
    model = SentenceTransformer(MODEL_NAME)

    # Export ONNX using optimum
    try:
        from optimum.onnxruntime import ORTModelForFeatureExtraction
        from optimum.exporters.onnx import main_export

        main_export(
            MODEL_NAME,
            output=output_dir,
            task="feature-extraction",
        )
        print(f"Exported ONNX model to {output_dir}")
    except ImportError:
        # Fallback: export via sentence-transformers
        model.save(str(output_dir / "model"))
        print(f"Exported model to {output_dir / 'model'}")

    # 2. Export tokenizer
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    tokenizer.save_pretrained(str(output_dir))
    print(f"Exported tokenizer to {output_dir}")

    # 3. Extract and embed intents
    index_path = ontology_root / "index.enabled.ttl"
    if not index_path.exists():
        index_path = ontology_root / "index.ttl"

    if not index_path.exists():
        # Fallback: scan all .ttl files
        all_intents = []
        for ttl_file in ontology_root.rglob("*.ttl"):
            all_intents.extend(extract_intents_from_ontology(ttl_file))
    else:
        all_intents = extract_intents_from_ontology(index_path)

    # Deduplicate intents
    intent_map: dict[str, list[str]] = {}
    for item in all_intents:
        intent = item["intent"]
        if intent not in intent_map:
            intent_map[intent] = []
        intent_map[intent].extend(item["skills"])

    unique_intents = [
        {"intent": intent, "skills": list(set(skills))}
        for intent, skills in intent_map.items()
    ]

    if not unique_intents:
        print("No intents found in ontology")
        return

    # Compute embeddings
    intent_strings = [item["intent"] for item in unique_intents]
    print(f"Computing embeddings for {len(intent_strings)} intents...")

    embeddings = model.encode(intent_strings, convert_to_numpy=True)

    # Build output
    intents_data = {
        "model": MODEL_NAME,
        "dimension": EMBEDDING_DIM,
        "intents": [
            {
                "intent": item["intent"],
                "embedding": emb.tolist(),
                "skills": item["skills"],
            }
            for item, emb in zip(unique_intents, embeddings)
        ],
    }

    intents_path = output_dir / "intents.json"
    with open(intents_path, "w") as f:
        json.dump(intents_data, f)

    print(f"Exported {len(unique_intents)} intent embeddings to {intents_path}")
