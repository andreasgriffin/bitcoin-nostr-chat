from typing import Callable, Dict, Iterable, Type


def varnames(method: Callable) -> Iterable[str]:
    return method.__code__.co_varnames[: method.__code__.co_argcount]


def filtered_dict(d: Dict, allowed_keys: Iterable[str]) -> Dict:
    return {k: v for k, v in d.items() if k in allowed_keys}


def filtered_for_init(d: Dict, cls: Type) -> Dict:
    return filtered_dict(d, varnames(cls.__init__))
