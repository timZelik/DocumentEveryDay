"""Seam for a future ranking or posting stage that runs on the chosen clips before they are produced.

Today it keeps the selection as-is. Auto-posting is deliberately out of scope: approval stays manual."""

from typing import Protocol

from documenteveryday.domain import ClipPlan


class PostSelectionStage(Protocol):
    def process(self, plans: list[ClipPlan]) -> list[ClipPlan]: ...


class KeepSelectionAsIs:
    def process(self, plans: list[ClipPlan]) -> list[ClipPlan]:
        return plans
