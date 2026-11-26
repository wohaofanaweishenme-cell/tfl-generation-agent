"""Kaplan-Meier plotter (conventions v1.0 section 8, figure_plot contract).

plot(spec, data=None) -> matplotlib Figure
  data=None : labelled empty plotting frame (the shell): axis titles and units, legend entries,
              number-at-risk rows with placeholders. No curves, no data points.
  data      : DataFrame with columns time, event, group (see FIG_KAPLAN_MEIER.figure_plot.data_contract).
              Not implemented yet (implementation_status = shell_only).
"""
import textwrap

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402

LINESTYLES = ["-", "--", "-.", ":"]


def _text(slot):
    if not slot:
        return ""
    v = slot.get("value")
    if slot.get("status") in ("unresolved", "conflict"):
        return "<<UNRESOLVED: %s | %s>>" % (v or "value required", slot.get("question_id", "Q???"))
    return "" if v is None else str(v)


def plot(spec, data=None, style=None):
    if data is not None:
        raise NotImplementedError("FIG_KAPLAN_MEIER is shell_only; data plotting is a later step.")
    fig_spec = spec["figure"]
    lay = (style or {}).get("figure_layout", {"width_in": 9.0, "height_in": 5.2})
    font = (style or {}).get("page", {}).get("font", "Courier New")
    plt.rcParams["font.family"] = "monospace"
    plt.rcParams["font.monospace"] = [font, "Courier", "DejaVu Sans Mono"]
    risk = bool(fig_spec.get("risk_table", {}).get("value"))
    groups = fig_spec["legend"]["value"] or []

    fig = plt.figure(figsize=(lay["width_in"], lay["height_in"]), dpi=200, facecolor="white")
    left = 0.30 if risk else 0.12
    if risk:
        ax = fig.add_axes([left, 0.36, 0.96 - left, 0.58])
        rax = fig.add_axes([left, 0.04, 0.96 - left, 0.18])
    else:
        ax = fig.add_axes([left, 0.14, 0.96 - left, 0.80])
        rax = None

    ax.set_xlim(0, 10)
    ax.set_ylim(0, 1.0)
    ax.set_yticks([0, 0.2, 0.4, 0.6, 0.8, 1.0])
    ax.set_xticks(range(0, 11, 2))
    ax.set_xticklabels(["x"] * 6)
    ax.set_xlabel(_text(fig_spec["x_axis"]["label"]), fontsize=9)
    ax.set_ylabel(_text(fig_spec["y_axis"]["label"]), fontsize=9)
    ax.tick_params(labelsize=8)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)

    handles = [Line2D([0], [0], color="black", linestyle=LINESTYLES[i % 4], lw=1.2) for i in range(len(groups))]
    if fig_spec.get("censor_marks", {}).get("value"):
        handles.append(Line2D([0], [0], color="black", marker="+", linestyle="None", markersize=8))
        groups = groups + ["Censored"]
    if handles:
        ax.legend(handles, [textwrap.fill(g, 48) for g in groups], loc="upper right", fontsize=7, frameon=False)

    if rax is not None:
        rax.set_xlim(ax.get_xlim())
        rax.axis("off")
        rows = fig_spec["legend"]["value"] or []
        rax.text(-0.02, 1.05, "Number at risk", transform=rax.transAxes, ha="right", va="bottom", fontsize=8, fontweight="bold")
        for i, g in enumerate(rows):
            y = 0.8 - i * (0.8 / max(1, len(rows)))
            label = textwrap.fill(g.split(" (N=")[0], 34)
            rax.text(-0.02, y, label, transform=rax.transAxes, ha="right", va="center", fontsize=7, linespacing=1.0)
            for xt in range(0, 11, 2):
                rax.text(xt, y, "xx", transform=rax.get_xaxis_transform(), ha="center", va="center", fontsize=8)
    return fig
