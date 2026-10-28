"""Phase 4 IGBS and its matched pair-blind ablation; no harness access."""

from copy import deepcopy
from itertools import combinations
import random

from pilot.config import digest
from .config import flatten, unflatten
from .contrasts import ContrastAnalyzer
from .selection import selection_key

SPECIFICATION = {
    "version": "igbs-1",
    "screen_panels": 7,
    "action_cycle": ["pair", "single", "global"],
    "bootstrap_resamples": 2000,
    "bootstrap_quantile": 0.95,
    "practical_threshold": 0.05,
    "minimum_groups": 8,
    "minimum_stability": 0.8,
}


def stream_seed(seed, purpose):
    return int(digest({"seed": seed, "purpose": purpose})[:8], 16)


class InteractionSearch:
    def __init__(self, space, seed, groups, pair_blind=False):
        self.space, self.pair_blind = space, pair_blind
        self.names = tuple(space.parameters)
        if len(self.names) != 3 or any(len(v) != 3 for v in space.parameters.values()):
            raise ValueError("IGBS v1 requires the frozen three-by-three space")
        self.streams = {name: stream_seed(seed, name) for name in
                        ("initialization", "blocks", "candidates", "bootstrap")}
        initial = random.Random(self.streams["initialization"])
        self.block_rng = random.Random(self.streams["blocks"])
        self.candidate_rng = random.Random(self.streams["candidates"])
        self.analyzer = ContrastAnalyzer(space, groups, self.streams["bootstrap"], SPECIFICATION)
        default = flatten(space.default)
        alternative = {n: initial.choice([v for v in space.parameters[n] if v != default[n]])
                       for n in self.names}
        self.screen = [deepcopy(space.default)]
        for size in (1, 2):
            for dims in combinations(self.names, size):
                self.screen.append(space.validate(unflatten(dict(default, **{n: alternative[n] for n in dims}))))
        self.pending = None
        self.seen, self.history = set(), []
        self.incumbent = None

    def ask(self):
        if self.pending is not None:
            raise RuntimeError("Previous IGBS panel has not been observed")
        index = len(self.history)
        diagnostic, selected_block, reason = None, None, None
        if index < len(self.screen):
            candidate, action = self.screen[index], "screen"
        else:
            action = SPECIFICATION["action_cycle"][(index - len(self.screen)) % 3]
            center = self.incumbent["settings"]
            diagnostic = self.analyzer.analyze(self.history, center)
            unseen = [p for p in self.space.points if digest(p) not in self.seen]
            if not unseen:
                raise StopIteration("Finite grid exhausted")
            eligible = []
            size = {"single": 1, "pair": 2}.get(action)
            if size:
                flat_center = flatten(center)
                for block in diagnostic["blocks"]:
                    dims = block["dimensions"]
                    if len(dims) != size:
                        continue
                    candidates = [p for p in unseen if
                                  {n for n, v in flatten(p).items() if v != flat_center[n]} == set(dims)]
                    if candidates:
                        weight = 0.0 if self.pair_blind and size == 2 else block["weight"]
                        eligible.append((dims, weight, candidates))
            if not eligible:
                reason = "scheduled_global" if action == "global" else "no_unseen_local_neighbor"
                candidate = self.candidate_rng.choice(unseen)
            else:
                best = max(weight for _, weight, _ in eligible)
                choices = [e for e in eligible if e[1] == best] if best > 0 else eligible
                selected_block, _, candidates = self.block_rng.choice(choices)
                reason = ("positive_stable_weight" if best > 0 else
                          "pair_blind_uniform" if self.pair_blind and size == 2 else
                          "unidentified_or_unreliable_uniform")
                candidate = self.candidate_rng.choice(candidates)
        candidate = self.space.validate(candidate)
        cid = digest(candidate)
        if cid in self.seen:
            raise RuntimeError("IGBS proposed a repeated configuration")
        self.seen.add(cid)
        self.pending = deepcopy(candidate)
        return candidate, {"origin": "igbs_pair_blind" if self.pair_blind else "igbs",
                           "algorithm_version": SPECIFICATION["version"], "action": action,
                           "selected_block": selected_block, "routing_reason": reason,
                           "stream_seeds": self.streams, "diagnostic": diagnostic}

    def tell(self, loss, duration):
        if self.pending is None:
            raise RuntimeError("IGBS tell without a proposal")
        # The full, task-paired observation is delivered by observe().

    def observe(self, panel, results):
        if self.pending is None or panel["settings"] != self.pending:
            raise ValueError("IGBS observation does not match its own pending proposal")
        if not panel["complete"] or not panel["measurement_valid"]:
            raise ValueError("IGBS cannot learn from partial or invalid panels")
        tasks = [r["task_id"] for r in results]
        if len(tasks) != len(set(tasks)) or set(tasks) != set(self.analyzer.tasks):
            raise ValueError("IGBS requires exactly its validation tasks")
        if any(type(r["success"]) is not bool for r in results):
            raise ValueError("Expected normalized boolean success")
        if panel["pass_rate"] != sum(r["success"] for r in results) / len(results):
            raise ValueError("Panel score disagrees with observations")
        self.history.append({"settings": deepcopy(self.pending), "results": deepcopy(results)})
        if self.incumbent is None or selection_key(panel) < selection_key(self.incumbent):
            self.incumbent = deepcopy(panel)
        self.pending = None
