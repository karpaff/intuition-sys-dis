"""Extract chapters from the two frozen EPUB editions and measure their composition."""

import csv
import hashlib
import json
import posixpath
import re
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "data/raw"
OUT = ROOT / "reports/eda"
BOOKS = json.loads((ROOT / "data/books.json").read_text())


def download(url, path):
    if not path.exists():
        request = urllib.request.Request(url, headers={"User-Agent": "LiteraryEDA/1.0"})
        with urllib.request.urlopen(request, timeout=60) as response:
            path.write_bytes(response.read())
    return path.read_bytes()


def local(tag):
    return tag.rsplit("}", 1)[-1]


def text_of(node):
    # Exclude footnote anchors; preserve their following punctuation and paragraph text.
    if local(node.tag) in {"script", "style", "sup"}:
        return ""
    if local(node.tag) == "a" and "note" in node.attrib.get("href", "").lower():
        return ""
    return (node.text or "") + "".join(text_of(c) + (c.tail or "") for c in node)


def extract(book):
    path = CACHE / f"{book}.epub"
    config = BOOKS[book]
    if not path.exists():
        if not config["download_url"]:
            raise FileNotFoundError(f"Place the EPUB from {config['source_page']} at {path}")
        download(config["download_url"], path)
    chapters, current, current_source, current_title = [], [], "", ""

    def flush():
        nonlocal current
        if current:
            chapters.append(
                {
                    "book": book,
                    "chapter_order": len(chapters) + 1,
                    "heading": current_title,
                    "epub_item": current_source,
                    "text": "\n\n".join(current),
                    "paragraphs": list(current),
                }
            )
            current = []

    with zipfile.ZipFile(path) as archive:
        if archive.read("mimetype").strip() != b"application/epub+zip":
            raise ValueError("Invalid EPUB mimetype")
        container = ET.fromstring(archive.read("META-INF/container.xml"))
        opf_path = next(
            n.attrib["full-path"] for n in container.iter() if local(n.tag) == "rootfile"
        )
        opf = ET.fromstring(archive.read(opf_path))
        base = posixpath.dirname(opf_path)
        items = {n.attrib["id"]: n.attrib for n in opf.iter() if local(n.tag) == "item"}
        spine = [items[n.attrib["idref"]] for n in opf.iter() if local(n.tag) == "itemref"]
        ncx = next(i for i in items.values() if i.get("media-type") == "application/x-dtbncx+xml")
        toc = ET.fromstring(archive.read(posixpath.join(base, ncx["href"])))
        toc_count = sum(local(n.tag) == "navPoint" for n in toc.iter())
        included, excluded = [], []
        for item in spine:
            filename = posixpath.normpath(posixpath.join(base, item["href"]))
            if any(s in filename.lower() for s in ["cover", "annotation", "notes"]):
                excluded.append(filename)
                continue
            included.append(filename)
            body = next(
                n for n in ET.fromstring(archive.read(filename)).iter() if local(n.tag) == "body"
            )
            for node in body.iter():
                tag = local(node.tag)
                if tag not in {"p", "h1", "h2", "h3", "blockquote"}:
                    continue
                if tag == "blockquote" and any(local(c.tag) == "p" for c in node.iter()):
                    continue
                text = re.sub(r"\s+", " ", text_of(node)).strip()
                if not text:
                    continue
                if re.fullmatch(r"[IVX]+", text):
                    flush()
                    current_title = text
                    current_source = filename
                elif tag.startswith("h") or node.attrib.get("class") == "header":
                    continue
                else:
                    if not current_title:
                        raise ValueError(f"Literary text before first chapter: {filename}")
                    current.append(text)
        flush()
    if len(chapters) != config["expected_chapters"]:
        raise ValueError(f"Unexpected chapter count: {book}: {len(chapters)}")
    metadata = {
        "book": book,
        **config,
        "sha256_epub": hashlib.sha256(path.read_bytes()).hexdigest(),
        "epub_bytes": path.stat().st_size,
        "ncx_entries_including_service": toc_count,
        "included_items": included,
        "excluded_items": excluded,
    }
    return chapters, metadata


def load_chapters(book):
    path = CACHE / f"{book}-chapters.json"
    if not path.exists():
        raise FileNotFoundError("Run scripts/eda.py first")
    return json.loads(path.read_text())


def main():
    CACHE.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    chapter_rows, sources, summary = [], [], {}
    for book in BOOKS:
        chapters, metadata = extract(book)
        (CACHE / f"{book}-chapters.json").write_text(
            json.dumps(chapters, ensure_ascii=False) + "\n"
        )
        rows = []
        all_paragraphs = []
        for chapter in chapters:
            text, ps = chapter["text"], chapter["paragraphs"]
            all_paragraphs.extend(ps)
            row = {k: chapter[k] for k in ["book", "chapter_order", "heading", "epub_item"]}
            row.update(
                {
                    "characters": len(text),
                    "paragraphs": len(ps),
                    "words": len(re.findall(r"[А-Яа-яЁё]+(?:-[А-Яа-яЁё]+)*", text)),
                    "replacement_characters": text.count("\ufffd"),
                    "paragraphs_over_4000_chars": sum(len(p) > 4000 for p in ps),
                    "sha256_text": hashlib.sha256(text.encode()).hexdigest(),
                }
            )
            rows.append(row)
        chapter_rows.extend(rows)
        sources.append(metadata)
        summary[book] = {
            "chapters": len(rows),
            **{
                key: sum(r[key] for r in rows)
                for key in [
                    "characters",
                    "paragraphs",
                    "words",
                    "replacement_characters",
                    "paragraphs_over_4000_chars",
                ]
            },
            "min_chapter_chars": min(r["characters"] for r in rows),
            "max_chapter_chars": max(r["characters"] for r in rows),
            "duplicate_paragraph_occurrences": sum(n - 1 for n in Counter(all_paragraphs).values()),
        }
    for name, data in [("chapters", chapter_rows), ("sources", sources), ("summary", summary)]:
        (OUT / f"{name}.json").write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    with (OUT / "chapters.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(chapter_rows[0]))
        writer.writeheader()
        writer.writerows(chapter_rows)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
