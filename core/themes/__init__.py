"""
Terminal-native palette.

Zani does not ship colours. Every value here is an ANSI slot, so the actual
hues come from whatever the user's terminal defines — kitty's `font_family` and
colour0..15, alacritty's theme, a tmux palette, whatever. Backgrounds stay
transparent so the terminal's own background (including transparency and
background images) shows through untouched.

Two naming schemes are needed because the two renderers disagree:
  * `text`/`subtext`/`mauve`/... are Rich markup names, used inside
    `[...]` tags and `rich.style.Style`.
  * `css_*` are Textual CSS values, which require the `ansi_` prefix.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class TuiTheme:
    name: str

    # Rich markup colour names — resolved by the terminal's palette.
    text: str
    subtext: str
    lavender: str
    mauve: str
    sapphire: str
    green: str
    red: str
    peach: str

    # Textual CSS values.
    css_bg: str
    css_fg: str
    css_dim: str
    css_border: str
    css_panel_bg: str  # bottom dock — opaque so chat scrolls underneath

    # Retained so existing call sites keep working; both are terminal defaults.
    @property
    def base(self) -> str:
        return self.css_bg

    @property
    def input_bg(self) -> str:
        return self.css_bg

    @property
    def border(self) -> str:
        return self.css_border

    @property
    def overlay(self) -> str:
        return "default"


TERMINAL = TuiTheme(
    name="terminal",
    text="default",
    subtext="bright_black",
    lavender="blue",
    mauve="magenta",
    sapphire="cyan",
    green="green",
    red="red",
    peach="yellow",
    css_bg="transparent",
    css_fg="ansi_default",
    css_dim="ansi_bright_black",
    css_border="ansi_bright_black",
    css_panel_bg="ansi_default",
)


def get_theme() -> TuiTheme:
    return TERMINAL
