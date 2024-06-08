import os

from PyQt6.QtGui import QIcon


def resource_path(*parts):
    pkg_dir = os.path.split(os.path.realpath(__file__))[0]
    return os.path.join(pkg_dir, *parts)


def icon_path(icon_basename: str):
    return resource_path("icons", icon_basename)


def read_QIcon(icon_basename: str) -> QIcon:
    if not icon_basename:
        return QIcon()
    return QIcon(icon_path(icon_basename))
