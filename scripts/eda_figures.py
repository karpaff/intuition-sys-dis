"""Generate the four EDA figures from measured EPUB-backed artifacts."""

import csv
import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from eda import OUT, ROOT
from matplotlib.ticker import FuncFormatter

FIG = OUT / "figures"
NAMES = {"ionych": "Ионыч", "crime": "Преступление и наказание"}
BLUE, ORANGE, RED, GREEN, GRAY = "#33658a", "#e09f3e", "#b74f4f", "#4c956c", "#96999c"


def save(fig, name):
    fig.savefig(FIG / f"{name}.png", dpi=170, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def style(ax):
    ax.spines[["top", "right"]].set_visible(False)
    ax.set_axisbelow(True)


def main():
    FIG.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 11,
            "axes.titleweight": "bold",
            "axes.labelcolor": "#333333",
        }
    )
    chapters = json.loads((OUT / "chapters.json").read_text())
    fig, axes = plt.subplots(1, 2, figsize=(13.5, 4.7), constrained_layout=True)
    for ax, (book, name) in zip(axes, NAMES.items(), strict=True):
        rows = [r for r in chapters if r["book"] == book]
        ax.bar([r["chapter_order"] for r in rows], [r["characters"] for r in rows], color=BLUE)
        ax.set(title=name, xlabel="Глава по сквозному порядку", ylabel="Символов очищенного текста")
        ax.yaxis.set_major_formatter(FuncFormatter(lambda x, _: f"{x / 1000:g} тыс."))
        ax.set_xticks(range(1, len(rows) + 1, 1 if book == "ionych" else 5))
        ax.grid(axis="y", alpha=0.2)
        style(ax)
    fig.suptitle("Длина каждой главы в выбранных EPUB", fontsize=15, fontweight="bold")
    save(fig, "chapter_lengths")

    audit = json.loads((OUT / "profile_verification.json").read_text())["quotes"]
    statuses = [
        ("unique", "Единственное совпадение", BLUE),
        ("ambiguous", "Несколько совпадений", ORANGE),
        ("too_short", "Короткая цитата", GRAY),
        ("multiple_quotes_in_block", "Составной блок", "#9375a3"),
        ("unmatched", "Не сопоставлено", RED),
    ]
    fig, ax = plt.subplots(figsize=(12.5, 4.5), constrained_layout=True)
    left = np.zeros(2)
    for status, label, color in statuses:
        counts = [
            sum(r["book_id"] == book and r["status"] == status for r in audit) for book in NAMES
        ]
        totals = [sum(r["book_id"] == book for r in audit) for book in NAMES]
        widths = np.array(counts) / totals * 100
        ax.barh(list(NAMES.values()), widths, left=left, color=color, label=label)
        for y, (count, width) in enumerate(zip(counts, widths, strict=True)):
            if width >= 6:
                ax.text(left[y] + width / 2, y, str(count), ha="center", va="center", color="white")
        left += widths
    ax.set(
        xlim=(0, 100), xlabel="Доля цитатных блоков, %", title="Сопоставление цитат с текстами EPUB"
    )
    ax.invert_yaxis()
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.22), ncol=3, frameon=False, fontsize=10)
    style(ax)
    save(fig, "quote_quality")

    profiles = list(csv.DictReader((ROOT / "data/characters/profiles.csv").open()))
    fig, axes = plt.subplots(
        1, 2, figsize=(15, 12), constrained_layout=True, gridspec_kw={"width_ratios": [1, 1.35]}
    )
    for ax, (book, name) in zip(axes, NAMES.items(), strict=True):
        rows = [r for r in profiles if r["book_id"] == book and r["entity_type"] == "person"]
        labels = [
            r["character"]
            .replace("Старцев, Дмитрий Ионыч", "Дмитрий Ионыч Старцев")
            .replace("Екатерина Ивановна Туркина (Котик)", "Екатерина Ивановна (Котик)")
            for r in rows
        ]
        values = [int(r["quote_blocks_for_character"]) for r in rows]
        colors = [
            GRAY if r["profile_scope"] == "shared_family" else BLUE if v else RED
            for r, v in zip(rows, values, strict=True)
        ]
        ax.barh(labels, values, color=colors)
        for i, (r, v) in enumerate(zip(rows, values, strict=True)):
            label = (
                f"{v} (раздел)"
                if r["profile_scope"] == "shared_family"
                else str(v)
                if v
                else "не найдено"
            )
            ax.text(v + 0.8, i, label, va="center", fontsize=9)
        ax.invert_yaxis()
        ax.set(
            title=name,
            xlabel="Блоков в статье или персональном разделе",
            xlim=(0, max(values) * 1.38),
        )
        ax.grid(axis="x", alpha=0.18)
        style(ax)
    fig.suptitle(
        "Покрытие исходного списка цитатными характеристиками", fontsize=16, fontweight="bold"
    )
    save(fig, "profile_coverage")

    summary = json.loads((OUT / "ner/comparison_summary.json").read_text())
    fig, ax = plt.subplots(figsize=(12, 4.8), constrained_layout=True)
    labels = list(NAMES.values())
    original = [summary[b]["reference_persons"] for b in NAMES]
    additions = [summary[b]["confirmed_additions_excluding_dream"] for b in NAMES]
    dreams = [summary[b]["additional_dream_characters"] for b in NAMES]
    ax.barh(labels, original, label="Исходный список сайта", color=BLUE)
    ax.barh(labels, additions, left=original, label="Подтверждённые дополнения", color=ORANGE)
    ax.barh(
        labels,
        dreams,
        left=np.array(original) + additions,
        label="Дополнительный персонаж сна",
        color="#9375a3",
    )
    for y, (a, b, c) in enumerate(zip(original, additions, dreams, strict=True)):
        ax.text(a / 2, y, str(a), ha="center", va="center", color="white")
        if b > 2:
            ax.text(a + b / 2, y, str(b), ha="center", va="center", color="#222222")
        ax.text(a + b + c + 0.8, y, f"≥ {a + b + c}", va="center", fontweight="bold")
    ax.set(
        xlim=(0, 51),
        xlabel="Подтверждённые лица, нижняя оценка",
        title="Проверка полноты списков: сайты + NER и просмотр контекстов",
    )
    ax.invert_yaxis()
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.22), ncol=2, frameon=False, fontsize=10)
    style(ax)
    save(fig, "list_completeness")


if __name__ == "__main__":
    main()
