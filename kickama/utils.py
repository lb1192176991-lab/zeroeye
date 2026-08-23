"""
Utility functions for Kickama distributed training and deterministic seeding.
"""

import os
import random
import numpy as np
import torch
import torch.distributed as dist


def set_deterministic_data_seed(seed: int, dp_rank: int = 0, tp_rank: int = 0, pp_rank: int = 0) -> int:
    """
    Sets deterministic random seeds for data loading and generation routines across parallel model parameters.

    To prevent state differentiation across Tensor Parallel (TP) and Pipeline Parallel (PP) ranks,
    ranks within the same Data Parallel (DP) group must share the exact same data seed.
    Different DP groups receive distinct seeds to ensure diverse data sampling across data parallel workers.

    Args:
        seed (int): Base random seed.
        dp_rank (int): Data parallel rank index. Defaults to 0.
        tp_rank (int): Tensor parallel rank index (unused for seed generation to ensure state alignment). Defaults to 0.
        pp_rank (int): Pipeline parallel rank index (unused for seed generation to ensure state alignment). Defaults to 0.

    Returns:
        int: Calculated deterministic seed assigned to the current process.
    """
    # Data seed depends strictly on base seed and data parallel rank
    # TP and PP ranks within the same DP group receive identical data seeds
    data_seed = seed + dp_rank

    random.seed(data_seed)
    np.random.seed(data_seed % (2**32))
    torch.manual_seed(data_seed)

    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(data_seed)
        torch.backends.cudnn.deterministic = True
        torch.backends.cudnn.benchmark = False

    return data_seed


def get_parallel_ranks():
    """
    Helper function to retrieve parallel ranks (dp_rank, tp_rank, pp_rank) from
    torch.distributed environment variables or initialized process groups.
    """
    if not dist.is_available() or not dist.is_initialized():
        return 0, 0, 0

    global_rank = dist.get_rank()
    world_size = dist.get_world_size()

    # Retrieve mesh coordinate attributes or environment variable fallback
    dp_rank = int(os.environ.get("DP_RANK", getattr(dist, "dp_rank", 0)))
    tp_rank = int(os.environ.get("TP_RANK", getattr(dist, "tp_rank", 0)))
    pp_rank = int(os.environ.get("PP_RANK", getattr(dist, "pp_rank", 0)))

    # Default fallback to global_rank as dp_rank if no parallel groups defined
    if dp_rank == 0 and tp_rank == 0 and pp_rank == 0 and world_size > 1:
        dp_rank = global_rank

    return dp_rank, tp_rank, pp_rank


def seed_everything(seed: int = 42) -> int:
    """
    Convenience function to deterministically seed all random number generators
    taking parallel model parameter state into account.
    """
    dp_rank, tp_rank, pp_rank = get_parallel_ranks()
    return set_deterministic_data_seed(seed, dp_rank=dp_rank, tp_rank=tp_rank, pp_rank=pp_rank)
