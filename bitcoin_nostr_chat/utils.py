import os
from typing import Callable, Dict, Iterable, Type


def resource_path(*parts):
    pkg_dir = os.path.split(os.path.realpath(__file__))[0]
    return os.path.join(pkg_dir, *parts)


def varnames(method: Callable) -> Iterable[str]:
    return method.__code__.co_varnames[: method.__code__.co_argcount]


def filtered_dict(d: Dict, allowed_keys: Iterable[str]) -> Dict:
    return {k: v for k, v in d.items() if k in allowed_keys}


def filtered_for_init(d: Dict, cls: Type) -> Dict:
    return filtered_dict(d, varnames(cls.__init__))
