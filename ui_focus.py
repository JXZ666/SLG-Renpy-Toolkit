"""Keyboard focus and activation for CustomTkinter widgets.

CustomTkinter draws buttons and check boxes on canvases that are not part of
Tk's focus traversal by default.  This module gives each visible control a real
focus target, a visible ring, and a keyboard activation path without replacing
any widget or command.  It is deliberately separate from ``appgui`` so the
same rules apply to dynamic controls such as library cards.

Desktop users expect Tab to reach every action.  A mouse-only interface is not
acceptable for a tool that changes files in a game directory.
"""

from __future__ import annotations

import tkinter as tk

import customtkinter as ctk


def _target(widget):
    """The inner Tk widget that can actually take focus."""
    if isinstance(widget, ctk.CTkEntry):
        return getattr(widget, "_entry", None)
    if isinstance(widget, ctk.CTkTextbox):
        return getattr(widget, "_textbox", None)
    if isinstance(widget, (ctk.CTkButton, ctk.CTkCheckBox,
                           ctk.CTkSegmentedButton, ctk.CTkRadioButton)):
        return getattr(widget, "_canvas", None)
    if isinstance(widget, ctk.CTkScrollableFrame):
        # The scroll canvas is a mouse convenience, not a control.  Leaving it
        # in the Tab chain makes keyboard traversal appear to skip the page.
        return None
    if hasattr(widget, "bind"):
        return widget
    return None


def _resolve(widget, color):
    """Resolve a CustomTkinter colour pair for a raw Tk canvas option."""
    if isinstance(color, (tuple, list)) and len(color) == 2:
        try:
            mode = str(ctk.get_appearance_mode()).lower()
        except Exception:  # noqa: BLE001 - fall back to the dark half
            mode = "dark"
        return color[0] if mode == "light" else color[1]
    return color


def _safe_configure(widget, **options):
    try:
        widget.configure(**options)
    except (tk.TclError, ValueError, AttributeError):
        pass
    except Exception:  # noqa: BLE001 - a focus ring must never break the window
        pass


def _ring(widget, target, ring_color, background, visible):
    if target is None:
        return
    if isinstance(widget, (ctk.CTkEntry, ctk.CTkTextbox)):
        _safe_configure(
            widget,
            border_width=2 if visible else getattr(widget, "_rpykit_border_width", 1),
            border_color=(ring_color if visible else
                          getattr(widget, "_rpykit_border_color", background)),
        )
        return
    _safe_configure(
        target,
        highlightthickness=2 if visible else 0,
        highlightcolor=_resolve(widget, ring_color),
        highlightbackground=_resolve(widget, background),
    )


def _activate_button(widget):
    try:
        if str(widget.cget("state")) != "disabled":
            widget.invoke()
    except (tk.TclError, AttributeError, TypeError):
        pass


def _activate_checkbox(widget):
    try:
        if str(widget.cget("state")) != "disabled":
            widget.toggle()
    except (tk.TclError, AttributeError, TypeError):
        pass


def _cycle_segment(widget, delta):
    try:
        values = list(widget.cget("values") or [])
        if not values:
            return
        current = widget.get()
        index = values.index(current) if current in values else 0
        value = values[(index + delta) % len(values)]
        widget.set(value)
        command = getattr(widget, "_command", None)
        if callable(command):
            command(value)
    except (tk.TclError, ValueError, AttributeError, TypeError):
        pass


def install(widget, ring_color, background=None, activate=None):
    """Make ``widget`` reachable by Tab and visibly focused.

    ``ring_color`` and ``background`` may be CustomTkinter colour pairs; the
    values are passed straight through to Tk, which resolves pairs when the
    appearance mode changes.  ``activate`` can override the default action for
    unusual controls.
    """
    target = _target(widget)
    if target is None:
        return None
    _safe_configure(target, takefocus=1)
    if isinstance(widget, (ctk.CTkButton, ctk.CTkCheckBox,
                           ctk.CTkSegmentedButton, ctk.CTkRadioButton)):
        _safe_configure(target, highlightthickness=0,
                        highlightbackground=_resolve(
                            widget, background or "transparent"),
                        highlightcolor=_resolve(widget, ring_color))
    if isinstance(widget, ctk.CTkSegmentedButton):
        # CTk 6 draws real child buttons inside the segmented control.  They
        # would otherwise each become a Tab stop with no focus ring; the outer
        # control handles Left/Right itself.
        for child in widget.winfo_children():
            child_target = _target(child)
            if child_target is not None:
                _safe_configure(child_target, takefocus=0)
    if isinstance(widget, (ctk.CTkEntry, ctk.CTkTextbox)):
        try:
            widget._rpykit_border_width = int(widget.cget("border_width"))
            widget._rpykit_border_color = widget.cget("border_color")
        except (tk.TclError, ValueError, TypeError):
            pass
    widget._rpykit_focus_target = target
    target.bind("<FocusIn>", lambda _event: _ring(
        widget, target, ring_color, background, True), add="+")
    target.bind("<FocusOut>", lambda _event: _ring(
        widget, target, ring_color, background, False), add="+")
    target.bind("<Button-1>", lambda _event: target.focus_set(), add="+")

    if isinstance(widget, ctk.CTkButton):
        target.bind("<Return>", lambda _event: _activate_button(widget), add="+")
        target.bind("<space>", lambda _event: _activate_button(widget), add="+")
    elif isinstance(widget, ctk.CTkCheckBox):
        target.bind("<Return>", lambda _event: _activate_checkbox(widget), add="+")
        target.bind("<space>", lambda _event: _activate_checkbox(widget), add="+")
    elif isinstance(widget, ctk.CTkSegmentedButton):
        target.bind("<Left>", lambda _event: _cycle_segment(widget, -1), add="+")
        target.bind("<Right>", lambda _event: _cycle_segment(widget, 1), add="+")
        target.bind("<Return>", lambda _event: _cycle_segment(widget, 1), add="+")
        target.bind("<space>", lambda _event: _cycle_segment(widget, 1), add="+")
    elif callable(activate):
        target.bind("<Return>", lambda _event: activate(), add="+")
        target.bind("<space>", lambda _event: activate(), add="+")
    return target


def install_many(widgets, ring_color, background=None):
    """Install the same ring on an iterable; returns the successful targets."""
    targets = []
    for widget in widgets:
        target = install(widget, ring_color, background)
        if target is not None:
            targets.append(target)
    return targets


def focus_target(widget):
    """Public inspection helper used by tests and the screenshot verifier."""
    return getattr(widget, "_rpykit_focus_target", _target(widget))
