"""
kupas/services/llm_client.py
Async Ollama/OpenAI-compatible LLM client.
"""

import json
import logging
import re
from typing import Dict, Optional

import httpx

from kupas.config import OLLAMA_BASE_URL, OLLAMA_MODEL, OLLAMA_TIMEOUT

logger = logging.getLogger(__name__)


class OllamaClient:
    def __init__(self, base_url: str = OLLAMA_BASE_URL, model: str = OLLAMA_MODEL):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.endpoint = f"{self.base_url}/chat/completions"
        self.timeout = OLLAMA_TIMEOUT

    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: int = 2048,
        temperature: float = 0.3,
    ) -> str:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                resp = await client.post(
                    self.endpoint,
                    json={
                        "model": self.model,
                        "messages": messages,
                        "max_tokens": max_tokens,
                        "temperature": temperature,
                        "stream": False,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                content: str = data["choices"][0]["message"]["content"].strip()
                logger.info("Ollama generated %d chars", len(content))
                return content
            except httpx.ConnectError:
                logger.error("Cannot connect to Ollama at %s", self.base_url)
                raise RuntimeError("Gagal terhubung ke Ollama. Pastikan service berjalan.")
            except httpx.HTTPStatusError as e:
                logger.error("Ollama API error: %s", e.response.status_code)
                raise RuntimeError(f"Ollama error: {e.response.status_code}")
            except Exception as e:
                logger.error("Unexpected Ollama error: %s", str(e))
                raise RuntimeError(f"Generate failed: {str(e)}")

    async def generate_structured(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        response_format: str = "json",
    ) -> Dict:
        if response_format == "json":
            format_instruction = "\n\nFormat jawaban HARUS JSON valid. Jangan tambahkan teks lain."
        else:
            format_instruction = "\n\nFormat jawaban dalam Markdown yang rapi."

        result = await self.generate(prompt + format_instruction, system_prompt)

        if response_format == "json":
            json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", result, re.DOTALL)
            if json_match:
                result = json_match.group(1)
            return json.loads(result)

        return {"content": result}

    async def close(self) -> None:
        pass  # httpx.AsyncClient cleans up via context manager
