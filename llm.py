"""
Unified LLM caller. All API calls go through here.
Supports retry on rate limits and optional response caching.
"""

import hashlib
import json
import os
import time

import requests

from config import LLM_CONFIGS

# Simple in-memory cache for this run (avoids re-calling for identical prompts)
_cache = {}


def get_available_llms(exclude=None):
    exclude = exclude or []
    return [k for k, v in LLM_CONFIGS.items()
            if k not in exclude and os.environ.get(v["env_key"])]


def call_by_id(llm_id, system_prompt, user_prompt, max_tokens=1500, use_cache=True):
    """Call an LLM by its config ID."""
    config = LLM_CONFIGS[llm_id]
    api_key = os.environ.get(config["env_key"])
    if not api_key:
        return None
    return call(config["provider"], config["model"],
                system_prompt, user_prompt, api_key, max_tokens, use_cache)


def call(provider, model, system_prompt, user_prompt, api_key, max_tokens=1500, use_cache=True):
    """Unified LLM call with retry and optional caching."""
    # Check cache
    if use_cache:
        cache_key = hashlib.md5(
            "{}:{}:{}:{}".format(provider, model, system_prompt, user_prompt).encode()
        ).hexdigest()
        if cache_key in _cache:
            return _cache[cache_key]
    else:
        cache_key = None

    for attempt in range(3):
        try:
            result = _call_once(provider, model, system_prompt, user_prompt, api_key, max_tokens)
            if result and cache_key:
                _cache[cache_key] = result
            return result
        except requests.exceptions.HTTPError as e:
            if e.response is not None and e.response.status_code == 429:
                wait = (attempt + 1) * 15
                print("    ... rate limited, waiting {}s (attempt {}/3)".format(wait, attempt + 1))
                time.sleep(wait)
            else:
                code = e.response.status_code if e.response else "unknown"
                print("  X {}/{}: HTTP {}".format(provider, model, code))
                return None
        except Exception as e:
            print("  X {}/{}: {}".format(provider, model, str(e)[:100]))
            return None
    return None


def _call_once(provider, model, system_prompt, user_prompt, api_key, max_tokens):
    if provider == "google":
        url = "https://generativelanguage.googleapis.com/v1beta/models/{}:generateContent?key={}".format(model, api_key)
        payload = {
            "contents": [{"parts": [{"text": system_prompt + "\n\n" + user_prompt}]}],
            "generationConfig": {"maxOutputTokens": max_tokens, "temperature": 0.3}
        }
        resp = requests.post(url, json=payload, timeout=90)
        resp.raise_for_status()
        return resp.json()["candidates"][0]["content"]["parts"][0]["text"]

    elif provider == "openai":
        url = "https://api.openai.com/v1/chat/completions"
        headers = {"Authorization": "Bearer " + api_key, "Content-Type": "application/json"}
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "max_tokens": max_tokens, "temperature": 0.3
        }
        resp = requests.post(url, headers=headers, json=payload, timeout=90)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]

    elif provider == "anthropic":
        url = "https://api.anthropic.com/v1/messages"
        headers = {
            "x-api-key": api_key, "content-type": "application/json",
            "anthropic-version": "2023-06-01"
        }
        payload = {
            "model": model, "max_tokens": max_tokens,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_prompt}]
        }
        resp = requests.post(url, headers=headers, json=payload, timeout=90)
        resp.raise_for_status()
        return resp.json()["content"][0]["text"]

    elif provider == "xai":
        url = "https://api.x.ai/v1/chat/completions"
        headers = {"Authorization": "Bearer " + api_key, "Content-Type": "application/json"}
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "max_tokens": max_tokens, "temperature": 0.3
        }
        resp = requests.post(url, headers=headers, json=payload, timeout=90)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]
