"""Charge dispatches, reserve known bounds, and distinguish USD provenance."""

from decimal import Decimal


def money(value):
    number = Decimal(str(value))
    if not number.is_finite() or number < 0:
        raise ValueError("Budget quantities must be finite and nonnegative")
    return number


class Ledger:
    def __init__(self, attempts, usd_cap, simulated_cap):
        self.limit = attempts
        self.usd_cap, self.simulated_cap = money(usd_cap), money(simulated_cap)
        self.attempts = 0
        self.usd = self.actual = self.estimated = self.simulated = Decimal(0)
        self.actual_count = self.estimated_count = self.unknown_count = 0
        self.problem = None
        self.pending = None

    def reserve(self, usd_bound, simulated_bound):
        if self.pending is not None:
            raise RuntimeError("An attempt is already in flight")
        if self.problem:
            return self.problem
        if self.attempts >= self.limit:
            return "attempt_budget"
        usd, simulated = money(usd_bound), money(simulated_bound)
        if self.usd + usd > self.usd_cap:
            return "usd_budget"
        if self.simulated + simulated > self.simulated_cap:
            return "simulated_cost_budget"
        self.pending = usd, simulated
        self.attempts += 1  # Charged BEFORE evaluator dispatch, including crashes.
        return None

    def settle(self, result):
        if self.pending is None:
            raise RuntimeError("Cannot settle an undispatched attempt")
        usd_bound, simulated_bound = self.pending
        self.pending = None
        actual, estimate = result["actual_cost_usd"], result["estimated_cost_usd"]
        if actual is not None:
            charge = money(actual)
            self.actual += charge
            self.actual_count += 1
        elif estimate is not None:
            charge = money(estimate)
            self.estimated += charge
            self.estimated_count += 1
        else:
            charge = None
            self.unknown_count += 1
            self.problem = "measurement_gate_missing_cost"
        if charge is not None:
            self.usd += charge
            if charge > usd_bound or self.usd > self.usd_cap:
                self.problem = "usd_bound_breach"
        simulated = result["simulated_cost_units"]
        if simulated is not None:
            self.simulated += money(simulated)
            if money(simulated) > simulated_bound or self.simulated > self.simulated_cap:
                self.problem = "simulated_bound_breach"

    def snapshot(self):
        return {
            "attempt_limit": self.limit, "attempts": self.attempts,
            "actual_usd_known_sum": float(self.actual),
            "estimated_usd_used_sum": float(self.estimated),
            "accounted_usd": float(self.usd) if not self.unknown_count else None,
            "actual_cost_attempts": self.actual_count,
            "estimated_cost_attempts": self.estimated_count,
            "unknown_cost_attempts": self.unknown_count,
            "simulated_cost_units": float(self.simulated),
            "usd_cap": float(self.usd_cap), "simulated_cap": float(self.simulated_cap),
            "problem": self.problem,
        }
