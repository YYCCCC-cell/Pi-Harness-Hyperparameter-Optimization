"""Source appended to BenchFlow's generated callback module, not imported here.

The generated module supplies BenchFlowLiteLLMLogger. This extension changes
only host-side accounting, and never persists prompts, responses or secrets.
"""
import os
import json
import threading
import re


class JournalLogger(BenchFlowLiteLLMLogger):
    def __init__(self, journal_path):
        super().__init__()
        self.journal_path = journal_path
        self.journal_lock = threading.Lock()
        self.observed_ids = set()
        self.emit("proxy_ready", version="request_journal_v1")

    def emit(self, event, **fields):
        data = (json.dumps(dict(event=event, **fields), allow_nan=False) + "\n").encode()
        with self.journal_lock:
            fd = os.open(self.journal_path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            try:
                if os.write(fd, data) != len(data):
                    raise RuntimeError("Incomplete metering journal write")
                os.fsync(fd)
            finally:
                os.close(fd)

    @staticmethod
    def call_id(data):
        value = data.get("litellm_call_id") or (data.get("litellm_params") or {}).get("litellm_call_id")
        if not isinstance(value, str) or not 1 <= len(value) <= 256:
            raise ValueError("Missing stable proxy call ID")
        return value

    async def async_pre_call_hook(self, user_api_key_dict, cache, data, call_type):
        # Awaited by the proxy before routing; a failed write rejects the call.
        self.emit("request_started", call_id=self.call_id(data))
        return data

    def log_pre_api_call(self, model, messages, kwargs):
        # Count retries separately. A missing/duplicate handoff fails the audit.
        self.emit("provider_attempt", call_id=self.call_id(kwargs))

    def _base_record(self, kwargs, start_time, end_time):
        return dict(super()._base_record(kwargs, start_time, end_time), call_id=self.call_id(kwargs))

    def observe_id(self, kwargs, response_obj):
        response = _jsonable(response_obj)
        identifier = response.get("id") if isinstance(response, dict) else None
        if identifier is None and isinstance(response, dict):
            identifier = (response.get("response") or {}).get("id")
        if (isinstance(identifier, str) and len(identifier) < 2048
                and not re.fullmatch(r"chatcmpl-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", identifier)):
            key = (self.call_id(kwargs), identifier)
            if key not in self.observed_ids:
                self.observed_ids.add(key)
                self.emit("generation_observed", call_id=key[0], response_id=identifier)

    async def async_log_stream_event(self, kwargs, response_obj, start_time, end_time):
        self.observe_id(kwargs, response_obj)

    async def async_post_call_streaming_iterator_hook(self, user_api_key_dict, response, request_data):
        # The awaited iterator hook also covers native Responses streams, whose
        # logging callbacks may only run at response.completed.
        async for item in response:
            self.observe_id(request_data, item)
            yield item

    async def async_log_success_event(self, kwargs, response_obj, start_time, end_time):
        self.observe_id(kwargs, response_obj)
        await super().async_log_success_event(kwargs, response_obj, start_time, end_time)
        self.emit("request_finished", call_id=self.call_id(kwargs), outcome="success")

    async def async_log_failure_event(self, kwargs, response_obj, start_time, end_time):
        self.observe_id(kwargs, response_obj)
        await super().async_log_failure_event(kwargs, response_obj, start_time, end_time)
        self.emit("request_finished", call_id=self.call_id(kwargs), outcome="failure")
