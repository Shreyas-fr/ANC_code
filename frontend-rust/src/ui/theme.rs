//! Tactical Visual Theme and Design System for DRDO SIH 26052 Mission Control.
//!
//! Military-aerospace dark theme with obsidian depth, glowing HUD accents,
//! and high-contrast accessibility.

use egui::{Color32, Context, Rounding, Stroke, Style, Visuals};

pub struct Theme;

impl Theme {
    // Deep Obsidian Dark Space Palette
    pub const BG_VOID: Color32 = Color32::from_rgb(8, 11, 18);
    pub const BG_SURFACE: Color32 = Color32::from_rgb(13, 18, 30);
    pub const BG_CARD: Color32 = Color32::from_rgb(18, 25, 42);
    pub const BG_CARD_HOVER: Color32 = Color32::from_rgb(25, 35, 58);
    pub const BG_INPUT: Color32 = Color32::from_rgb(22, 30, 50);

    // Luminous Borders and Grid Dividers
    pub const BORDER_DEFAULT: Color32 = Color32::from_rgb(32, 45, 72);
    pub const BORDER_HIGHLIGHT: Color32 = Color32::from_rgb(50, 72, 112);
    pub const BORDER_SUBTLE: Color32 = Color32::from_rgb(22, 32, 52);

    // High-Contrast Technical Typography
    pub const TEXT_PRIMARY: Color32 = Color32::from_rgb(245, 248, 255);
    pub const TEXT_SECONDARY: Color32 = Color32::from_rgb(156, 172, 198);
    pub const TEXT_MUTED: Color32 = Color32::from_rgb(102, 120, 148);

    // Tactical Neon Status & Signal Accents
    pub const ACCENT_CYAN: Color32 = Color32::from_rgb(0, 229, 255);   // Enhanced Speech Output
    pub const ACCENT_AMBER: Color32 = Color32::from_rgb(255, 179, 0);  // Raw Sensor Feed
    pub const ACCENT_GREEN: Color32 = Color32::from_rgb(0, 230, 118);  // Qualified / Live / Voice
    pub const ACCENT_RED: Color32 = Color32::from_rgb(255, 23, 68);    // Alert / Packet Loss
    pub const ACCENT_VIOLET: Color32 = Color32::from_rgb(168, 85, 247); // Neural / Compute RTF
    pub const ACCENT_BLUE: Color32 = Color32::from_rgb(41, 121, 255);

    /// Applies global tactical aerospace dark style to egui context.
    pub fn apply_to_context(ctx: &Context) {
        let mut visuals = Visuals::dark();

        visuals.override_text_color = Some(Self::TEXT_PRIMARY);
        visuals.panel_fill = Self::BG_VOID;
        visuals.window_fill = Self::BG_SURFACE;
        visuals.faint_bg_color = Self::BG_CARD;
        visuals.extreme_bg_color = Self::BG_VOID;

        // Interactive widgets (buttons, sliders)
        visuals.widgets.noninteractive.bg_fill = Self::BG_CARD;
        visuals.widgets.noninteractive.bg_stroke = Stroke::new(1.0_f32, Self::BORDER_DEFAULT);
        visuals.widgets.noninteractive.rounding = Rounding::same(6.0);

        visuals.widgets.inactive.bg_fill = Self::BG_CARD;
        visuals.widgets.inactive.bg_stroke = Stroke::new(1.0_f32, Self::BORDER_DEFAULT);
        visuals.widgets.inactive.rounding = Rounding::same(6.0);

        visuals.widgets.hovered.bg_fill = Self::BG_CARD_HOVER;
        visuals.widgets.hovered.bg_stroke = Stroke::new(1.0_f32, Self::BORDER_HIGHLIGHT);
        visuals.widgets.hovered.rounding = Rounding::same(6.0);

        visuals.widgets.active.bg_fill = Self::BG_INPUT;
        visuals.widgets.active.bg_stroke = Stroke::new(1.5_f32, Self::ACCENT_CYAN);
        visuals.widgets.active.rounding = Rounding::same(6.0);

        visuals.selection.bg_fill = Self::ACCENT_BLUE;
        visuals.selection.stroke = Stroke::new(1.0_f32, Self::ACCENT_CYAN);

        let style = Style {
            visuals,
            ..Style::default()
        };

        ctx.set_style(style);
    }
}
