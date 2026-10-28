"""Optional diagnostic-only admission guard, embedded in the generated proxy.

Reserve an uncached full-context/full-output envelope before each handoff.
Missing usage keeps that reservation occupied. This is a local pricing-based
guard, not a provider-side spending limit or proof of final invoice charges.
"""
from decimal import Decimal
import json
import os
import threading


class DiagnosticSpendGuard:
    def __init__(self, config, path):
        self.cap = Decimal(config['cap_usd'])
        self.input_price = Decimal(config['input_price'])
        self.output_price = Decimal(config['output_price'])
        self.envelope = Decimal(config['request_envelope_usd'])
        if not all(v.is_finite() and v > 0 for v in
                   (self.cap, self.input_price, self.output_price, self.envelope)):
            raise ValueError('Invalid diagnostic budget')
        self.path, self.lock = path, threading.Lock()
        self.charged, self.pending, self.blocked = Decimal(0), {}, False

    def record(self, event, **fields):
        row = dict(event=event, conservative_spend_usd=str(self.charged),
                   reserved_usd=str(sum(self.pending.values(), Decimal(0))), **fields)
        fd = os.open(self.path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        try:
            data = (json.dumps(row) + '\n').encode()
            if os.write(fd, data) != len(data):
                raise RuntimeError('Incomplete budget journal write')
            os.fsync(fd)
        finally:
            os.close(fd)

    def admit(self, cid, data):
        with self.lock:
            # No paid provider tools/plugins are included in the token envelope.
            native_tools = any(t.get('type') not in ('function', None)
                               for t in data.get('tools', []) if isinstance(t, dict))
            occupied = self.charged + sum(self.pending.values(), Decimal(0))
            if (self.blocked or native_tools or data.get('plugins') or cid in self.pending
                    or occupied + self.envelope > self.cap):
                self.record('rejected_before_handoff', call_id=cid)
                raise RuntimeError('Diagnostic request budget admission denied')
            self.pending[cid] = self.envelope
            self.record('reserved_before_handoff', call_id=cid)

    def settle(self, cid, usage):
        with self.lock:
            if cid not in self.pending:
                self.blocked = True
                return
            usage = usage or {}
            inputs = usage.get('input_tokens', usage.get('prompt_tokens'))
            outputs = usage.get('output_tokens', usage.get('completion_tokens'))
            if any(type(n) is not int or n < 0 for n in (inputs, outputs)):
                self.record('usage_missing_reservation_retained', call_id=cid)
                return
            conservative = inputs * self.input_price + outputs * self.output_price
            cost = usage.get('cost')
            if cost is not None:
                try:
                    provider = Decimal(str(cost))
                    if not provider.is_finite() or provider < 0:
                        raise ValueError('Invalid usage')
                    conservative = max(conservative, provider)
                except Exception:
                    self.blocked = True
                    return
            reserved = self.pending.pop(cid)
            self.charged += conservative
            self.blocked = conservative > reserved or self.charged > self.cap
            self.record('usage_settled_conservatively', call_id=cid,
                        conservative_call_usd=str(conservative), envelope_breached=self.blocked)


def guarded_logger(base, guard):
    class GuardedLogger(base):
        async def async_post_call_streaming_iterator_hook(self, user_api_key_dict, response, request_data):
            # LiteLLM discovers this hook only in the leaf class __dict__.
            # Forward explicitly so adding admission control cannot hide IDs.
            async for item in super().async_post_call_streaming_iterator_hook(user_api_key_dict, response, request_data):
                yield item

        async def async_pre_call_hook(self, user_api_key_dict, cache, data, call_type):
            guard.admit(self.call_id(data), data)
            return await super().async_pre_call_hook(user_api_key_dict, cache, data, call_type)

        async def async_log_success_event(self, kwargs, response_obj, start_time, end_time):
            await super().async_log_success_event(kwargs, response_obj, start_time, end_time)
            # Generated BenchFlow callback provides this content-free extraction.
            guard.settle(self.call_id(kwargs), _usage_from_response(response_obj))
    return GuardedLogger
