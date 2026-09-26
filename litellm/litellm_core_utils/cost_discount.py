import fnmatch
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

_GLOB_CHARS: Final = frozenset("*?[")


@dataclass(frozen=True, slots=True)
class CostDiscountKey:
    provider: str
    model_pattern: str | None


def parse_cost_discount_key(key: str) -> CostDiscountKey:
    provider, separator, pattern = key.partition("/")
    return CostDiscountKey(provider=provider, model_pattern=pattern if separator else None)


def _literal_length(pattern: str) -> int:
    length = 0
    index = 0
    while index < len(pattern):
        char = pattern[index]
        if char in "*?":
            index += 1
            continue
        if char == "[":
            search_start = index + 2 if pattern[index + 1 : index + 2] == "!" else index + 1
            if pattern[search_start : search_start + 1] == "]":
                search_start += 1
            closing = pattern.find("]", search_start)
            if closing >= 0:
                index = closing + 1
                continue
        length += 1
        index += 1
    return length


def resolve_cost_discount(
    cost_discount_config: Mapping[str, float],
    custom_llm_provider: str | None,
    model: str | None,
) -> float | None:
    if not custom_llm_provider:
        return None

    provider_prefix: Final = f"{custom_llm_provider}/"
    model_name: Final = (
        model[len(provider_prefix) :] if model is not None and model.startswith(provider_prefix) else model
    )
    patterns: Final = tuple(
        parsed.model_pattern
        for parsed in (parse_cost_discount_key(key) for key in cost_discount_config)
        if parsed.provider == custom_llm_provider and parsed.model_pattern is not None
    )

    if model_name is not None:
        exact: Final = next(
            (pattern for pattern in patterns if not _GLOB_CHARS & set(pattern) and pattern == model_name),
            None,
        )
        if exact is not None:
            return cost_discount_config[f"{custom_llm_provider}/{exact}"]
        matches: Final = tuple(
            pattern for pattern in patterns if _GLOB_CHARS & set(pattern) and fnmatch.fnmatchcase(model_name, pattern)
        )
        if matches:
            best_match: Final = max(matches, key=_literal_length)
            return cost_discount_config[f"{custom_llm_provider}/{best_match}"]

    return cost_discount_config.get(custom_llm_provider)
