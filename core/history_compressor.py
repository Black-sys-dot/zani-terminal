def should_soft_reset(total_tokens, config):
    return total_tokens >= config["soft_reset_tokens"]


def split_history(history, keep_ratio):
    keep_n = max(1, int(len(history) * keep_ratio))
    old = history[:-keep_n]
    recent = history[-keep_n:]
    return old, recent
