"""Public literary corpus EDA; Python 3.11+, standard library only."""

import hashlib
import html
import json
import re
import urllib.request
from collections import Counter
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "data/raw"
OUT = ROOT / "reports/eda"
BOOKS = {
    "ionych": (437, 5, ["Старцев", "Дмитрий Ионыч", "Ионыч", "Котик", "Екатерина Ивановна"]),
    "crime": (69, 41, ["Раскольников", "Родион", "Родя", "Соня", "Софья Семеновна"]),
}


def download(url, path):
    if not path.exists():
        request = urllib.request.Request(url, headers={"User-Agent": "LiteraryEDA/1.0"})
        with urllib.request.urlopen(request, timeout=60) as response:
            path.write_bytes(response.read())
    return path.read_bytes()


class LiteraryParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.depth = 0
        self.blocks = []
        self.current = []

    def handle_starttag(self, tag, attrs):
        if tag == "z":
            self.depth += 1

    def handle_endtag(self, tag):
        if tag == "z":
            self.depth -= 1
            if self.depth == 0:
                text = re.sub(r"\s+", " ", "".join(self.current)).strip()
                if text:
                    self.blocks.append(text)
                self.current = []

    def handle_data(self, data):
        if self.depth:
            self.current.append(data)


def paragraphs(raw):
    source = raw.decode("cp1251", errors="strict")
    source = source.split('<div class="fns">')[0]
    source = re.sub(r"<(script|fn)\b[^>]*>.*?</\1>", "", source, flags=re.S | re.I)
    parser = LiteraryParser()
    parser.feed(source)
    if not parser.blocks or parser.depth:
        raise ValueError("Source layout changed: missing/unbalanced literary paragraphs")
    return parser.blocks


def svg(rows, title, path):
    maximum = max(value for _, value in rows) or 1
    height = 75 + len(rows) * 28
    elements = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="900" height="{height}" '
        f'viewBox="0 0 900 {height}">',
        '<rect width="100%" height="100%" fill="white"/>',
        '<g font-family="sans-serif" font-size="13" fill="#17324d">',
        f'<text x="20" y="25">{html.escape(title)}</text>',
    ]
    for i, (label, value) in enumerate(rows):
        y = 50 + i * 28
        width = value / maximum * 500
        elements.extend(
            [
                f'<text x="12" y="{y + 14}">{html.escape(label)}</text>',
                f'<rect x="300" y="{y}" width="{width:.2f}" height="19" fill="#42858c"/>',
                f'<text x="{310 + width:.2f}" y="{y + 14}">{value}</text>',
            ]
        )
    path.write_text("\n".join(elements + ["</g></svg>\n"]), encoding="utf-8")


def main():
    CACHE.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    manifest, summary, lengths, aliases = [], {}, [], []
    for book, (source_id, expected, names) in BOOKS.items():
        index_url = f"https://ilibrary.ru/text/{source_id}/index.html"
        index_raw = download(index_url, CACHE / f"{book}-index.html")
        links = sorted(
            {
                int(n)
                for n in re.findall(
                    rf"/text/{source_id}/p\.(\d+)/index.html", index_raw.decode("cp1251")
                )
            }
        )
        if links != list(range(1, expected + 1)):
            raise ValueError(f"Unexpected table of contents: {book}: {links}")
        chapters, all_paragraphs = [], []
        for number in links:
            url = f"https://ilibrary.ru/text/{source_id}/p.{number}/index.html"
            raw = download(url, CACHE / f"{book}-{number:02}.html")
            ps = paragraphs(raw)
            text = "\n\n".join(ps)
            row = {
                "book": book,
                "chapter_order": number,
                "url": url,
                "sha256_raw": hashlib.sha256(raw).hexdigest(),
                "sha256_text": hashlib.sha256(text.encode()).hexdigest(),
                "characters": len(text),
                "paragraphs": len(ps),
                "words": len(re.findall(r"[А-Яа-яЁё]+(?:-[А-Яа-яЁё]+)*", text)),
                "replacement_characters": text.count("\ufffd"),
                "paragraphs_over_4000_chars": sum(len(p) > 4000 for p in ps),
                "dialogue_paragraphs": sum(p.startswith(("—", "–", "\x97")) for p in ps),
            }
            chapters.append(row)
            all_paragraphs.extend(ps)
            lengths.append((f"{book} {number}", len(text)))
        full = "\n\n".join(all_paragraphs)
        counts = {
            name: len(re.findall(r"(?<!\w)" + re.escape(name) + r"(?!\w)", full, re.I))
            for name in names
        }
        aliases.extend((f"{book}: {name}", count) for name, count in counts.items())
        ps_counts = Counter(all_paragraphs)
        summary[book] = {
            "chapters": len(chapters),
            **{
                key: sum(c[key] for c in chapters)
                for key in [
                    "characters",
                    "words",
                    "paragraphs",
                    "replacement_characters",
                    "paragraphs_over_4000_chars",
                    "dialogue_paragraphs",
                ]
            },
            "duplicate_paragraph_occurrences": sum(n - 1 for n in ps_counts.values()),
            "min_chapter_chars": min(c["characters"] for c in chapters),
            "max_chapter_chars": max(c["characters"] for c in chapters),
            "exact_surface_counts_not_entities": counts,
            "gold_characters": 0,
            "gold_relations": 0,
            "gold_questions": 0,
        }
        manifest.extend(chapters)
    (OUT / "chapters.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (OUT / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    provenance = {
        "retrieved_at_utc": datetime.now(UTC).isoformat(),
        "note": "Timestamp of analysis; existing local cache may be older.",
    }
    (OUT / "run.json").write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")
    svg(lengths, "Chapter length (Unicode characters)", OUT / "chapter_lengths.svg")
    svg(aliases, "Exact surface forms (not entity counts)", OUT / "aliases.svg")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
