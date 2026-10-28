"""Native default, uniform sampling, and the upstream SMAC3 BO facade."""

import importlib.metadata
import random

from pilot.config import digest
from .config import flatten, unflatten


class PanelObserver:
    def observe(self, panel, results):
        """Same panel data are available to all methods; standard BO uses aggregate loss."""


class Default(PanelObserver):
    def __init__(self, space):
        self.space = space

    def ask(self):
        return self.space.default, {"origin": "native_default"}

    def tell(self, loss, duration):
        pass


class RandomSearch(PanelObserver):
    def __init__(self, space, seed):
        self.points = list(space.points)
        random.Random(seed).shuffle(self.points)

    def ask(self):
        return self.points.pop(), {"origin": "uniform_without_replacement"}

    def tell(self, loss, duration):
        pass


class BayesianOptimization(PanelObserver):
    def __init__(self, space, seed, count, initial_count, output):
        if importlib.metadata.version("smac") != "2.4.0":
            raise RuntimeError("BO requires pinned smac==2.4.0")
        from ConfigSpace import ConfigurationSpace, OrdinalHyperparameter
        from smac import HyperparameterOptimizationFacade as HPO, Scenario

        cs = ConfigurationSpace(seed=seed)
        native = flatten(space.default)
        cs.add([OrdinalHyperparameter(name, values, default_value=native[name])
                for name, values in space.parameters.items()])
        scenario = Scenario(cs, name="baseline-bo", output_directory=output,
                            deterministic=True, n_trials=count, seed=seed,
                            n_workers=1, use_default_config=False)
        self.smac = HPO(
            scenario, target_function=None, overwrite=False, logging_level=40,
            initial_design=HPO.get_initial_design(
                scenario, n_configs=initial_count, max_ratio=1.0),
            intensifier=HPO.get_intensifier(scenario, max_config_calls=1),
            config_selector=HPO.get_config_selector(scenario, retrain_after=1),
        )
        self.space = space
        self.pending = None
        self.seen = set()

    def ask(self):
        if self.pending is not None:
            raise RuntimeError("Previous BO panel has not been told")
        info = self.smac.ask()
        settings = self.space.validate(unflatten(dict(info.config)))
        if digest(settings) in self.seen:
            raise RuntimeError("SMAC proposed a repeated point; no hidden replacement")
        self.pending = info
        self.seen.add(digest(settings))
        return settings, {"origin": info.config.origin, "smac_seed": info.seed,
                          "library": "smac", "version": "2.4.0"}

    def tell(self, loss, duration):
        from smac.runhistory.dataclasses import TrialValue

        if self.pending is None:
            raise RuntimeError("BO tell without a pending panel")
        # A completed panel of operational failures is a valid observed loss.
        # SMAC's cost means objective loss, NOT USD.
        self.smac.tell(self.pending, TrialValue(cost=loss, time=duration))
        self.pending = None
