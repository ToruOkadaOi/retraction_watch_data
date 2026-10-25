"""Run the dashboard against a disposable real-CSV sample, without Aura access."""

import argparse
import csv
import os
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from knowledge_graph import KnowledgeGraphGenerator
import uvicorn


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--sample-rows", type=int, default=200)
    args = parser.parse_args()
    if not 1 <= args.sample_rows <= 1000:
        parser.error("Use between 1 and 1000 sample rows")
    with tempfile.TemporaryDirectory(prefix="rw-dashboard-preview-") as directory:
        path = Path(directory) / "sample.csv"
        with (ROOT / "retraction_watch.csv").open(
            encoding="utf-8-sig", newline=""
        ) as source, path.open("w", encoding="utf-8", newline="") as target:
            reader, writer = csv.reader(source), csv.writer(target)
            for index, row in enumerate(reader):
                writer.writerow(row)
                if index == args.sample_rows:
                    break
        generator = KnowledgeGraphGenerator(path, profile="aura")
        generator.parse_csv()
        snapshot = Path(directory) / "graph.json"
        generator.export_to_json(snapshot)
        os.environ.pop("NEO4J_PASSWORD", None)
        os.environ["GRAPH_JSON_PATH"] = str(snapshot)
        uvicorn.run("api:app", host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
