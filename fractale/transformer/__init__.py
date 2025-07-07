from .flux import Transformer as FluxTransformer
from .kubernetes import Transformer as KubernetesTransformer

plugins = {
    "kubernetes": KubernetesTransformer,
    "flux": FluxTransformer,
}


def get_transformer(name, selector="random", solver=None):
    if name not in plugins:
        raise ValueError(f"{name} is not a valid transformer.")
    return plugins[name](selector, solver)
