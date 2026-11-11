"""Explicit API mode only. Never quietly substitute synthetic results when a call fails."""
import json
from pathlib import Path

class OpenAIJSONClient:
    def __init__(self,model='gpt-4.1-mini'):
        from openai import OpenAI
        self.client=OpenAI()  # API key comes from OPENAI_API_KEY
        self.model=model
    def json(self,system,user):
        result=self.client.chat.completions.create(
            model=self.model,
            response_format={'type':'json_object'},
            messages=[{'role':'system','content':system+'\nReturn only a JSON object.'},
                      {'role':'user','content':user}],
        )
        txt=result.choices[0].message.content
        if not txt: raise RuntimeError('LLM returned an empty response; do not infer any fields.')
        return json.loads(txt)

class FixtureJSONClient:
    """For tests and demo ONLY; outputs are hand-authored synthetic expected values."""
    def __init__(self,fixture):
        self.fixture=json.loads(Path(fixture).read_text(encoding='utf-8'))
    def json(self,system,user):
        if 'QUERY_PLANNER' in system: return {'queries':self.fixture['queries']}
        if 'EVIDENCE_EXTRACTOR' in system: return self.fixture['extraction']
        raise ValueError('Unknown fixture prompt')
