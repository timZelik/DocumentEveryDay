"""Splits the screen into one tile per clip, so twelve clips means twelve tiles of a puzzle.

The grid area is tried with every column count; the winner keeps tiles closest to the shape of phone
footage (portrait) while leaving no hole: the last row's tiles simply widen to fill it.
"""

import math
from dataclasses import dataclass

PHONE_FOOTAGE_ASPECT = 3 / 4  # width / height of portrait iPhone (9:16) and glasses (3:4) footage, roughly


@dataclass(frozen=True)
class Tile:
    x: int
    y: int
    width: int
    height: int


def even(value: float) -> int:
    """yuv420 video needs even sizes."""
    return max(2, int(value) // 2 * 2)


def tile_shape_penalty(tile_count: int, columns: int, width: int, height: int) -> float:
    rows = math.ceil(tile_count / columns)
    last_row_count = tile_count - (rows - 1) * columns
    full_aspect = (width / columns) / (height / rows)
    last_aspect = (width / last_row_count) / (height / rows)
    full_rows_share = (rows - 1) / rows
    return full_rows_share * abs(math.log(full_aspect / PHONE_FOOTAGE_ASPECT)) + (1 - full_rows_share) * abs(
        math.log(last_aspect / PHONE_FOOTAGE_ASPECT)
    )


def grid_tiles(tile_count: int, width: int, height: int, top: int = 0, gap: int = 6) -> list[Tile]:
    if tile_count <= 0:
        return []
    columns = min(range(1, tile_count + 1), key=lambda c: tile_shape_penalty(tile_count, c, width, height))
    rows = math.ceil(tile_count / columns)
    row_height = height / rows
    tiles = []
    for row in range(rows):
        in_row = min(columns, tile_count - row * columns)
        column_width = width / in_row
        for column in range(in_row):
            tiles.append(
                Tile(
                    x=even(column * column_width + gap / 2),
                    y=even(top + row * row_height + gap / 2),
                    width=even(column_width - gap),
                    height=even(row_height - gap),
                )
            )
    return tiles
