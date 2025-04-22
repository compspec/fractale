from .flux import Transformer as FluxTransformer

plugins = {
    "flux": FluxTransformer,
}


def get_transformer(name, selector, solver):
    if name not in plugins:
        raise ValueError(f"{name} is not a valid transformer.")
    return plugins[name](selector, solver)
