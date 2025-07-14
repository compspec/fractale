from .flux import Transformer as FluxTransformer
from .kubernetes import Transformer as KubernetesTransformer
from .slurm import Transformer as SlurmTransformer

plugins = {
    "kubernetes": KubernetesTransformer,
    "flux": FluxTransformer,
    "slurm": SlurmTransformer,
}


def get_transformer(name, selector="random", solver=None):
    if name not in plugins:
        raise ValueError(f"{name} is not a valid transformer.")
    return plugins[name](selector, solver)
