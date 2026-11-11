"""JSON clients. Never silently replace a failed real API call with fixture data."""
import json
import os
from pathlib import Path


class OpenAIJSONClient:
    def __init__(self, model='gpt-4.1-mini'):
        from openai import OpenAI
        self.client = OpenAI()  # OPENAI_API_KEY comes from the environment
        self.model = model

    def json(self, system, user):
        response = self.client.chat.completions.create(
            model=self.model,
            response_format={'type': 'json_object'},
            messages=[
                {'role': 'system', 'content': system + '\nReturn only a JSON object.'},
                {'role': 'user', 'content': user},
            ],
        )
        text = response.choices[0].message.content
        if not text or not text.strip():
            raise RuntimeError('LLM returned empty JSON; no fields have been inferred.')
        return json.loads(text)


class DeepSeekJSONClient:
    """DeepSeek's OpenAI-compatible /chat/completions endpoint, JSON mode.

    Never print or persist the key. The notebook reads DEEPSEEK_API_KEY from
    Colab Secrets. The two Step-2 prompts are billed API requests.
    """
    def __init__(self, model='deepseek-flash', api_key=None, max_tokens=8192, thinking=False):
        from openai import OpenAI
        key = api_key or os.environ.get('DEEPSEEK_API_KEY')
        if not key:
            raise RuntimeError('Set DEEPSEEK_API_KEY in Colab Secrets (or the environment).')
        self.client = OpenAI(
            api_key=key,
            base_url='https://api.deepseek.com',
            timeout=90.0,
            max_retries=1,
        )
        self.model = model
        self.max_tokens = max_tokens
        self.thinking = thinking

    def json(self, system, user):
        response = self.client.chat.completions.create(
            model=self.model,
            response_format={'type': 'json_object'},
            max_tokens=self.max_tokens,
            extra_body={'thinking': {'type': 'enabled' if self.thinking else 'disabled'}},
            messages=[
                {'role': 'system', 'content': system + '\nReturn a valid JSON object only.'},
                {'role': 'user', 'content': user},
            ],
        )
        choice = response.choices[0]
        if choice.finish_reason == 'length':
            raise RuntimeError('DeepSeek truncated the JSON response; increase max_tokens or reduce evidence.')
        content = choice.message.content
        if not content or not content.strip():
            raise RuntimeError('DeepSeek returned empty JSON. Try again; do not treat this as a valid extraction.')
        try:
            output = json.loads(content)
        except json.JSONDecodeError as error:
            raise RuntimeError('DeepSeek returned invalid JSON; extraction was not accepted.') from error
        if not isinstance(output, dict):
            raise RuntimeError('DeepSeek JSON result must be an object.')
        return output


class FixtureJSONClient:
    """For tests and synthetic demo ONLY: hand-authored expected answers."""
    def __init__(self, fixture):
        self.fixture = json.loads(Path(fixture).read_text(encoding='utf-8'))

    def json(self, system, user):
        if 'QUERY_PLANNER' in system:
            return {'queries': self.fixture['queries']}
        if 'EVIDENCE_EXTRACTOR' in system:
            return self.fixture['extraction']
        raise ValueError('Unknown fixture prompt')
