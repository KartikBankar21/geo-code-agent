import os

from packages.agent.llm import get_llm_provider


def main():
    provider_name = os.getenv(
        "LLM_PROVIDER",
        "ollama",
    )

    llm = get_llm_provider()

    response = llm.generate(
        "Reply with exactly: LLM PROVIDER TEST PASSED"
    )

    print()
    print("=" * 60)
    print(f"Provider: {provider_name}")
    print(response)
    print("=" * 60)


if __name__ == "__main__":
    main()