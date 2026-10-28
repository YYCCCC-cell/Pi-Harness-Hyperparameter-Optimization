"""Same pass-rate/cost/time tie-break for every method within each backend."""


def selection_key(panel):
    if panel.get("measurement_kind") == "real":
        return (-panel["pass_rate"], panel["accounted_usd"],
                panel["wall_time_seconds"], panel["config_id"])
    return (-panel["pass_rate"], panel["simulated_cost_units"],
            panel["simulated_time_seconds"], panel["config_id"])
