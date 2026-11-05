#!/usr/bin/env python3
"""系列顺序与配色（对比图用）。

约定写在 config.yaml 的 series 段：

    series:
      order: ["Ru", "3%", "4.5%"]      # 图例从上到下的顺序
      colors:
        Ru: "#00ff00"
        "3%": "#ff0000"
        "4.5%": "#0000ff"

匹配规则：先按目录名/标签全等匹配，再按“名称里包含该关键词”匹配。
没有配到的样品保持原顺序，沿用 matplotlib 默认色循环。
"""


def _series_cfg(cfg):
    sec = (cfg or {}).get("series") or {}
    order = [str(x) for x in (sec.get("order") or [])]
    colors = {str(k): str(v) for k, v in (sec.get("colors") or {}).items()}
    return order, colors


def _match_key(name, order):
    """返回 name 命中的关键词下标，未命中返回 None。"""
    if name in order:
        return order.index(name)
    hits = [(i, key) for i, key in enumerate(order) if key and key in name]
    if not hits:
        return None
    hits.sort(key=lambda item: (-len(item[1]), item[0]))
    return hits[0][0]


def sort_curves(curves, cfg, key="folder"):
    """按 series.order 排序；未配置时保持调用前的顺序。"""
    order, _ = _series_cfg(cfg)
    if not order:
        return curves
    indexed = []
    for pos, c in enumerate(curves):
        idx = _match_key(str(c.get(key, "")), order)
        indexed.append((0 if idx is not None else 1, idx if idx is not None else 0, pos, c))
    indexed.sort(key=lambda item: (item[0], item[1], item[2]))
    return [item[3] for item in indexed]


def color_of(cfg, name):
    """返回该样品配置的颜色；未配置返回 None（交给默认色循环）。"""
    order, colors = _series_cfg(cfg)
    name = str(name)
    if name in colors:
        return colors[name]
    for key in order:
        if key in name and key in colors:
            return colors[key]
    return None
