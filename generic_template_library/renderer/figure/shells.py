"""Shell plotters for the non-KM figure templates (conventions v1.0 section 8).

Each function has the contract plot(spec, data=None, style=None) -> matplotlib Figure.
With data=None they draw a labelled empty frame: axis titles and units, legend entries,
panel titles, reference lines and category placeholders. No curves, bars, boxes or points.
Data plotting is a later step (template figure_plot.implementation_status = shell_only).
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
    if isinstance(v, list):
        v = ", ".join(v)
    if slot.get("status") in ("unresolved", "conflict"):
        return "<<UNRESOLVED: %s | %s>>" % (v or "value required", slot.get("question_id", "Q???"))
    return "" if v is None else str(v)


def _values(slot):
    return list((slot or {}).get("value") or [])


def _setup(spec, style, n_panels):
    lay = (style or {}).get("figure_layout", {"width_in": 9.0, "height_in": 5.2})
    font = (style or {}).get("page", {}).get("font", "Courier New")
    plt.rcParams["font.family"] = "monospace"
    plt.rcParams["font.monospace"] = [font, "Courier", "DejaVu Sans Mono"]
    fig, axes = plt.subplots(1, max(1, n_panels), figsize=(lay["width_in"], lay["height_in"]), dpi=200, facecolor="white", squeeze=False)
    axes = list(axes[0])
    f = spec["figure"]
    for i, ax in enumerate(axes):
        ax.set_xlabel(_text(f["x_axis"]["label"]), fontsize=8)
        if i == 0:
            ax.set_ylabel(_text(f["y_axis"]["label"]), fontsize=8)
        ax.tick_params(labelsize=7)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
    panels = _values(f.get("panels"))
    if len(panels) > 1:
        for ax, title in zip(axes, panels):
            ax.set_title(textwrap.fill(title, 40), fontsize=8)
    return fig, axes


def _ref_lines(ax, spec, axis="y"):
    for ref in _values(spec["figure"].get("reference_lines")):
        try:
            val = float(ref.split("=")[-1].strip().rstrip("%"))
        except ValueError:
            continue
        (ax.axhline if axis == "y" else ax.axvline)(val, color="grey", lw=0.8, ls=":")


def _legend(ax, labels, markers=False):
    if not labels:
        return
    handles = [Line2D([0], [0], color="black", ls=LINESTYLES[i % 4], lw=1.2, marker="o" if markers else None, markersize=3) for i in range(len(labels))]
    ax.legend(handles, [textwrap.fill(l, 44) for l in labels], fontsize=7, frameon=False, loc="upper right")


def _time_axis(ax, n=6):
    ax.set_xlim(0, n - 1)
    ax.set_xticks(range(n))
    ax.set_xticklabels(["[t%d]" % i for i in range(n)])


def plot_summary_over_time(spec, data=None, style=None):
    if data is not None:
        raise NotImplementedError("shell_only")
    f = spec["figure"]
    panels = _values(f.get("panels")) or ["single panel"]
    fig, axes = _setup(spec, style, len(panels))
    for ax, title in zip(axes, panels):
        _time_axis(ax)
        if "log" in title.lower():
            ax.set_yscale("log")
            ax.set_ylim(1, 1000)
        else:
            ax.set_ylim(0, 1)
            ax.set_yticks([0, 0.25, 0.5, 0.75, 1.0])
            ax.set_yticklabels(["x"] * 5)
        _ref_lines(ax, spec)
    _legend(axes[-1], _values(f["legend"]), markers=True)
    fig.tight_layout()
    return fig


def plot_individual_profile(spec, data=None, style=None):
    if data is not None:
        raise NotImplementedError("shell_only")
    f = spec["figure"]
    panels = _values(f.get("panels")) or ["single panel"]
    fig, axes = _setup(spec, style, len(panels))
    for ax, title in zip(axes, panels):
        _time_axis(ax)
        if "log" in title.lower():
            ax.set_yscale("log")
            ax.set_ylim(1, 1000)
        else:
            ax.set_ylim(-100, 100)
        _ref_lines(ax, spec)
    note = "One line per subject"
    axes[-1].legend([Line2D([0], [0], color="black", lw=0.8)], [note], fontsize=7, frameon=False, loc="upper right")
    fig.tight_layout()
    return fig


def plot_box(spec, data=None, style=None):
    if data is not None:
        raise NotImplementedError("shell_only")
    f = spec["figure"]
    fig, axes = _setup(spec, style, 1)
    ax = axes[0]
    groups = [g.split(" (N=")[0] for g in _values(f["legend"])] or ["[Group]"]
    ax.set_xlim(0.5, len(groups) + 0.5)
    ax.set_xticks(range(1, len(groups) + 1))
    ax.set_xticklabels([textwrap.fill(g, 24) + "\n(N=xx)" for g in groups])
    ax.set_ylim(-100, 100)
    _ref_lines(ax, spec)
    fig.tight_layout()
    return fig


def plot_waterfall(spec, data=None, style=None):
    if data is not None:
        raise NotImplementedError("shell_only")
    f = spec["figure"]
    panels = _values(f.get("panels")) or ["single panel"]
    fig, axes = _setup(spec, style, len(panels))
    for ax in axes:
        ax.set_xlim(0, 20)
        ax.set_xticks([])
        ax.set_ylim(-100, 100)
        ax.axhline(0, color="black", lw=0.8)
        _ref_lines(ax, spec)
    cats = _values(f.get("annotations"))
    if cats:
        axes[-1].legend([plt.Rectangle((0, 0), 1, 1, fc="white", ec="black", hatch=h) for h, _ in zip(["", "///", "...", "xx", "\\\\"], cats)],
                        cats, fontsize=7, frameon=False, loc="upper right", title="Bar fill", title_fontsize=7)
    fig.tight_layout()
    return fig


def plot_tornado(spec, data=None, style=None):
    if data is not None:
        raise NotImplementedError("shell_only")
    f = spec["figure"]
    groups = [g.split(" (N=")[0] for g in _values(f["legend"])][:2] or ["[Group A]", "[Group B]"]
    fig, axes = _setup(spec, style, 1)
    ax = axes[0]
    terms = ["[Preferred Term %d]" % i for i in range(1, 9)]
    ax.set_ylim(-0.5, len(terms) - 0.5)
    ax.set_yticks(range(len(terms)))
    ax.set_yticklabels(terms[::-1], fontsize=7)
    ax.set_xlim(-100, 100)
    ax.set_xticks([-100, -50, 0, 50, 100])
    ax.set_xticklabels(["xx", "xx", "0", "xx", "xx"])
    ax.axvline(0, color="black", lw=0.8)
    ax.text(0.25, 1.02, textwrap.fill(groups[0], 30), transform=ax.transAxes, ha="center", fontsize=7)
    if len(groups) > 1:
        ax.text(0.75, 1.02, textwrap.fill(groups[1], 30), transform=ax.transAxes, ha="center", fontsize=7)
    fig.tight_layout()
    return fig
