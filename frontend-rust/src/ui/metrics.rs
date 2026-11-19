//! Metric Cards and Instrumentation Widgets for the Mission Control Dashboard.

use egui::{Color32, Ui};
use super::theme::Theme;

pub struct MetricCard;

impl MetricCard {
    pub fn show(
        ui: &mut Ui,
        title: &str,
        value: &str,
        subtitle: &str,
        value_color: Color32,
    ) {
        egui::Frame::none()
            .fill(Theme::BG_CARD)
            .stroke(egui::Stroke::new(1.0_f32, Theme::BORDER_DEFAULT))
            .rounding(6.0)
            .inner_margin(egui::Margin::same(10.0))
            .show(ui, |ui| {
                ui.set_min_width(140.0);
                ui.label(egui::RichText::new(title).size(10.0).color(Theme::TEXT_MUTED));
                ui.add_space(2.0);
                ui.label(egui::RichText::new(value).size(18.0).strong().color(value_color));
                ui.add_space(2.0);
                ui.label(egui::RichText::new(subtitle).size(9.0).color(Theme::TEXT_SECONDARY));
            });
    }
}

pub struct StatusBadge;

impl StatusBadge {
    pub fn show(ui: &mut Ui, status: &str) {
        let (color, bg) = match status {
            "LIVE" => (Theme::ACCENT_GREEN, Color32::from_rgb(6, 78, 59)),
            "DEGRADED" => (Theme::ACCENT_AMBER, Color32::from_rgb(120, 53, 15)),
            "DEMO" => (Theme::ACCENT_VIOLET, Color32::from_rgb(88, 28, 135)),
            _ => (Theme::ACCENT_RED, Color32::from_rgb(127, 29, 29)),
        };

        egui::Frame::none()
            .fill(bg)
            .stroke(egui::Stroke::new(1.0_f32, color))
            .rounding(4.0)
            .inner_margin(egui::Margin::symmetric(10.0, 4.0))
            .show(ui, |ui| {
                ui.horizontal(|ui| {
                    ui.label(egui::RichText::new("●").color(color).size(10.0));
                    ui.label(egui::RichText::new(status).strong().color(color).size(12.0));
                });
            });
    }
}
