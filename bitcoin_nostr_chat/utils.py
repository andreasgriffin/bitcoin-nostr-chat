import os
from collections.abc import Callable, Iterable


def resource_path(*parts):
    pkg_dir = os.path.split(os.path.realpath(__file__))[0]
    return os.path.join(pkg_dir, *parts)


def varnames(method: Callable) -> Iterable[str]:
    return method.__code__.co_varnames[: method.__code__.co_argcount]


def filtered_dict(d: dict, allowed_keys: Iterable[str]) -> dict:
    return {k: v for k, v in d.items() if k in allowed_keys}


def filtered_for_init(d: dict, cls: type) -> dict:
    return filtered_dict(d, varnames(cls.__init__))  # type: ignore
