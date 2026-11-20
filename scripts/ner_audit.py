"""Offline Natasha PER audit: same extractor as Intuition, no frequency filter or LLM."""

import csv
import gzip
import hashlib
import importlib.metadata
import json
import re
from collections import Counter

import pymorphy3
from eda import ROOT, load_chapters
from natasha import Doc, NewsEmbedding, NewsNERTagger, Segmenter


def main():
    segmenter = Segmenter()
    embedding = NewsEmbedding()
    tagger = NewsNERTagger(embedding)
    morph = pymorphy3.MorphAnalyzer()
    out = ROOT / "reports/eda/ner"
    out.mkdir(parents=True, exist_ok=True)
    mentions, frequencies, manifest = [], [], []
    for book, count in [("ionych", 5), ("crime", 41)]:
        counter = Counter()
        first = {}
        for ch in load_chapters(book):
            chapter, text = ch["chapter_order"], ch["text"]
            doc = Doc(text)
            doc.segment(segmenter)
            doc.tag_ner(tagger)
            manifest.append(
                {
                    "book_id": book,
                    "chapter_order": chapter,
                    "sha256_text": hashlib.sha256(text.encode()).hexdigest(),
                }
            )
            for span in doc.spans:
                if span.type != "PER" or len(span.text.strip()) < 2:
                    continue
                assert text[span.start : span.stop] == span.text
                # Morphology supplies comparison keys, not character identity decisions.
                key = " ".join(
                    morph.parse(t)[0].normal_form for t in re.findall(r"[\w-]+", span.text)
                )
                key = key.lower().replace("ё", "е")
                row = {
                    "book_id": book,
                    "chapter_order": chapter,
                    "start": span.start,
                    "end": span.stop,
                    "surface": span.text,
                    "comparison_key": key,
                    "context": text[max(0, span.start - 100) : min(len(text), span.stop + 100)],
                }
                mentions.append(row)
                counter[key] += 1
                first.setdefault(key, row)
            print(
                f"{book} chapter {chapter}/{count}: {sum(s.type == 'PER' for s in doc.spans)} PER",
                flush=True,
            )
        for key, count in counter.most_common():
            frequencies.append(
                {
                    "book_id": book,
                    "comparison_key": key,
                    "count": count,
                    "example_surface": first[key]["surface"],
                    "first_chapter": first[key]["chapter_order"],
                    "example_context": first[key]["context"],
                }
            )
    for name, rows in [("mentions", mentions), ("candidates", frequencies)]:
        path = out / (f"{name}.csv.gz" if name == "mentions" else f"{name}.csv")
        opener = gzip.open if name == "mentions" else open
        with opener(path, "wt", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    metadata = {
        "natasha": importlib.metadata.version("natasha"),
        "pymorphy3": importlib.metadata.version("pymorphy3"),
        "model": "NewsEmbedding + NewsNERTagger (Natasha bundled)",
        "production_reference_commit": "2d3ee3d4f1e8e86dc4c0bb09addf2449a5b8efdc",
        "production_parity": "PER extraction only; no count>=2 filter or LLM alias merge",
        "chapters": manifest,
    }
    (out / "run.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
