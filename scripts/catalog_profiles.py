"""Inventory character profile URLs and quote blocks; no editorial prose is published."""

import csv
import hashlib
import json
import re
from concurrent.futures import ThreadPoolExecutor

from collect_characters import clean
from eda import CACHE, ROOT, download
from quote_utils import Quotes

BASE = "https://www.literaturus.ru/2016/12/"
IONYCH = {
    1: (BASE + "dmitrij-ionych-starcev-obraz-harakteristika-jetapy-zhizni.html", "individual"),
    2: (BASE + "semja-turkinyh-obraz-harakteristika-ionych.html", "family"),
    3: (BASE + "ekaterina-ivanovna-ionych-chehov-obraz-harakteristika.html", "individual"),
    4: (BASE + "semja-turkinyh-obraz-harakteristika-ionych.html", "shared_family"),
    5: (BASE + "semja-turkinyh-obraz-harakteristika-ionych.html", "shared_family"),
}


def read_rows(book):
    with (ROOT / f"data/characters/{book}.csv").open(encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def crime_links():
    source = (CACHE / "crime-characters.html").read_text(encoding="utf-8")
    table = re.search(r'<table[^>]*class="MsoNormalTable".*?</table>', source, re.S)[0]
    result = {}
    for row in re.findall(r"<tr\b[^>]*>(.*?)</tr>", table, re.S)[1:]:
        heading = re.search(r"<b>(.*?)</b>", row, re.S)
        if heading:
            links = re.findall(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', row, re.S)
            candidates = [url for url, label in links if "Подробнее" in clean(label)]
            if len(candidates) != 1:
                raise ValueError(f"Missing/ambiguous profile link: {clean(heading[1])}")
            result[clean(heading[1])] = candidates[0]
    return result


def inspect(url):
    cache = CACHE / ("profile-" + hashlib.sha256(url.encode()).hexdigest()[:16] + ".html")
    raw = download(url, cache)
    source = raw.decode("utf-8")
    # Restrict to article content, excluding comments and related-site widgets.
    article = re.search(r"<div[^>]+class=[\'\"][^\'\"]*post-body[^\'\"]*[\'\"][^>]*>", source)
    if not article:
        raise ValueError(f"Article content missing: {url}")
    body = source[article.end() :].split("<!-- AddThis", 1)[0]
    body = re.split(r"<div[^>]+class=[\'\"](?:post-footer|comments)", body)[0]
    parser = Quotes()
    parser.feed(body)
    title = re.search(r"<title>(.*?)</title>", source, re.S)
    return {
        "url": url,
        "title": clean(title[1]) if title else "",
        "sha256_raw": hashlib.sha256(raw).hexdigest(),
        "cache_file": cache.name,
        "quote_blocks": len(parser.items),
        "checked_date": "2026-11-01",
    }


def main():
    mapping = crime_links()
    # The list links to Luzhin's hub; follow its verified quote-profile article.
    mapping["Лужин"] = (
        "https://www.literaturus.ru/2020/07/"
        "luzhin-harakteristika-obraz-prestuplenie-i-nakazanie-opisanie-vneshnost-harakter.html"
    )
    rows = []
    for book in ("ionych", "crime"):
        for row in read_rows(book):
            index = int(row["source_index"])
            url, scope = (
                (mapping[row["source_label"]], "individual")
                if book == "crime"
                else (IONYCH.get(index, ("", "brief_only")))
            )
            rows.append(
                {
                    "book_id": book,
                    "source_index": index,
                    "character": row["source_label"],
                    "entity_type": row["entity_type"],
                    "profile_url": url,
                    "profile_scope": scope,
                    "brief_source_url": row["source_url"],
                }
            )
    urls = sorted({row["profile_url"] for row in rows if row["profile_url"]})
    with ThreadPoolExecutor(max_workers=4) as pool:
        pages = list(pool.map(inspect, urls))
    by_url = {page["url"]: page for page in pages}
    for row in rows:
        page = by_url.get(row["profile_url"])
        row["quote_blocks_on_page"] = page["quote_blocks"] if page else 0
        row["quote_blocks_for_character"] = row["quote_blocks_on_page"]
        if page and row["profile_scope"] == "shared_family":
            source = (CACHE / page["cache_file"]).read_text()
            father = re.search(r"<b>Отец</b>", source).start()
            mother = re.search(r"<b>Мать(?:&nbsp;)?\s*</b>", source).start()
            daughter = re.search(r"<b>Дочь</b>", source).start()
            section = source[father:mother] if row["source_index"] == 4 else source[mother:daughter]
            parser = Quotes()
            parser.feed(section)
            row["quote_blocks_for_character"] = len(parser.items)
        row["status"] = (
            "quote_profile_found"
            if page and page["quote_blocks"]
            else "profile_without_blockquotes"
            if page
            else "quote_profile_not_found"
        )
        row["review_status"] = "not_checked_against_book"
    out = ROOT / "data/characters"
    with (out / "profiles.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    (out / "profile_sources.json").write_text(
        json.dumps(pages, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "pages": len(pages),
                "quote_blocks": sum(p["quote_blocks"] for p in pages),
                "pages_without_quotes": [p["url"] for p in pages if not p["quote_blocks"]],
            },
            ensure_ascii=False,
        )
    )
    for row in rows:
        print(row["book_id"], row["character"], row["profile_scope"], row["quote_blocks_on_page"])


if __name__ == "__main__":
    main()
