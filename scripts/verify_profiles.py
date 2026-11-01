"""Verify quote-block text against frozen book chapters; no semantic claim validation."""

import csv
import hashlib
import json
import re
from collections import Counter

from eda import CACHE, ROOT, load_chapters
from quote_utils import Quotes, normalize

OUT = ROOT / "reports/eda"


def quote_body(block):
    # Remove explicit source annotations even when the opening quote is missing.
    pattern = r"\([^()]*?(?:глав[аеы]|эпилог)[^()]*\)"
    annotations = re.findall(pattern, block, re.I)
    body = re.sub(pattern, "", block, flags=re.I).strip(' \n\t"«».,')
    # Editorial gloss outside a fully enclosed quotation, e.g. Starcev block 3.
    match = re.fullmatch(r'\s*["«](.*)["»]\s*(\(.*\))[.,]?\s*', block, re.S)
    if match and not annotations:
        return match[1], match[2]
    enclosed = re.fullmatch(r'\s*["«](.*)["»]\s*[.,]?\s*(\([^()]*\))?[.,]?\s*', block, re.S)
    if enclosed:
        body = re.sub(pattern, "", enclosed[1], flags=re.I)
        if enclosed[2] and enclosed[2] not in annotations:
            annotations.append(enclosed[2])
    return body, " ".join(annotations)


def find(quote, chapters):
    segments = [normalize(s)[0] for s in re.split(r"\.{3,}|…|<…>|\[\.\.\.\]", quote)]
    segments = [s for s in segments if s]
    if not segments or len(segments[0]) < 8 or sum(map(len, segments)) < 20:
        return "too_short", []
    candidates = []
    for chapter, text, offsets in chapters:
        for match in re.finditer(re.escape(segments[0]), text):
            start, end = match.span()
            for segment in segments[1:]:
                pos = text.find(segment, end)
                if pos < 0:
                    break
                end = pos + len(segment)
            else:
                if end - start <= sum(map(len, segments)) + 500:
                    candidates.append(
                        {
                            "chapter_order": chapter,
                            "start": offsets[start],
                            "end": offsets[end - 1] + 1,
                        }
                    )
    return (
        "unique" if len(candidates) == 1 else "ambiguous" if candidates else "unmatched",
        candidates,
    )


def stated_chapter(annotation):
    m = re.search(r"част[ьи]\s*(\d)\s*[,;]?\s*глав[аеы]\s*([IVX]+|\d+)", annotation, re.I)
    if not m:
        return None
    part = int(m[1])
    romans = {"I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6, "VII": 7, "VIII": 8}
    number = int(m[2]) if m[2].isdigit() else romans.get(m[2].upper())
    sizes = [7, 7, 6, 6, 5, 8]
    if number is None or not 1 <= part <= 6 or not 1 <= number <= sizes[part - 1]:
        return None
    return sum(sizes[: part - 1]) + number


def main():
    manifests = json.loads((ROOT / "data/characters/profile_sources.json").read_text())
    profiles = list(csv.DictReader((ROOT / "data/characters/profiles.csv").open()))
    books = {}
    book_manifest = json.loads((OUT / "chapters.json").read_text())
    for book in ("ionych", "crime"):
        chapters = []
        for ch in load_chapters(book):
            chapter, text = ch["chapter_order"], ch["text"]
            expected = next(
                r for r in book_manifest if r["book"] == book and r["chapter_order"] == chapter
            )
            if hashlib.sha256(text.encode()).hexdigest() != expected["sha256_text"]:
                raise ValueError("Book text differs from EDA snapshot")
            normalized, offsets = normalize(text)
            chapters.append((chapter, normalized, offsets))
        books[book] = chapters
    results, failures = [], []
    for page in manifests:
        linked = [p for p in profiles if p["profile_url"] == page["url"]]
        book = linked[0]["book_id"]
        raw = (CACHE / page["cache_file"]).read_bytes()
        if hashlib.sha256(raw).hexdigest() != page["sha256_raw"]:
            raise ValueError("Profile HTML differs from catalog snapshot")
        parser = Quotes()
        parser.feed(raw.decode())
        if len(parser.items) != page["quote_blocks"]:
            raise ValueError("Quote count differs from catalog")
        for index, block in enumerate(parser.items, 1):
            body, annotation = quote_body(block)
            strict_status, strict = find(block, books[book])
            status, candidates = find(body, books[book])
            if len(re.findall(r"\([^()]*?(?:глав[аеы]|эпилог)[^()]*\)", block, re.I)) > 1:
                status, candidates = "multiple_quotes_in_block", []
            claimed = stated_chapter(annotation) if book == "crime" else None
            row = {
                "book_id": book,
                "profile_url": page["url"],
                "quote_index": index,
                "quote_sha256": hashlib.sha256(block.encode()).hexdigest(),
                "status": status,
                "raw_block_status": strict_status,
                "annotation_removed": bool(annotation),
                "stated_chapter_order": claimed,
                "stated_chapter_conflict": bool(
                    claimed and len(candidates) == 1 and candidates[0]["chapter_order"] != claimed
                ),
                "candidates": candidates,
            }
            results.append(row)
            if status != "unique" or row["stated_chapter_conflict"]:
                failures.append({**row, "block_for_local_review": block})
    report = {
        book: dict(Counter(r["status"] for r in results if r["book_id"] == book)) for book in books
    }
    report["annotation_removed"] = sum(r["annotation_removed"] for r in results)
    report["stated_chapter_conflicts"] = sum(r["stated_chapter_conflict"] for r in results)
    (OUT / "profile_verification.json").write_text(
        json.dumps(
            {"summary": report, "semantic_claims_reviewed": False, "quotes": results},
            ensure_ascii=False,
            separators=(",", ":"),
        )
        + "\n"
    )
    private = ROOT.parent / "profile_review_local.json"
    private.write_text(json.dumps(failures, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
