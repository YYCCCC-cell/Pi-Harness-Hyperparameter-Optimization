"""Observe provider IDs before LiteLLM's Responses-to-Chat conversion.

Installed only in the project-generated proxy process. No third-party file or
agent-visible payload is changed. The upstream iterator owns the stable call
ID, avoiding a global 'current request' association under concurrent streams.
"""


def install_response_bridge_observer(logger):
    from litellm.completion_extras.litellm_responses_transformation.transformation import (
        OpenAiResponsesToChatCompletionStreamIterator as Bridge,
    )
    original = Bridge.chunk_parser
    if getattr(original, '_pe6203_bridge_observer', False):
        raise RuntimeError('Duplicate response bridge observer')

    def parse_with_identity(self, chunk):
        response = chunk.get('response') if isinstance(chunk, dict) else None
        if isinstance(response, dict) and isinstance(response.get('id'), str):
            upstream = getattr(self, 'streaming_response', None)
            details = getattr(getattr(upstream, 'logging_obj', None), 'model_call_details', None)
            if not isinstance(details, dict):
                raise RuntimeError('Response bridge lacks stable request association')
            # Awaited stream conversion: fsync happens before the chunk reaches
            # the client, including response.created followed by cancellation.
            logger.observe_id(details, chunk)
        return original(self, chunk)

    parse_with_identity._pe6203_bridge_observer = True
    Bridge.chunk_parser = parse_with_identity
    return original
