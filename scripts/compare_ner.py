"""Reproduce a context-reviewed comparison, without automatic alias merging."""

import csv
import gzip
import json
from collections import Counter

from eda import ROOT

# Comparison keys are mechanical lemmas, not canonical character names.
EXISTING = {
    "ionych": [
        "старцев",
        "екатерина иванович",
        "иван петрович",
        "вера иосифович",
        "пантелеймон",
        "завловский",
        "пава",
        "иван",
    ],
    "crime": [
        "раскольников",
        "алена иванович",
        "мармеладов",
        "соня",
        "пульхерия александрович",
        "дуня",
        "катерина иванович",
        "лужин",
        "разумихин",
        "свидригайлов",
        "марфа петрович",
        "лебезятников",
        "лизавета",
        "зосимов",
        "заметов",
        "никодим фомич",
        "порфирий петрович",
        "илья петрович",
        "амалия иванович",
        "прасковья павлович",
        "наталья егорович",
        "вахрушин",
        "лавиза иванович",
        "дарья францовен",
        "ресслихо",
        "настасья",
        "миколай",
        "мещанин",
    ],
}
ADDITIONS = {
    "ionych": [("Деметти", "деметти", "mentioned_person", "Умершая певица; памятник на кладбище")],
    "crime": [
        ("Поленька / Полечка", "полечка", "story_character", "Дочь Катерины Ивановны"),
        ("Коля", "коля", "story_character", "Сын Катерины Ивановны"),
        ("Лидочка / Леня", "лидочка", "story_character", "Младшая дочь Катерины Ивановны"),
        ("Капернаумов", "капернаумов", "story_character", "Портной; Соня снимает у него комнату"),
        ("Кох", "кох", "story_character", "Посетитель квартиры старухи"),
        ("Пестряков", "пестряков", "story_character", "Студент, посетитель квартиры старухи"),
        (
            "Душкин",
            "душкина",
            "story_character",
            "Содержатель распивочной, приносит футляр с серьгами",
        ),
        ("Чебаров", "чебаров", "story_character", "Надворный советник, которому передан вексель"),
        ("Афросиньюшка", "афросиньюшка", "story_character", "Женщина в сцене у моста"),
        ("Митька / Дмитрий", "митька", "story_character", "Маляр, напарник Николая"),
        ("Бакалеев", "бакалеев", "mentioned_person", "Владелец дома с номерами"),
        ("Юшин", "юшина", "mentioned_person", "Купец, содержит номера в доме Бакалеева"),
        (
            "Филипп / Филька",
            "филипп",
            "mentioned_person",
            "Дворовый человек в рассказе о Свидригайлове",
        ),
        ("Катя", "катя", "story_character", "Девушка в сцене со Свидригайловым"),
        (
            "Нил Павлыч",
            "нил павлович",
            "story_character",
            "Служащий, к которому обращается Илья Петрович",
        ),
        ("Федосья", "федосья", "mentioned_person", "Упомянута в рассказе о невесте Свидригайлова"),
        ("Миколка из сна", "миколка", "dream_character", "В сне о лошади; не маляр Николай"),
    ],
}


def main():
    out = ROOT / "reports/eda/ner"
    with gzip.open(out / "mentions.csv.gz", "rt", encoding="utf-8") as stream:
        mentions = list(csv.DictReader(stream))
    candidates = list(csv.DictReader((out / "candidates.csv").open()))
    evidence, summary = [], {}
    for book, keys in EXISTING.items():
        refs = list(csv.DictReader((ROOT / f"data/characters/{book}.csv").open()))
        refs = [r for r in refs if r["entity_type"] == "person"]
        assert len(refs) == len(keys)
        selections = [
            (r["source_label"], key, "in_source_list", "")
            for r, key in zip(refs, keys, strict=True)
        ] + ADDITIONS[book]
        for name, key, category, note in selections:
            matches = [m for m in mentions if m["book_id"] == book and m["comparison_key"] == key]
            # Disambiguate the dream character by chapter, not by spelling.
            if category == "dream_character":
                matches = [m for m in matches if m["chapter_order"] == "5"]
            assert matches, (book, name, key)
            m = matches[0]
            evidence.append(
                {
                    "book_id": book,
                    "character": name,
                    "category": category,
                    "comparison_key": key,
                    "surface": m["surface"],
                    "chapter_order": m["chapter_order"],
                    "start": m["start"],
                    "end": m["end"],
                    "context": m["context"],
                    "note": note,
                    "review": "assistant_context_review_not_human_gold",
                }
            )
        raw_counts = Counter(m["surface"] for m in mentions if m["book_id"] == book)
        summary[book] = {
            "mentions": sum(m["book_id"] == book for m in mentions),
            "comparison_keys": sum(r["book_id"] == book for r in candidates),
            "reference_persons_found": len(keys),
            "reference_persons": len(refs),
            "single_occurrence_surface_forms": sum(v == 1 for v in raw_counts.values()),
            "confirmed_additions_excluding_dream": sum(
                cat != "dream_character" for _, _, cat, _ in ADDITIONS[book]
            ),
            "additional_dream_characters": sum(
                cat == "dream_character" for _, _, cat, _ in ADDITIONS[book]
            ),
        }
    with (out / "comparison_review.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(evidence[0]))
        writer.writeheader()
        writer.writerows(evidence)
    (out / "comparison_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
