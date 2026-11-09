# -*- coding: utf-8 -*-
"""大模型接入层：任何 OpenAI 兼容的 /chat/completions 接口。

设计约束：
1. 只用标准库，不引入依赖。项目至今零第三方依赖，这一点不破坏。
2. 没有配置模型时**不是报错**，而是明确告知「未配置」，由上层回退到本地模板。
3. API Key 只在内存与请求头里出现，不写日志、不写文件、status 接口只回掩码。
"""

from __future__ import annotations

import json
import os
import ssl
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "config" / "llm.json"

# 常用服务商预设。base_url 一律到 /v1 这一层，代码里再拼 /chat/completions。
PRESETS: dict[str, dict] = {
    "deepseek": {"base_url": "https://api.deepseek.com/v1", "model": "deepseek-chat"},
    "moonshot": {"base_url": "https://api.moonshot.cn/v1", "model": "moonshot-v1-8k"},
    "qwen": {"base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1", "model": "qwen-plus"},
    "openai": {"base_url": "https://api.openai.com/v1", "model": "gpt-4o-mini"},
    "ollama": {"base_url": "http://127.0.0.1:11434/v1", "model": "qwen2.5:7b"},
    "custom": {"base_url": "", "model": ""},
}


class LLMNotConfigured(RuntimeError):
    """没有可用的模型配置。上层应回退到本地模板，而不是抛给用户。"""


class LLMError(RuntimeError):
    """调用失败（网络、鉴权、限流、返回格式）。消息面向用户可读。"""


@dataclass
class LLMConfig:
    provider: str = "custom"
    base_url: str = ""
    api_key: str = ""
    model: str = ""
    temperature: float = 0.4
    max_tokens: int = 1400
    timeout: float = 60.0
    extra: dict = field(default_factory=dict)

    @property
    def endpoint(self) -> str:
        base = self.base_url.rstrip("/")
        if base.endswith("/chat/completions"):
            return base
        return base + "/chat/completions"

    def masked_key(self) -> str:
        k = self.api_key or ""
        if not k:
            return ""
        if len(k) <= 8:
            return "*" * len(k)
        return f"{k[:4]}{'*' * 6}{k[-4:]}"

    def public(self) -> dict:
        return {
            "provider": self.provider,
            "base_url": self.base_url,
            "model": self.model,
            "masked_key": self.masked_key(),
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }


def _read_file_config(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # 配置写坏了不能拖垮整个应用
        raise LLMError(f"配置文件 {path.name} 不是合法 JSON：{exc}") from exc
    if not isinstance(data, dict):
        raise LLMError(f"配置文件 {path.name} 顶层必须是对象")
    return data


def resolve_config(overrides: dict | None = None) -> LLMConfig:
    """优先级：显式参数 > 环境变量 > config/llm.json > OPENAI_API_KEY。

    任何一层都可能不存在；全都为空时抛 LLMNotConfigured，由调用方回退。
    """
    overrides = overrides or {}
    file_cfg = _read_file_config(CONFIG_PATH)

    provider = (
        overrides.get("provider")
        or os.environ.get("MINGLI_LLM_PROVIDER")
        or file_cfg.get("provider")
        or ("openai" if os.environ.get("OPENAI_API_KEY") and not file_cfg else "")
        or "custom"
    )
    preset = PRESETS.get(provider, {})

    def pick(key: str, env: str, default=""):
        return (
            overrides.get(key)
            or os.environ.get(env)
            or file_cfg.get(key)
            or preset.get(key)
            or default
        )

    base_url = pick("base_url", "MINGLI_LLM_BASE_URL")
    model = pick("model", "MINGLI_LLM_MODEL")
    api_key = pick("api_key", "MINGLI_LLM_API_KEY")

    # OpenAI 官方走通用环境变量兜底
    if not api_key and provider == "openai":
        api_key = os.environ.get("OPENAI_API_KEY", "")
    if not base_url and provider == "openai" and api_key:
        base_url = PRESETS["openai"]["base_url"]
    if not model and provider == "openai" and api_key:
        model = PRESETS["openai"]["model"]

    timeout = float(
        overrides.get("timeout")
        or os.environ.get("MINGLI_LLM_TIMEOUT")
        or file_cfg.get("timeout")
        or 60.0
    )
    temperature = float(
        overrides.get("temperature", file_cfg.get("temperature", 0.4))
    )
    max_tokens = int(overrides.get("max_tokens", file_cfg.get("max_tokens", 1400)))

    cfg = LLMConfig(
        provider=provider,
        base_url=base_url,
        api_key=api_key,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout=timeout,
    )

    # 本地 ollama 不需要 key；其余需要 base_url + model，远端还需要 key
    if not cfg.base_url or not cfg.model:
        raise LLMNotConfigured(
            "未配置大模型。可用环境变量 MINGLI_LLM_PROVIDER=deepseek、"
            "MINGLI_LLM_API_KEY=sk-xxx，或在 config/llm.json 中配置。"
        )
    if cfg.provider != "ollama" and not cfg.api_key:
        raise LLMNotConfigured(
            f"已指定服务商 {cfg.provider}，但缺少 API Key。"
            "请设置 MINGLI_LLM_API_KEY 或写入 config/llm.json。"
        )
    return cfg


def is_configured() -> bool:
    try:
        resolve_config()
        return True
    except (LLMNotConfigured, LLMError):
        return False


def _post_json(url: str, payload: dict, api_key: str, timeout: float) -> dict:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    if api_key:
        req.add_header("Authorization", f"Bearer {api_key}")

    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            raw = resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:500]
        hint = {
            401: "API Key 无效或已过期",
            403: "该 Key 无权访问此模型",
            404: "接口地址或模型名不存在",
            429: "触发限流，请稍后再试",
        }.get(exc.code, "服务端返回错误")
        raise LLMError(f"{hint}（HTTP {exc.code}）：{detail}") from exc
    except urllib.error.URLError as exc:
        raise LLMError(f"无法连接模型服务：{exc.reason}") from exc
    except TimeoutError as exc:
        raise LLMError(f"模型服务超时（{timeout:.0f} 秒）") from exc

    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise LLMError(f"模型返回的不是 JSON：{raw[:200]}") from exc


def chat(messages: list[dict], cfg: LLMConfig | None = None,
         retries: int = 1) -> dict:
    """调用模型，返回 {text, model, provider, usage, elapsed_ms}。"""
    cfg = cfg or resolve_config()
    payload = {
        "model": cfg.model,
        "messages": messages,
        "temperature": cfg.temperature,
        "max_tokens": cfg.max_tokens,
        "stream": False,
    }
    started = time.time()
    last: Exception | None = None
    for attempt in range(retries + 1):
        try:
            data = _post_json(cfg.endpoint, payload, cfg.api_key, cfg.timeout)
            break
        except LLMError as exc:
            last = exc
            # 只对限流与服务端 5xx 重试，鉴权错误重试无意义
            msg = str(exc)
            if attempt < retries and ("429" in msg or "50" in msg[:40]):
                time.sleep(1.5)
                continue
            raise
    else:  # pragma: no cover - 循环必然 break 或 raise
        raise last or LLMError("未知错误")

    try:
        choices = data["choices"]
        content = choices[0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMError(f"模型返回结构异常：{str(data)[:300]}") from exc

    if isinstance(content, list):  # 某些实现返回分段内容
        content = "".join(
            part.get("text", "") for part in content if isinstance(part, dict)
        )

    return {
        "text": (content or "").strip(),
        "model": data.get("model", cfg.model),
        "provider": cfg.provider,
        "usage": data.get("usage", {}),
        "elapsed_ms": int((time.time() - started) * 1000),
    }


def status() -> dict:
    """给界面用的状态。绝不返回明文 Key。"""
    try:
        cfg = resolve_config()
        return {"configured": True, **cfg.public(),
                "presets": sorted(k for k in PRESETS if k != "custom")}
    except LLMNotConfigured as exc:
        return {"configured": False, "reason": str(exc),
                "presets": sorted(k for k in PRESETS if k != "custom")}
    except LLMError as exc:
        return {"configured": False, "reason": str(exc),
                "presets": sorted(k for k in PRESETS if k != "custom")}
