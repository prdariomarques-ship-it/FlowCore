"""Catalog and search helpers for the historical theology experience."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


_CATALOG_PATH = Path(__file__).resolve().parent.parent / "data" / "theology_catalog.json"


@dataclass(frozen=True)
class Theologian:
    slug: str
    name: str
    dates: str
    period_id: str
    tradition: str
    summary: str
    prompt: str
    period_title: str
    period_era: str

    def to_dict(self) -> dict[str, str]:
        return {
            "slug": self.slug,
            "name": self.name,
            "dates": self.dates,
            "period_id": self.period_id,
            "tradition": self.tradition,
            "summary": self.summary,
            "prompt": self.prompt,
            "period_title": self.period_title,
            "period_era": self.period_era,
        }


@dataclass(frozen=True)
class ChurchPeriod:
    id: str
    title: str
    era: str
    description: str
    accent: str
    theologians: tuple[Theologian, ...]

    def to_dict(self, include_prompts: bool = True) -> dict:
        data = {
            "id": self.id,
            "title": self.title,
            "era": self.era,
            "description": self.description,
            "accent": self.accent,
            "theologians": [],
        }
        for theologian in self.theologians:
            item = theologian.to_dict()
            if not include_prompts:
                item.pop("prompt", None)
            data["theologians"].append(item)
        return data


def _load_catalog() -> tuple[ChurchPeriod, ...]:
    if not _CATALOG_PATH.exists():
        raise FileNotFoundError(f"Theology catalog not found: {_CATALOG_PATH}")
    payload = json.loads(_CATALOG_PATH.read_text(encoding="utf-8"))
    periods: list[ChurchPeriod] = []
    for raw_period in payload.get("periods", []):
        period_id = str(raw_period["id"])
        title = str(raw_period["title"])
        theologians = tuple(
            Theologian(
                slug=str(raw_theologian["slug"]),
                name=str(raw_theologian["name"]),
                dates=str(raw_theologian["dates"]),
                period_id=str(raw_theologian.get("periodId", period_id)),
                tradition=str(raw_theologian["tradition"]),
                summary=str(raw_theologian["summary"]),
                prompt=str(raw_theologian["prompt"]),
                period_title=title,
                period_era=str(raw_period["era"]),
            )
            for raw_theologian in raw_period.get("theologians", [])
        )
        periods.append(
            ChurchPeriod(
                id=period_id,
                title=title,
                era=str(raw_period["era"]),
                description=str(raw_period["description"]),
                accent=str(raw_period["accent"]),
                theologians=theologians,
            )
        )
    return tuple(periods)


@lru_cache(maxsize=1)
def get_periods() -> tuple[ChurchPeriod, ...]:
    return _load_catalog()


def get_all_theologians() -> tuple[Theologian, ...]:
    return tuple(theologian for period in get_periods() for theologian in period.theologians)


def get_theologian(slug: str) -> Theologian | None:
    return next((theologian for theologian in get_all_theologians() if theologian.slug == slug), None)


def search_catalog(query: str, limit: int = 30) -> list[dict]:
    normalized = " ".join(query.casefold().split())
    if not normalized:
        return [period.to_dict(include_prompts=False) for period in get_periods()[:limit]]

    terms = normalized.split()
    results: list[tuple[int, Theologian]] = []
    for theologian in get_all_theologians():
        haystack = " ".join(
            [
                theologian.name,
                theologian.dates,
                theologian.tradition,
                theologian.summary,
                theologian.period_title,
                theologian.period_era,
            ]
        ).casefold()
        if not all(term in haystack for term in terms):
            continue
        score = sum(haystack.count(term) for term in terms)
        if theologian.name.casefold().startswith(normalized):
            score += 10
        results.append((score, theologian))

    results.sort(key=lambda item: (-item[0], item[1].name))
    return [theologian.to_dict() | {"prompt": None} for _, theologian in results[:limit]]
