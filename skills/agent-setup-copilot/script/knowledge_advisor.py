#!/usr/bin/env python3
import argparse
import sys
import yaml
from pathlib import Path

# Try to find the bundle directory relative to this script
BUNDLE_DIR = Path(__file__).parent / "bundle"

def load_ontology():
    data = {}
    instances_dir = BUNDLE_DIR / "instances"
    if not instances_dir.exists():
        return None
    
    for f in instances_dir.glob("*.yaml"):
        with open(f, "r", encoding="utf-8") as file:
            content = yaml.safe_load(file)
            # Most instances are under a top-level key like 'components', 'devices', etc.
            for key, value in content.items():
                if isinstance(value, list):
                    for item in value:
                        if "id" in item:
                            data[item["id"]] = item
    return data

def main():
    parser = argparse.ArgumentParser(description="Tailored Knowledge Advisor for Local AI Setup")
    parser.add_argument("--term", required=True, help="Terminology ID (e.g., rtx-3090)")
    parser.add_argument("--level", choices=["simple", "technical", "dual"], default="simple", help="Explanation depth")
    
    args = parser.parse_args()
    
    ontology = load_ontology()
    if not ontology:
        print("Error: Ontology bundle not found.", file=sys.stderr)
        sys.exit(1)
        
    item = ontology.get(args.term)
    if not item:
        print(f"Error: Term '{args.term}' not found in ontology.", file=sys.stderr)
        sys.exit(1)
        
    explanations = item.get("explanations", {})
    
    if args.level == "dual":
        simple_text = explanations.get("simple", "")
        tech_text = explanations.get("technical", "")
        if not simple_text and not tech_text:
            explanation = item.get("note", item.get("llm_perf_note", "No specific explanation available."))
        else:
            explanation = f"{simple_text}\n\n(기술적 스펙: {tech_text})"
    else:
        explanation = explanations.get(args.level, explanations.get("simple"))
        if not explanation:
            # Fallback to general note if no specific explanation exists
            explanation = item.get("note", item.get("llm_perf_note", "No specific explanation available."))
        
    print(f"\n### {item.get('label', args.term)} ({args.level.capitalize()})")
    print(f"\n{explanation}")

if __name__ == "__main__":
    main()
