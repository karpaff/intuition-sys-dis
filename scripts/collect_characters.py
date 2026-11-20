"""Collect source labels only; these are candidate lists, not reviewed gold."""

import csv
import hashlib
import html
import json
import re

from eda import CACHE, ROOT, download

SOURCES = {
    "ionych": "https://www.sdamna5.ru/ionych_harakteristiki",
    "crime": (
        "https://www.literaturus.ru/2020/07/"
        "geroi-prestuplenie-i-nakazanie-opisanie-personazhi-spisok-tablica.html"
    ),
}


def clean(fragment):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]*>", "", fragment))).strip()


def labels(book, source):
    if book == "ionych":
        section = source.split("<h2>", 1)[1].split("Смотрите также:", 1)[0]
        return [clean(s) for s in re.findall(r"<strong>(.*?)</strong>", section, re.S)]
    table = re.search(r'<table[^>]*class="MsoNormalTable".*?</table>', source, re.S)
    if not table:
        raise ValueError("Character table missing")
    rows = re.findall(r"<tr\b[^>]*>(.*?)</tr>", table[0], re.S)
    names = []
    for row in rows[1:]:
        heading = re.search(r"<b>(.*?)</b>", row, re.S)
        if heading:
            names.append(clean(heading[1]))
        elif 'class="adsbygoogle"' not in row:
            raise ValueError("Unexpected row without character name")
    return names


def main():
    CACHE.mkdir(parents=True, exist_ok=True)
    out = ROOT / "data/characters"
    out.mkdir(parents=True, exist_ok=True)
    manifest = []
    for book, url in SOURCES.items():
        raw = download(url, CACHE / f"{book}-characters.html")
        names = labels(book, raw.decode("utf-8"))
        if not names or any(not n for n in names) or len(names) != len(set(names)):
            raise ValueError(f"Empty or duplicate source labels: {book}")
        records = []
        for index, label in enumerate(names, 1):
            name, aliases = label, ""
            # Only the alias explicitly present in the source label is split off.
            if "(" in label and label.endswith(")"):
                name, aliases = label[:-1].split(" (", 1)
            records.append(
                {
                    "book_id": book,
                    "source_index": index,
                    "source_label": label,
                    "name": name,
                    "aliases": aliases,
                    "entity_type": "group" if label == "Семья Туркиных" else "person",
                    "review_status": "not_checked_against_book",
                    "source_url": url,
                }
            )
        with (out / f"{book}.csv").open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(records[0]))
            writer.writeheader()
            writer.writerows(records)
        manifest.append(
            {
                "book_id": book,
                "source_url": url,
                "accessed_date": "2026-11-01",
                "sha256_raw": hashlib.sha256(raw).hexdigest(),
                "records": len(records),
                "persons": sum(r["entity_type"] == "person" for r in records),
                "groups": sum(r["entity_type"] == "group" for r in records),
            }
        )
        print(book, len(records), "records:", ", ".join(names))
    (out / "sources.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
