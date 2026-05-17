import logging


def cuda_works() -> bool:
    """Return True only if CUDA is available AND a kernel actually executes without error."""
    try:
        import torch
    except ImportError:
        return False
    if not torch.cuda.is_available() or not torch.version.cuda:
        return False
    try:
        torch.zeros(1, device="cuda")
        return True
    except Exception as e:
        logging.debug("CUDA smoke test failed, falling back to CPU: %s", e)
        return False
