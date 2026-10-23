r"""Run from C:\Santio: .\.venv\Scripts\python.exe .\llm_response_test.py"""

import os
from pathlib import Path

from dotenv import load_dotenv
from openai import APIError, OpenAI


# EDIT YOUR PROMPT HERE, then save and run this file again.
PROMPT = "is gandu a slang?"


def main():
    load_dotenv(Path(__file__).with_name(".env"))
    key = os.getenv("NVIDIA_API_KEY")
    if not key:
        raise SystemExit("Set NVIDIA_API_KEY in the project .env file first.")

    model = (
        os.getenv("NVIDIA_MODEL")
        or os.getenv("PBL_MODEL_NAME")
        or "nvidia/nemotron-3-super-120b-a12b"
    ).removeprefix("openai/")
    client = OpenAI(
        base_url=os.getenv("NVIDIA_BASE_URL") or "https://integrate.api.nvidia.com/v1",
        api_key=key,
        timeout=30,
        max_retries=0,
    )
    print(f"Model: {model}", flush=True)
    print(f"Your prompt: {PROMPT}\n\nCalling NVIDIA...", flush=True)
    options = {}
    if "nemotron-3" in model.lower():
        options["extra_body"] = {"chat_template_kwargs": {"enable_thinking": False}}
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": PROMPT}],
            temperature=0.2,
            max_tokens=512,
            stream=False,
            **options,
        )
    except APIError as error:
        raise SystemExit(str(error).replace(key, "[REDACTED]")) from None

    reply = response.choices[0].message.content
    if not reply or not reply.strip():
        raise SystemExit("NVIDIA returned no answer text. Try again or increase max_tokens.")
    print(f"\nLLM response:\n{reply}")
    if response.usage:
        print(f"\nTokens used: {response.usage.total_tokens}")


if __name__ == "__main__":
    main()
