//! Metric Cards, HUD Beacons, and Telemetry Widgets.

use egui::{Color32, Margin, Rounding, Stroke, Ui};
use super::theme::Theme;

pub struct MetricCard;

impl MetricCard {
    /// Renders an elevated card with top accent stripe and high-contrast typography.
    pub fn show(
        ui: &mut Ui,
        title: &str,
        value: &str,
        subtitle: &str,
        accent_color: Color32,
    ) {
        egui::Frame::none()
            .fill(Theme::BG_CARD)
            .stroke(Stroke::new(1.0_f32, Theme::BORDER_DEFAULT))
            .rounding(Rounding::same(8.0))
            .inner_margin(Margin::symmetric(12.0, 10.0))
            .show(ui, |ui| {
                ui.set_min_width(148.0);
                ui.set_max_width(180.0);

                // Top miniature indicator bar
                let (rect, _) = ui.allocate_exact_size(egui::vec2(28.0, 3.0), egui::Sense::hover());
                ui.painter().rect_filled(rect, Rounding::same(1.5), accent_color);
                ui.add_space(4.0);

                ui.label(
                    egui::RichText::new(title)
                        .size(10.0)
                        .strong()
                        .color(Theme::TEXT_MUTED),
                );
                ui.add_space(1.0);

                ui.label(
                    egui::RichText::new(value)
                        .size(19.0)
                        .strong()
                        .color(Theme::TEXT_PRIMARY),
                );
                ui.add_space(1.0);

                ui.label(
                    egui::RichText::new(subtitle)
                        .size(9.5)
                        .color(accent_color),
                );
            });
    }
}

pub struct VadBeacon;

impl VadBeacon {
    /// Renders glowing real-time Voice Activity Detection beacon.
    pub fn show(ui: &mut Ui, is_speech: bool, spp: f32) {
        let (color, bg, text) = if is_speech {
            (
                Theme::ACCENT_GREEN,
                Color32::from_rgb(4, 50, 36),
                format!("VOICE ACTIVE ({:.0}%)", spp * 100.0),
            )
        } else {
            (
                Theme::TEXT_MUTED,
                Color32::from_rgb(18, 25, 40),
                "NOISE PAUSE".to_string(),
            )
        };

        egui::Frame::none()
            .fill(bg)
            .stroke(Stroke::new(1.0_f32, color))
            .rounding(Rounding::same(6.0))
            .inner_margin(Margin::symmetric(10.0, 5.0))
            .show(ui, |ui| {
                ui.horizontal(|ui| {
                    ui.label(egui::RichText::new("●").color(color).size(11.0));
                    ui.label(egui::RichText::new(text).strong().size(11.0).color(color));
                });
            });
    }
}

pub struct StatusBadge;

impl StatusBadge {
    pub fn show(ui: &mut Ui, status: &str) {
        let (color, bg, label) = match status {
            "LIVE" => (Theme::ACCENT_GREEN, Color32::from_rgb(6, 60, 45), "LIVE STREAM"),
            "DEGRADED" => (Theme::ACCENT_AMBER, Color32::from_rgb(80, 40, 10), "STREAM DEGRADED"),
            "DEMO" => (Theme::ACCENT_VIOLET, Color32::from_rgb(60, 20, 95), "DEMO MODE"),
            _ => (Theme::ACCENT_RED, Color32::from_rgb(80, 15, 25), "OFFLINE"),
        };

        egui::Frame::none()
            .fill(bg)
            .stroke(Stroke::new(1.0_f32, color))
            .rounding(Rounding::same(6.0))
            .inner_margin(Margin::symmetric(10.0, 5.0))
            .show(ui, |ui| {
                ui.horizontal(|ui| {
                    ui.label(egui::RichText::new("●").color(color).size(10.0));
                    ui.label(egui::RichText::new(label).strong().color(color).size(11.5));
                });
            });
    }
}
