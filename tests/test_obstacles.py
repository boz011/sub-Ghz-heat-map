"""Tests for obstacle/wall modeling and intersection math."""

import numpy as np
import pytest

from lpwan_sim.core.environment import (
    Environment, Obstacle, MATERIAL_ATTENUATION, segments_intersect,
)


class TestMaterials:
    def test_preset_materials_exist(self):
        for mat in ("drywall", "wood", "glass", "concrete", "brick", "metal"):
            assert mat in MATERIAL_ATTENUATION

    def test_preset_values(self):
        assert MATERIAL_ATTENUATION["drywall"] == 3.0
        assert MATERIAL_ATTENUATION["metal"] == 20.0

    def test_from_material(self):
        obs = Obstacle.from_material((0, 0), (10, 10), "concrete")
        assert obs.attenuation_db == 12.0
        assert obs.material == "concrete"

    def test_from_material_case_insensitive(self):
        obs = Obstacle.from_material((0, 0), (1, 1), "BRICK")
        assert obs.attenuation_db == 10.0

    def test_unknown_material_raises(self):
        with pytest.raises(ValueError, match="Unknown material"):
            Obstacle.from_material((0, 0), (1, 1), "unobtanium")


class TestSegmentsIntersect:
    def test_crossing(self):
        assert segments_intersect((0, 0), (10, 10), (0, 10), (10, 0)) is True

    def test_parallel_no_cross(self):
        assert segments_intersect((0, 0), (10, 0), (0, 1), (10, 1)) is False

    def test_t_intersection(self):
        assert segments_intersect((5, 0), (5, 10), (0, 5), (10, 5)) is True

    def test_no_overlap_short_segments(self):
        assert segments_intersect((0, 0), (1, 0), (2, 0), (3, 0)) is False

    def test_disjoint(self):
        assert segments_intersect((0, 0), (1, 1), (5, 5), (6, 6)) is False


class TestObstacleCreation:
    def test_add_obstacle(self):
        env = Environment(100, 100)
        obs = Obstacle(start_point=(10, 0), end_point=(10, 100), attenuation_db=15.0, material="custom")
        env.add_obstacle(obs)
        assert len(env.obstacles) == 1
        assert env.obstacles[0].attenuation_db == 15.0

    def test_obstacle_attenuation_no_obstacles(self):
        env = Environment(100, 100)
        assert env.obstacle_attenuation(0, 0, 50, 50) == 0.0


class TestObstacleAttenuation:
    def test_single_wall_crossed(self):
        env = Environment(100, 100, resolution=10)
        env.add_obstacle(Obstacle(start_point=(50, 0), end_point=(50, 100),
                                  attenuation_db=12.0, material="concrete"))
        att = env.obstacle_attenuation(0, 50, 100, 50)
        assert att == pytest.approx(12.0)

    def test_no_crossing(self):
        env = Environment(100, 100, resolution=10)
        env.add_obstacle(Obstacle(start_point=(50, 0), end_point=(50, 100),
                                  attenuation_db=12.0, material="concrete"))
        att = env.obstacle_attenuation(0, 50, 40, 50)
        assert att == pytest.approx(0.0)

    def test_multiple_walls_cumulative(self):
        env = Environment(100, 100, resolution=10)
        env.add_obstacle(Obstacle(start_point=(30, 0), end_point=(30, 100),
                                  attenuation_db=3.0, material="drywall"))
        env.add_obstacle(Obstacle(start_point=(60, 0), end_point=(60, 100),
                                  attenuation_db=10.0, material="brick"))
        att = env.obstacle_attenuation(0, 50, 100, 50)
        assert att == pytest.approx(13.0)

    def test_attenuation_grid(self):
        env = Environment(20, 20, resolution=10)
        env.add_obstacle(Obstacle(start_point=(10, 0), end_point=(10, 20),
                                  attenuation_db=5.0, material="wood"))
        grid = env.obstacle_attenuation_grid(0, 0)
        # Points on the left side (x=0) should have 0 attenuation
        assert grid[0, 0] == 0.0
        # Points on the right side (x=10) should have 5 dB attenuation
        assert grid[0, 1] == pytest.approx(5.0)
