//! Tactical Battery-Level & Power Drain HUD Widget.
//!
//! Provides a military-grade rugged battery telemetry monitor displaying:
//! - Physical Li-ion State of Charge (SoC %) with segmented battery icon.
//! - Terminal voltage under dynamic load, current drain (mA), and total power (mW).
//! - Arrhenius temperature status and internal cell resistance (ESR).
//! - Real-time estimated remaining mission runtime ("Xh YYm REMAINING").
//! - Interactive tactical power mode switcher: Nominal / Low-Power Eco / Emergency Beacon.

use eframe::egui::{self, Color32, Pos2, Rect, Stroke, Vec2};
use crate::ui::theme::Theme;
pub use anc_rust::streaming::battery::{BatteryTelemetry, TacticalPowerMode};

/// Interactive Tactical Battery & Power Management Widget.
#[derive(Debug, Clone, Default)]
pub struct TacticalBatteryWidget {
    pub telemetry: BatteryTelemetry,
    pub is_expanded: bool,
}

impl TacticalBatteryWidget {
    pub fn new() -> Self {
        Self::default()
    }

    /// Updates internal telemetry state from received edge telemetry or simulation.
    pub fn update(&mut self, telem: BatteryTelemetry) {
        self.telemetry = telem;
    }

    /// Renders the battery HUD widget. Returns `Some(TacticalPowerMode)` if the user clicked
    /// to change the operational power mode.
    pub fn show(&mut self, ui: &mut egui::Ui, height: f32) -> Option<TacticalPowerMode> {
        let mut mode_changed = None;

        egui::Frame::none()
            .fill(Theme::BG_CARD)
            .stroke(Stroke::new(1.0_f32, Theme::BORDER_DEFAULT))
            .rounding(8.0)
            .inner_margin(egui::Margin::same(10.0))
            .show(ui, |ui| {
                // Header row
                ui.horizontal(|ui| {
                    ui.label(egui::RichText::new("⚡").color(Theme::ACCENT_AMBER).size(13.0));
                    ui.label(
                        egui::RichText::new("FIELD POWER & DURABILITY")
                            .strong()
                            .size(11.0)
                            .color(Theme::TEXT_PRIMARY),
                    );

                    ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                        let (mode_lbl, mode_col) = match self.telemetry.power_mode {
                            TacticalPowerMode::Nominal => ("NOMINAL", Theme::ACCENT_CYAN),
                            TacticalPowerMode::LowPowerEco => ("ECO SAVER", Theme::ACCENT_GREEN),
                            TacticalPowerMode::EmergencyBeacon => ("BEACON", Theme::ACCENT_RED),
                        };

                        if ui.button(egui::RichText::new(mode_lbl).size(10.0).strong().color(mode_col)).clicked() {
                            let next = match self.telemetry.power_mode {
                                TacticalPowerMode::Nominal => TacticalPowerMode::LowPowerEco,
                                TacticalPowerMode::LowPowerEco => TacticalPowerMode::EmergencyBeacon,
                                TacticalPowerMode::EmergencyBeacon => TacticalPowerMode::Nominal,
                            };
                            self.telemetry.power_mode = next;
                            mode_changed = Some(next);
                        }
                    });
                });

                ui.add_space(6.0);

                // Main battery gauge and telemetry readout
                let (rect, _response) = ui.allocate_exact_size(
                    Vec2::new(ui.available_width(), height.max(70.0)),
                    egui::Sense::hover(),
                );

                let painter = ui.painter_at(rect);

                // Draw physical battery pack icon on left
                let batt_w = 64.0;
                let batt_h = 32.0;
                let batt_x = rect.min.x + 8.0;
                let batt_y = rect.min.y + (rect.height() - batt_h) * 0.5 - 6.0;

                let batt_body = Rect::from_min_size(Pos2::new(batt_x, batt_y), Vec2::new(batt_w, batt_h));
                let terminal_nipple = Rect::from_min_size(
                    Pos2::new(batt_x + batt_w, batt_y + (batt_h - 14.0) * 0.5),
                    Vec2::new(4.0, 14.0),
                );

                // Body border
                painter.rect_stroke(batt_body, 4.0, Stroke::new(1.5_f32, Theme::TEXT_MUTED));
                painter.rect_filled(terminal_nipple, 1.5, Theme::TEXT_MUTED);

                // Fill level segments
                let soc = self.telemetry.soc_pct.clamp(0.0, 100.0);
                let fill_col = if soc > 50.0 {
                    Theme::ACCENT_GREEN
                } else if soc > 20.0 {
                    Theme::ACCENT_AMBER
                } else {
                    Theme::ACCENT_RED
                };

                let inner_padding = 2.5;
                let max_fill_w = batt_w - inner_padding * 2.0;
                let cur_fill_w = max_fill_w * (soc / 100.0);

                if cur_fill_w > 1.0 {
                    let fill_rect = Rect::from_min_size(
                        Pos2::new(batt_x + inner_padding, batt_y + inner_padding),
                        Vec2::new(cur_fill_w, batt_h - inner_padding * 2.0),
                    );
                    painter.rect_filled(fill_rect, 2.5, fill_col);
                }

                // Battery % text inside/over the icon
                let soc_str = format!("{:.0}%", soc);
                painter.text(
                    batt_body.center(),
                    egui::Align2::CENTER_CENTER,
                    soc_str,
                    egui::FontId::monospace(11.0),
                    if soc > 35.0 { Color32::BLACK } else { Theme::TEXT_PRIMARY },
                );

                // Telemetry metrics readout on right side of gauge
                let metrics_x = batt_x + batt_w + 16.0;
                let line_h = 16.0;

                // Line 1: Terminal Voltage and Internal Resistance
                let l1_text = format!(
                    "PACK: {:.2} V  |  ESR: {:.0} mΩ  |  TEMP: {:.1} °C",
                    self.telemetry.terminal_voltage_v,
                    self.telemetry.internal_resistance_mohm,
                    self.telemetry.cell_temp_c,
                );
                painter.text(
                    Pos2::new(metrics_x, rect.min.y + 6.0),
                    egui::Align2::LEFT_TOP,
                    l1_text,
                    egui::FontId::monospace(10.0),
                    Theme::TEXT_SECONDARY,
                );

                // Line 2: Current Drain and Power Consumption
                let l2_text = format!(
                    "DRAIN: {:.0} mA  |  POWER: {:.0} mW",
                    self.telemetry.current_draw_ma,
                    self.telemetry.power_draw_mw,
                );
                painter.text(
                    Pos2::new(metrics_x, rect.min.y + 6.0 + line_h),
                    egui::Align2::LEFT_TOP,
                    l2_text,
                    egui::FontId::monospace(10.0),
                    Theme::TEXT_SECONDARY,
                );

                // Line 3: Prominent Remaining Mission Runtime Countdown
                let hours = self.telemetry.estimated_runtime_hours.floor() as u32;
                let mins = ((self.telemetry.estimated_runtime_hours.fract()) * 60.0).round() as u32;
                let runtime_str = format!("EST. RUNTIME: {}h {:02}m REMAINING", hours, mins);

                let runtime_color = if self.telemetry.estimated_runtime_hours > 4.0 {
                    Theme::ACCENT_GREEN
                } else if self.telemetry.estimated_runtime_hours > 1.5 {
                    Theme::ACCENT_AMBER
                } else {
                    Theme::ACCENT_RED
                };

                painter.text(
                    Pos2::new(metrics_x, rect.min.y + 6.0 + line_h * 2.0),
                    egui::Align2::LEFT_TOP,
                    runtime_str,
                    egui::FontId::monospace(10.5),
                    runtime_color,
                );
            });

        mode_changed
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_battery_widget_initial_state() {
        let widget = TacticalBatteryWidget::new();
        assert!(widget.telemetry.soc_pct > 80.0);
        assert_eq!(widget.telemetry.power_mode, TacticalPowerMode::Nominal);
    }

    #[test]
    fn test_battery_widget_update() {
        let mut widget = TacticalBatteryWidget::new();
        let telem = BatteryTelemetry {
            soc_pct: 45.0,
            terminal_voltage_v: 7.42,
            power_mode: TacticalPowerMode::LowPowerEco,
            ..Default::default()
        };

        widget.update(telem);
        assert_eq!(widget.telemetry.soc_pct, 45.0);
        assert_eq!(widget.telemetry.terminal_voltage_v, 7.42);
        assert_eq!(widget.telemetry.power_mode, TacticalPowerMode::LowPowerEco);
    }

    #[test]
    fn test_battery_widget_headless_context() {
        let mut widget = TacticalBatteryWidget::new();
        let ctx = egui::Context::default();
        let _ = ctx.run(Default::default(), |ctx| {
            egui::CentralPanel::default().show(ctx, |ui| {
                let _ = widget.show(ui, 75.0);
            });
        });
    }
}
