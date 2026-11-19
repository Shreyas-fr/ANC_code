//! Visual Theme for DRDO SIH 26052 Live Defence Dashboard.

use egui::Color32;

pub struct Theme;

impl Theme {
    pub const BG_OBSIDIAN: Color32 = Color32::from_rgb(11, 15, 25);
    pub const BG_SURFACE: Color32 = Color32::from_rgb(18, 24, 38);
    pub const BG_CARD: Color32 = Color32::from_rgb(23, 31, 48);
    pub const BG_INPUT: Color32 = Color32::from_rgb(28, 38, 58);

    pub const BORDER_DEFAULT: Color32 = Color32::from_rgb(38, 52, 78);
    pub const BORDER_SUBTLE: Color32 = Color32::from_rgb(28, 38, 58);

    pub const TEXT_PRIMARY: Color32 = Color32::from_rgb(240, 244, 252);
    pub const TEXT_SECONDARY: Color32 = Color32::from_rgb(148, 163, 184);
    pub const TEXT_MUTED: Color32 = Color32::from_rgb(100, 116, 139);

    pub const ACCENT_CYAN: Color32 = Color32::from_rgb(0, 240, 255);
    pub const ACCENT_AMBER: Color32 = Color32::from_rgb(245, 158, 11);
    pub const ACCENT_GREEN: Color32 = Color32::from_rgb(16, 185, 129);
    pub const ACCENT_RED: Color32 = Color32::from_rgb(239, 68, 68);
    pub const ACCENT_VIOLET: Color32 = Color32::from_rgb(168, 85, 247);
}
