# Copyright 2023-2026 Youssef Assis. Licensed under the Apache License, Version 2.0.
"""The spheres written out as a table."""

import csv

import pytest
from SphereAnnotationLib import export


class TestSphereRows:
    def test_a_pair_is_one_row(self):
        rows = export.sphere_rows([("aneurysm", [(0, 0, 0), (10, 0, 0)])])

        assert rows == [{
            "label": "aneurysm",
            "sphere": 0,
            "center_r": 5.0,
            "center_a": 0.0,
            "center_s": 0.0,
            "radius": 5.0,
        }]

    def test_spheres_are_numbered_within_each_annotation(self):
        rows = export.sphere_rows([
            ("a", [(0, 0, 0), (2, 0, 0), (10, 0, 0), (14, 0, 0)]),
            ("b", [(0, 0, 0), (0, 6, 0)]),
        ])

        assert [(row["label"], row["sphere"]) for row in rows] == [("a", 0), ("a", 1), ("b", 0)]
        assert [row["radius"] for row in rows] == [1.0, 2.0, 3.0]

    def test_pairs_are_consecutive_points(self):
        # Points 1 and 2 are not a sphere; 0-1 and 2-3 are.
        rows = export.sphere_rows([("a", [(0, 0, 0), (0, 0, 2), (100, 0, 0), (100, 0, 4)])])

        assert [(row["center_r"], row["center_s"], row["radius"]) for row in rows] == [
            (0.0, 1.0, 1.0),
            (100.0, 2.0, 2.0),
        ]

    def test_an_unpaired_point_is_not_exported(self):
        rows = export.sphere_rows([("a", [(0, 0, 0), (10, 0, 0), (50, 50, 50)])])

        assert len(rows) == 1

    def test_no_points_is_no_rows(self):
        assert export.sphere_rows([("a", [])]) == []
        assert export.sphere_rows([]) == []


class TestWriteCsv:
    def test_round_trips_through_the_csv_module(self, tmp_path):
        path = tmp_path / "spheres.csv"
        export.write_csv(path, export.sphere_rows([("nodule", [(1, 2, 3), (1, 2, 7)])]))

        with open(path, newline="", encoding="utf-8") as file:
            rows = list(csv.DictReader(file))

        assert list(rows[0]) == list(export.CSV_COLUMNS)
        assert rows[0]["label"] == "nodule"
        assert float(rows[0]["center_s"]) == pytest.approx(5.0)
        assert float(rows[0]["radius"]) == pytest.approx(2.0)

    def test_no_spheres_still_writes_the_header(self, tmp_path):
        path = tmp_path / "spheres.csv"
        export.write_csv(path, [])

        assert path.read_text(encoding="utf-8").splitlines() == [",".join(export.CSV_COLUMNS)]
