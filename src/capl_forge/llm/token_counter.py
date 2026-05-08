"""Token estimation with tiktoken fallback to character approximation."""

_estimate_fn = None


def estimate_tokens(text: str) -> int:
    """Estimate the number of tokens in a text string.

    Uses tiktoken if available, otherwise falls back to
    character-based approximation (4 chars ≈ 1 token).
    """
    global _estimate_fn
    if _estimate_fn is not None:
        return _estimate_fn(text)
    # Try tiktoken
    try:
        import tiktoken
        enc = tiktoken.get_encoding("cl100k_base")
        _estimate_fn = enc.encode
        count = len(_estimate_fn(text))
        return count
    except ImportError:
        pass
    except Exception:
        pass
    # Fallback: character approximation
    _estimate_fn = _char_approximation
    return _char_approximation(text)


def _char_approximation(text: str) -> int:
    """Approximate token count: ~4 characters per token."""
    return max(1, len(text) // 4)
