"""Reusable DeepSeek client setup. No generation or retry in authentication preflight."""
def normalize_api_key(key):
    if not isinstance(key,str) or not key.strip():
        raise ValueError("Missing DEEPSEEK_API_KEY")
    key=key.strip()
    if any(c.isspace() for c in key):
        raise ValueError("API key contains internal whitespace")
    return key

def preflight_deepseek(key,model="deepseek-flash",client_factory=None):
    """Return authenticated client; never print key or raw provider errors."""
    key=normalize_api_key(key)
    if client_factory is None:
        from openai import OpenAI
        client_factory=OpenAI
    client=client_factory(api_key=key,base_url="https://api.deepseek.com",max_retries=0,timeout=120)
    try:
        models=client.models.list()
    except Exception as e:
        code=getattr(e,"status_code",None)
        raise RuntimeError(f"DeepSeek preflight failed: {type(e).__name__}; HTTP {code if isinstance(code,int) else 'unknown'}") from None
    if model not in {m.id for m in models.data}:
        raise RuntimeError("Requested model not returned by DeepSeek model list")
    return client
