//! 3D Tactical Battlefield Acoustic Waterfall (3D Spectrogram Mesh).
//!
//! Developed for SIH 26052 Tactical Audio Systems.
//!
//! Renders a real-time 3D isometric/perspective terrain mesh displaying a rolling
//! 40 frames of 32 frequency bands.
//!
//! Features:
//! - Real-time 3D coordinate transformation with user interactive pitch/yaw mouse rotation.
//! - Elevation mapping proportional to instantaneous spectral energy (dBFS).
//! - Tactical military phosphor coloring:
//!   - Deep obsidian (#080B12) for silent noise floor (< -70 dBFS)
//!   - Electric cyan (#00F0FF) for speech formants (-50 to -25 dBFS)
//!   - Glowing amber (#FFB000) for vehicle harmonics (-25 to -12 dBFS)
//!   - Burning crimson (#FF003C) for gunfire / shockwave kurtosis bursts (> -12 dBFS).
//! - Back-to-front depth sorted polygon rasterization with tactical phosphor wireframe accents.

use super::theme::Theme;
use egui::{epaint::PathShape, Color32, Margin, Pos2, Rounding, Sense, Stroke, Ui, Vec2};

pub const WATERFALL_3D_FRAMES: usize = 40;
pub const WATERFALL_3D_BANDS: usize = 32;

/// Tactical 3D Spectrogram Terrain Mesh.
pub struct Waterfall3dMesh {
    /// Rolling buffer of historical frames: [WATERFALL_3D_FRAMES][WATERFALL_3D_BANDS]
    history: [[f32; WATERFALL_3D_BANDS]; WATERFALL_3D_FRAMES],
    head: usize,
    count: usize,
    /// Camera pitch angle in radians (elevation above ground plane).
    pub pitch: f32,
    /// Camera yaw angle in radians (azimuthal rotation).
    pub yaw: f32,
    /// Vertical elevation gain scale.
    pub z_scale: f32,
    /// Show wireframe overlay.
    pub show_wireframe: bool,
}

impl Default for Waterfall3dMesh {
    fn default() -> Self {
        Self::new()
    }
}

#[derive(Clone, Copy)]
struct CameraAngles {
    cos_yaw: f32,
    sin_yaw: f32,
    cos_pitch: f32,
    sin_pitch: f32,
    center: Pos2,
    scale: f32,
}

impl Waterfall3dMesh {
    /// Creates a new Waterfall3dMesh initialized with default tactical viewing angles.
    pub fn new() -> Self {
        Self {
            history: [[-90.0f32; WATERFALL_3D_BANDS]; WATERFALL_3D_FRAMES],
            head: 0,
            count: 0,
            pitch: 0.65, // ~37 degrees elevation
            yaw: -0.45,  // ~-25 degrees yaw
            z_scale: 1.0,
            show_wireframe: true,
        }
    }

    /// Resets the 3D viewing angle to tactical default.
    pub fn reset_view(&mut self) {
        self.pitch = 0.65;
        self.yaw = -0.45;
        self.z_scale = 1.0;
    }

    /// Pushes a new FFT magnitude frame (dBFS) into the 3D waterfall history.
    pub fn push_frame(&mut self, spectrum_db: &[f64]) {
        if spectrum_db.is_empty() {
            return;
        }

        let mut band_energies = [-90.0f32; WATERFALL_3D_BANDS];
        let bins_per_band = spectrum_db.len() as f32 / WATERFALL_3D_BANDS as f32;

        for (b, energy) in band_energies.iter_mut().enumerate() {
            let start = (b as f32 * bins_per_band) as usize;
            let end = (((b + 1) as f32 * bins_per_band) as usize).min(spectrum_db.len());
            if start < end {
                let max_in_band = spectrum_db[start..end]
                    .iter()
                    .fold(-120.0f64, |m, &v| m.max(v));
                *energy = max_in_band as f32;
            }
        }

        self.history[self.head] = band_energies;
        self.head = (self.head + 1) % WATERFALL_3D_FRAMES;
        if self.count < WATERFALL_3D_FRAMES {
            self.count += 1;
        }
    }

    /// Maps dBFS magnitude to tactical military phosphor color.
    pub fn tactical_color(db: f32) -> Color32 {
        if db <= -70.0 {
            // Deep obsidian #080B12
            Color32::from_rgb(8, 11, 18)
        } else if db <= -50.0 {
            // Gradient from obsidian to electric cyan
            let t = (db + 70.0) / 20.0;
            Color32::from_rgb(
                (8.0 + t * (0.0 - 8.0)) as u8,
                (11.0 + t * (240.0 - 11.0)) as u8,
                (18.0 + t * (255.0 - 18.0)) as u8,
            )
        } else if db <= -25.0 {
            // Electric cyan #00F0FF to glowing amber #FFB000
            let t = (db + 50.0) / 25.0;
            Color32::from_rgb(
                (t * 255.0) as u8,
                (240.0 - t * (240.0 - 176.0)) as u8,
                (255.0 * (1.0 - t)) as u8,
            )
        } else if db <= -12.0 {
            // Glowing amber #FFB000 to burning crimson #FF003C
            let t = (db + 25.0) / 13.0;
            Color32::from_rgb(255, (176.0 * (1.0 - t)) as u8, (t * 60.0) as u8)
        } else {
            // Burning crimson #FF003C for intense combat blasts
            let t = ((db + 12.0) / 12.0).clamp(0.0, 1.0);
            Color32::from_rgb(255, (t * 80.0) as u8, (60.0 + t * 40.0) as u8)
        }
    }

    /// Projects a 3D coordinate (x, y, z) to 2D screen coordinate (Pos2) with depth y_depth.
    fn project_3d(x: f32, y: f32, z: f32, cam: &CameraAngles) -> (Pos2, f32) {
        // 1. Yaw rotation around Z axis
        let x_yaw = x * cam.cos_yaw - y * cam.sin_yaw;
        let y_yaw = x * cam.sin_yaw + y * cam.cos_yaw;
        let z_yaw = z;

        // 2. Pitch rotation around X axis
        let y_pitch = y_yaw * cam.cos_pitch - z_yaw * cam.sin_pitch;
        let z_pitch = y_yaw * cam.sin_pitch + z_yaw * cam.cos_pitch;
        let x_pitch = x_yaw;

        // 3. Perspective depth factor
        let dist = 400.0;
        let depth_factor = dist / (dist + y_pitch);

        let screen_x = cam.center.x + x_pitch * cam.scale * depth_factor;
        let screen_y = cam.center.y - z_pitch * cam.scale * depth_factor;

        (Pos2::new(screen_x, screen_y), y_pitch)
    }

    /// Renders the 3D waterfall spectrogram mesh within the egui UI.
    pub fn show(&mut self, ui: &mut Ui, height: f32) {
        egui::Frame::none()
            .fill(Theme::BG_CARD)
            .stroke(Stroke::new(1.0_f32, Theme::BORDER_DEFAULT))
            .rounding(Rounding::same(8.0))
            .inner_margin(Margin::same(10.0))
            .show(ui, |ui| {
                ui.horizontal(|ui| {
                    ui.label(
                        egui::RichText::new("●")
                            .color(Theme::ACCENT_CYAN)
                            .size(11.0),
                    );
                    ui.label(
                        egui::RichText::new("3D TACTICAL BATTLEFIELD SPECTRAL TERRAIN MESH")
                            .strong()
                            .size(12.0)
                            .color(Theme::TEXT_PRIMARY),
                    );
                    ui.label(
                        egui::RichText::new("[40 Frames × 32 Perceptual Bands]")
                            .size(10.0)
                            .color(Theme::TEXT_MUTED),
                    );

                    ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                        if ui
                            .button(
                                egui::RichText::new("↺ RESET VIEW")
                                    .size(10.0)
                                    .color(Theme::TEXT_SECONDARY),
                            )
                            .clicked()
                        {
                            self.reset_view();
                        }

                        let wire_label = if self.show_wireframe {
                            "WIREFRAME: ON"
                        } else {
                            "WIREFRAME: OFF"
                        };
                        if ui
                            .button(
                                egui::RichText::new(wire_label)
                                    .size(10.0)
                                    .color(Theme::ACCENT_CYAN),
                            )
                            .clicked()
                        {
                            self.show_wireframe = !self.show_wireframe;
                        }

                        ui.label(
                            egui::RichText::new("🖱 DRAG TO ROTATE 3D")
                                .size(9.5)
                                .monospace()
                                .color(Theme::ACCENT_AMBER),
                        );
                    });
                });

                ui.add_space(6.0);

                let available_width = ui.available_width();
                let desired_size = Vec2::new(available_width, height);
                let (rect, response) = ui.allocate_exact_size(desired_size, Sense::drag());

                // Interactive mouse drag to rotate pitch & yaw
                if response.dragged() {
                    let delta = response.drag_delta();
                    self.yaw += delta.x * 0.008;
                    self.pitch = (self.pitch + delta.y * 0.008).clamp(0.15, 1.45);
                }

                if ui.is_rect_visible(rect) {
                    let painter = ui.painter_at(rect);

                    // Background dark obsidian grid
                    painter.rect_filled(rect, Rounding::same(6.0), Color32::from_rgb(6, 8, 14));

                    let center = rect.center();
                    let cos_yaw = self.yaw.cos();
                    let sin_yaw = self.yaw.sin();
                    let cos_pitch = self.pitch.cos();
                    let sin_pitch = self.pitch.sin();

                    let cam = CameraAngles {
                        cos_yaw,
                        sin_yaw,
                        cos_pitch,
                        sin_pitch,
                        center,
                        scale: 1.0,
                    };

                    let mesh_width = (rect.width() * 0.70).min(320.0);
                    let mesh_depth = (rect.height() * 1.1).min(200.0);
                    let mesh_height = 65.0 * self.z_scale;

                    let num_frames = WATERFALL_3D_FRAMES;
                    let num_bands = WATERFALL_3D_BANDS;

                    // Pre-project all grid vertices to 2D
                    // [frame_idx][band_idx] -> (Pos2, depth)
                    let mut proj_grid =
                        [[(Pos2::ZERO, 0.0f32); WATERFALL_3D_BANDS]; WATERFALL_3D_FRAMES];
                    let mut energy_grid = [[-90.0f32; WATERFALL_3D_BANDS]; WATERFALL_3D_FRAMES];

                    for t in 0..num_frames {
                        // Chronological indexing: older frames in back, newest in front
                        let hist_idx = (self.head + num_frames - 1 - t) % num_frames;
                        let frame_db = self.history[hist_idx];

                        // Normalize y from -0.5 (back) to +0.5 (front)
                        let y_norm = (t as f32 / (num_frames - 1) as f32) - 0.5;
                        let y_3d = y_norm * mesh_depth;

                        for b in 0..num_bands {
                            // Normalize x from -0.5 (low freq) to +0.5 (high freq)
                            let x_norm = (b as f32 / (num_bands - 1) as f32) - 0.5;
                            let x_3d = x_norm * mesh_width;

                            let db = frame_db[b];
                            energy_grid[t][b] = db;

                            // Elevation z normalized from 0.0 to 1.0
                            let z_norm = ((db + 85.0) / 80.0).clamp(0.0, 1.0);
                            let z_3d = z_norm * mesh_height;

                            let (p, depth) = Self::project_3d(x_3d, y_3d, z_3d, &cam);
                            proj_grid[t][b] = (p, depth);
                        }
                    }

                    // Render quads back-to-front (depth sorted)
                    // Construct quad primitives:
                    struct QuadPrimitive {
                        p0: Pos2,
                        p1: Pos2,
                        p2: Pos2,
                        p3: Pos2,
                        mean_depth: f32,
                        color: Color32,
                    }

                    let mut quads = Vec::with_capacity((num_frames - 1) * (num_bands - 1));

                    for t in 0..(num_frames - 1) {
                        for b in 0..(num_bands - 1) {
                            let (p0, d0) = proj_grid[t][b];
                            let (p1, d1) = proj_grid[t][b + 1];
                            let (p2, d2) = proj_grid[t + 1][b + 1];
                            let (p3, d3) = proj_grid[t + 1][b];

                            let mean_depth = (d0 + d1 + d2 + d3) * 0.25;
                            let mean_db = (energy_grid[t][b]
                                + energy_grid[t][b + 1]
                                + energy_grid[t + 1][b + 1]
                                + energy_grid[t + 1][b])
                                * 0.25;

                            let color = Self::tactical_color(mean_db);

                            quads.push(QuadPrimitive {
                                p0,
                                p1,
                                p2,
                                p3,
                                mean_depth,
                                color,
                            });
                        }
                    }

                    // Sort back-to-front: largest mean_depth first (furthest away)
                    quads.sort_by(|a, b| {
                        b.mean_depth
                            .partial_cmp(&a.mean_depth)
                            .unwrap_or(std::cmp::Ordering::Equal)
                    });

                    // Draw depth-sorted filled quads and optional wireframe accents
                    let wire_stroke =
                        Stroke::new(0.6_f32, Color32::from_rgba_unmultiplied(0, 240, 255, 35));

                    for quad in quads {
                        let fill_rgba = Color32::from_rgba_unmultiplied(
                            quad.color.r(),
                            quad.color.g(),
                            quad.color.b(),
                            185,
                        );

                        // Render shaded polygon face
                        painter.add(PathShape::convex_polygon(
                            vec![quad.p0, quad.p1, quad.p2, quad.p3],
                            fill_rgba,
                            if self.show_wireframe {
                                wire_stroke
                            } else {
                                Stroke::NONE
                            },
                        ));
                    }

                    // Render tactical legend and axis labels
                    let legend_y = rect.bottom() - 16.0;
                    painter.text(
                        Pos2::new(rect.left() + 10.0, legend_y),
                        egui::Align2::LEFT_CENTER,
                        "0 Hz",
                        egui::FontId::monospace(9.0),
                        Theme::TEXT_MUTED,
                    );
                    painter.text(
                        Pos2::new(rect.right() - 10.0, legend_y),
                        egui::Align2::RIGHT_CENTER,
                        "8000 Hz",
                        egui::FontId::monospace(9.0),
                        Theme::TEXT_MUTED,
                    );
                    painter.text(
                        Pos2::new(center.x, legend_y),
                        egui::Align2::CENTER_CENTER,
                        "◀ TIME (40 FRAMES) / FREQUENCY (32 BANDS) ▶",
                        egui::FontId::monospace(9.0),
                        Theme::TEXT_MUTED,
                    );
                }
            });
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_waterfall_3d_push_frame() {
        let mut mesh = Waterfall3dMesh::new();
        assert_eq!(mesh.count, 0);

        let spectrum = vec![-40.0f64; 257];
        mesh.push_frame(&spectrum);

        assert_eq!(mesh.count, 1);
        assert!((mesh.history[0][0] - (-40.0)).abs() < 1.0);
    }

    #[test]
    fn test_waterfall_3d_color_mapping() {
        // Silent floor
        let c_silent = Waterfall3dMesh::tactical_color(-80.0);
        assert_eq!(c_silent, Color32::from_rgb(8, 11, 18));

        // Formant cyan
        let c_cyan = Waterfall3dMesh::tactical_color(-35.0);
        assert!(c_cyan.g() > 100);

        // Amber
        let c_amber = Waterfall3dMesh::tactical_color(-18.0);
        assert_eq!(c_amber.r(), 255);

        // Crimson blast
        let c_blast = Waterfall3dMesh::tactical_color(-5.0);
        assert_eq!(c_blast.r(), 255);
        assert!(c_blast.b() > 50);
    }

    #[test]
    fn test_waterfall_3d_reset_view() {
        let mut mesh = Waterfall3dMesh::new();
        mesh.pitch = 1.2;
        mesh.yaw = 0.8;
        mesh.reset_view();
        assert!((mesh.pitch - 0.65).abs() < 0.01);
        assert!((mesh.yaw - (-0.45)).abs() < 0.01);
    }
}
