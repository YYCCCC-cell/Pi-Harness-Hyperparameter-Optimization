"""Observed matched contrasts; bootstrap weights are routing heuristics, not tests."""

from itertools import combinations, product
from math import sqrt

import numpy as np

from pilot.config import digest
from .config import flatten


class ContrastAnalyzer:
    def __init__(self, space, groups, seed, specification):
        self.names = tuple(space.parameters)
        self.domains = tuple(tuple(space.parameters[n]) for n in self.names)
        self.groups = tuple(tuple(g["tasks"]) for g in groups)
        self.tasks = tuple(t for group in self.groups for t in group)
        if not self.tasks or len(set(self.tasks)) != len(self.tasks):
            raise ValueError("Groups must partition distinct validation tasks")
        self.spec = dict(specification)
        self.sizes = np.array([len(g) for g in self.groups], dtype=int)
        if np.any(self.sizes == 0):
            raise ValueError("Empty validation group")
        self.draws = np.random.default_rng(seed).integers(
            0, len(self.groups), (self.spec["bootstrap_resamples"], len(self.groups)))
        self.denominators = self.sizes[self.draws].sum(axis=1)
        self.cache = {}

    def point(self, settings):
        flat = flatten(settings)
        return tuple(flat[n] for n in self.names)

    def estimate(self, values):
        if set(values) != set(self.tasks):
            raise ValueError("Contrast must contain exactly the validation roster")
        nums = np.array([sum(values[t] for t in g) for g in self.groups], dtype=float)
        if not np.all(np.isfinite(nums)):
            raise ValueError("Nonfinite contrast")
        delta = float(nums.sum() / len(self.tasks))
        boot = nums[self.draws].sum(axis=1) / self.denominators
        radius = float(np.quantile(np.abs(boot - delta), self.spec["bootstrap_quantile"],
                                   method="linear"))
        leave = [(nums.sum() - n) / (len(self.tasks) - size)
                 for n, size in zip(nums, self.sizes) if size < len(self.tasks)]
        epsilon = self.spec["practical_threshold"]
        stability = (sum(d * delta > 0 and abs(d) > epsilon / 2 for d in leave) / len(leave)
                     if leave else 0.0)
        weight = max(0.0, abs(delta) - radius - epsilon)
        if len(self.groups) < self.spec["minimum_groups"] or stability < self.spec["minimum_stability"]:
            weight = 0.0
        return {"delta": delta, "bootstrap_radius": radius,
                "leave_one_group_stability": stability, "routing_weight": weight,
                "group_count": len(self.groups), "task_count": len(self.tasks)}

    def analyze(self, history, center=None):
        """History contains private completed panels, not pooled other-method trials."""
        observed = {self.point(h["settings"]): h for h in history}
        if len(observed) != len(history):
            raise ValueError("Repeated configuration in contrast history")
        current = self.point(center) if center is not None else None
        contrasts, blocks = [], []
        for size in (1, 2):
            for dims in combinations(range(len(self.names)), size):
                others = tuple(i for i in range(len(self.names)) if i not in dims)
                backgrounds = ([tuple(current[i] for i in others)] if current is not None else
                               product(*(self.domains[i] for i in others)))
                block_rows = []
                for background in backgrounds:
                    for levels in product(*(tuple(combinations(self.domains[i], 2)) for i in dims)):
                        cells = []
                        for bits in product((0, 1), repeat=size):
                            point = [None] * len(self.names)
                            for i, value in zip(others, background):
                                point[i] = value
                            for i, values, bit in zip(dims, levels, bits):
                                point[i] = values[bit]
                            cells.append(tuple(point))
                        if not all(p in observed for p in cells):
                            continue  # Missing corner is unknown, never zero.
                        panels = [observed[p] for p in cells]
                        ids = [digest(p["settings"]) for p in panels]
                        coefficients = [-1, 1] if size == 1 else [1, -1, -1, 1]
                        key = tuple(ids)
                        if key not in self.cache:
                            results = [{r["task_id"]: r for r in p["results"]} for p in panels]
                            if any(set(r) != set(self.tasks) for r in results):
                                raise ValueError("Incomplete contrast panel")
                            values = {t: sum(c * float(r[t]["success"])
                                             for c, r in zip(coefficients, results)) for t in self.tasks}
                            cost = {}
                            for field in ("actual_cost_usd", "estimated_cost_usd",
                                          "simulated_cost_units", "simulated_time_seconds"):
                                cells_values = [r[t].get(field) for r in results for t in self.tasks]
                                cost[field] = (sum(c * sum(r[t][field] for t in self.tasks)
                                                   for c, r in zip(coefficients, results)) / len(self.tasks)
                                               if all(v is not None for v in cells_values) else None)
                            self.cache[key] = {**self.estimate(values), "cost_time_contrasts": cost}
                        row = {"kind": "edge" if size == 1 else "rectangle",
                               "dimensions": [self.names[i] for i in dims],
                               "levels": [list(v) for v in levels],
                               "background": {self.names[i]: v for i, v in zip(others, background)},
                               "configuration_ids": ids, "coefficients": coefficients,
                               **self.cache[key]}
                        block_rows.append(row)
                contrasts.extend(block_rows)
                weights = [r["routing_weight"] for r in block_rows]
                blocks.append({"dimensions": [self.names[i] for i in dims],
                               "coverage": len(weights), "identified": bool(weights),
                               "weight": sqrt(sum(w*w for w in weights) / len(weights)) if weights else 0.0})
        return {"blocks": blocks, "contrasts": contrasts,
                "interpretation": "Local observed contrasts; routing weights are not significance tests."}
