"""Bốn provider cùng một interface. Không chứa agent loop."""
import json
import os
import urllib.error
import urllib.request
import time
import random
import math
import threading
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

CONFIG = {
    'openai': ('OPENAI_API_KEY', 'https://api.openai.com/v1/chat/completions'),
    'gemini': ('GEMINI_API_KEY', 'https://generativelanguage.googleapis.com/v1beta/openai/chat/completions'),
    'openrouter': ('OPENROUTER_API_KEY', 'https://openrouter.ai/api/v1/chat/completions'),
    'anthropic': ('ANTHROPIC_API_KEY', 'https://api.anthropic.com/v1/messages'),
}


class ProviderRequestError(RuntimeError):
    """Only controlled labels and numbers may enter logs or evaluation reports."""

    def __init__(self, category, attempts, http_status=None, reason=None):
        self.category = category
        self.attempts = attempts
        self.http_status = http_status
        self.reason = reason
        super().__init__(
            f"Provider failure: {category}; HTTP={http_status}; "
            f"attempts={attempts}; reason={reason or 'not_retryable'}"
        )

    def diagnostics(self):
        return {"category": self.category, "http_status": self.http_status,
                "attempts": self.attempts, "reason": self.reason}


# Module state is shared by separate agent and judge Provider instances in
# this Python process. Every Gemini HTTP attempt, including retries, is paced.
GEMINI_MIN_INTERVAL = 6.0
_PACE_LOCK = threading.Lock()
_LAST_START = {}


def _pace_request(url, model, deadline):
    if url != CONFIG['gemini'][1]:
        return
    with _PACE_LOCK:
        key = (url, model)
        previous = _LAST_START.get(key)
        delay = 0.0 if previous is None else max(
            0.0, previous + GEMINI_MIN_INTERVAL - time.monotonic())
        if time.monotonic() + delay >= deadline:
            raise ProviderRequestError('pacing_budget_exhausted', 0)
        if delay:
            time.sleep(delay)
        _LAST_START[key] = time.monotonic()


def _retry_delay(header):
    """Honor delay-seconds and HTTP-date; a past date permits retry now."""
    try:
        delay = float(header)
    except (ValueError, TypeError):
        value = parsedate_to_datetime(str(header))
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        delay = (value - datetime.now(timezone.utc)).total_seconds()
    if not math.isfinite(delay):
        raise ValueError('Non-finite retry delay')
    return max(0.0, delay)


def _http_category(status, exc):
    if status in (401, 403):
        return 'authentication_or_permission', False
    if status == 429:
        # Inspect privately for known non-transient quota failures. Never log
        # messages, bodies, quota identifiers, headers, or credential values.
        try:
            body = json.loads(exc.read(65536).decode('utf-8'))
            error = body.get('error', {})
            code = error.get('code')
            if code in ('credit_balance_exhausted', 'insufficient_quota',
                        'organization_spend_limit_exceeded', 'project_spend_limit_exceeded',
                        'organization_usage_limit_exceeded'):
                return 'quota_exhausted', False
            for detail in error.get('details', []):
                if not isinstance(detail, dict):
                    continue
                for violation in detail.get('violations', []):
                    quota_id = str(violation.get('quotaId', '')).lower()
                    if ('perday' in quota_id or 'per_day' in quota_id
                            or str(violation.get('quotaValue')) == '0'):
                        return 'daily_or_zero_quota', False
        except (ValueError, TypeError, AttributeError, OSError):
            pass
        # Unknown 429s get bounded retries, never an unlimited retry loop.
        return 'rate_limited_or_quota', True
    if status in (408, 500, 502, 503, 504):
        return 'temporary_http_failure', True
    return 'request_rejected', False


def post_json(url, headers, payload):
    request = urllib.request.Request(
        url, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", **headers},
    )
    max_attempts = 3
    wait_budget = 30.0  # Retry sleeps only; pacing is bounded by deadline.
    deadline = time.monotonic() + 240.0

    for attempt in range(1, max_attempts + 1):
        try:
            _pace_request(url, payload.get('model'), deadline)
        except ProviderRequestError as exc:
            raise ProviderRequestError(exc.category, attempt - 1) from None
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ProviderRequestError('request_budget_exhausted', attempt - 1)
        retry_after = None
        http_status = None
        try:
            with urllib.request.urlopen(request, timeout=min(90.0, remaining)) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            http_status = exc.code
            retry_after = exc.headers.get('Retry-After') if exc.headers else None
            try:
                category, retryable = _http_category(http_status, exc)
            finally:
                exc.close()
        except TimeoutError:
            category, retryable = 'timeout', True
        except urllib.error.URLError as exc:
            if isinstance(exc.reason, TimeoutError):
                category = 'timeout'
            else:
                category = 'network_failure'
            retryable = True

        if not retryable or attempt == max_attempts:
            raise ProviderRequestError(
                category, attempt, http_status,
                'attempt_limit' if retryable else 'not_retryable') from None
        delay = 2 ** (attempt - 1) + random.uniform(0, 1)
        if retry_after is not None:
            try:
                delay = max(delay, _retry_delay(retry_after))
            except (ValueError, TypeError, OverflowError):
                raise ProviderRequestError(
                    category, attempt, http_status, 'invalid_retry_after') from None
        if delay > wait_budget or time.monotonic() + delay >= deadline:
            raise ProviderRequestError(
                category, attempt, http_status, 'retry_wait_budget_exceeded') from None
        wait_budget -= delay
        time.sleep(delay)

class Provider:
    """complete(messages, schemas) -> {message, calls, finish, usage}.

    messages: system/user/assistant/tool theo format Chat Completions. message trả về
    cần được append nguyên vẹn; tool result có role, tool_call_id, content (JSON string).
    """
    def __init__(self, name, model):
        if name not in CONFIG:
            raise ValueError(f'Provider không hợp lệ: {name}')
        if not model:
            raise ValueError('Cần đặt MODEL là model có hỗ trợ tool calling.')
        self.name, self.model = name, model
        key_name, self.url = CONFIG[name]
        self.key = os.getenv(key_name)
        if not self.key:
            raise ValueError(f'Thiếu {key_name}; xem README.md.')

    def complete(self, messages, schemas):
        if self.name == 'anthropic':
            return self._anthropic(messages, schemas)
        payload = {'model': self.model, 'messages': messages}
        if schemas:
            payload['tools'] = schemas
        data = post_json(self.url, {'Authorization': f'Bearer {self.key}'}, payload)
        choice = data['choices'][0]
        message = choice['message']
        calls = [{'id': c['id'], 'name': c['function']['name'], 'arguments': c['function']['arguments']} for c in message.get('tool_calls', [])]
        return {'message': message, 'calls': calls, 'finish': choice.get('finish_reason'), 'usage': data.get('usage', {})}

    def _anthropic(self, messages, schemas):
        system = '\n'.join(m['content'] for m in messages if m['role'] == 'system')
        native = []
        for m in messages:
            if m['role'] == 'system':
                continue
            if m['role'] == 'assistant':
                blocks = []
                if m.get('content'):
                    blocks.append({'type': 'text', 'text': m['content']})
                for call in m.get('tool_calls', []):
                    blocks.append({'type': 'tool_use', 'id': call['id'], 'name': call['function']['name'], 'input': json.loads(call['function']['arguments'])})
                native.append({'role': 'assistant', 'content': blocks})
            elif m['role'] == 'tool':
                block = {'type': 'tool_result', 'tool_use_id': m['tool_call_id'], 'content': m['content']}
                if native and native[-1]['role'] == 'user' and isinstance(native[-1]['content'], list):
                    native[-1]['content'].append(block)
                else:
                    native.append({'role': 'user', 'content': [block]})
            else:
                native.append({'role': 'user', 'content': m['content']})
        tools = [{'name': x['function']['name'], 'description': x['function']['description'], 'input_schema': x['function']['parameters']} for x in schemas]
        payload = {'model': self.model, 'max_tokens': 1024, 'system': system, 'messages': native}
        if tools:
            payload['tools'] = tools
        data = post_json(self.url, {'x-api-key': self.key, 'anthropic-version': '2023-06-01'}, payload)
        blocks = data['content']
        calls = [{'id': b['id'], 'name': b['name'], 'arguments': json.dumps(b['input'], ensure_ascii=False)} for b in blocks if b['type'] == 'tool_use']
        text = '\n'.join(b['text'] for b in blocks if b['type'] == 'text')
        message = {'role': 'assistant', 'content': text or None}
        if calls:
            message['tool_calls'] = [{'id': c['id'], 'type': 'function', 'function': {'name': c['name'], 'arguments': c['arguments']}} for c in calls]
        reason = {'end_turn': 'stop', 'tool_use': 'tool_calls', 'max_tokens': 'length'}.get(data.get('stop_reason'), data.get('stop_reason'))
        return {'message': message, 'calls': calls, 'finish': reason, 'usage': data.get('usage', {})}
