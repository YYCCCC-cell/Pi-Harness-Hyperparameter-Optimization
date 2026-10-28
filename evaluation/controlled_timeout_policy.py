"""Explicit fault-injection boundary; never a search-space parameter."""


def agent_timeout_override(request):
    diagnostic = request.get('controlled_timeout_diagnostic')
    if diagnostic is None:
        return None
    if (diagnostic != {'purpose': 'native_watchdog_accounting_acceptance', 'agent_seconds': 20,
                       'exclude_from_benchmark_results': True}
            or request['task_id'] != 'bike-rebalance'
            or request.get('evaluation_access') is not None
            or request['plan']['timeouts']['agent'] <= 20):
        raise ValueError('Invalid controlled timeout diagnostic')
    return 20
