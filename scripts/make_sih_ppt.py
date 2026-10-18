from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.enum.text import PP_ALIGN
from pptx.enum.shapes import MSO_SHAPE
from pptx.dml.color import RGBColor

# Create presentation
prs = Presentation()

# Use a standard slide layout (0 is title, 1 is title and content, 5 is title only, 6 is blank)
title_slide_layout = prs.slide_layouts[0]
content_slide_layout = prs.slide_layouts[1]
blank_slide_layout = prs.slide_layouts[6]

# Define student-made clean theme (e.g. standard dark blue font for titles, black for body)
TITLE_COLOR = RGBColor(0, 51, 102)

def set_title(slide, text):
    title_shape = slide.shapes.title
    title_shape.text = text
    title_shape.text_frame.paragraphs[0].font.color.rgb = TITLE_COLOR
    title_shape.text_frame.paragraphs[0].font.bold = True
    return title_shape

# --- SLIDE 1: TITLE PAGE ---
slide1 = prs.slides.add_slide(title_slide_layout)
title = slide1.shapes.title
subtitle = slide1.placeholders[1]

title.text = "SMART INDIA HACKATHON 2026\nProblem Statement ID: 26052"
title.text_frame.paragraphs[0].font.size = Pt(28)
title.text_frame.paragraphs[0].font.color.rgb = TITLE_COLOR
title.text_frame.paragraphs[0].font.bold = True
title.text_frame.paragraphs[1].font.size = Pt(24)

subtitle.text = (
    "AI/ML-Enabled Adaptive Noise Cancellation for Defence Communication\n\n"
    "Theme: Miscellaneous\n"
    "PS Category: Hardware\n\n"
    "Team ID: [YOUR TEAM ID]\n"
    "Team Name: [YOUR TEAM NAME]"
)

# Add simple visual logic to title slide using shapes
left = Inches(1.5)
top = Inches(6)
width = Inches(1.5)
height = Inches(0.8)

s1 = slide1.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, left, top, width, height)
s1.text = "Noisy Env."
a1 = slide1.shapes.add_shape(MSO_SHAPE.RIGHT_ARROW, left + width + Inches(0.1), top + Inches(0.2), Inches(0.8), Inches(0.4))

s2 = slide1.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, left + width + Inches(1), top, width, height)
s2.text = "AI Processor"
s2.fill.solid()
s2.fill.fore_color.rgb = RGBColor(0, 102, 204)

a2 = slide1.shapes.add_shape(MSO_SHAPE.RIGHT_ARROW, left + 2*width + Inches(1.1), top + Inches(0.2), Inches(0.8), Inches(0.4))
s3 = slide1.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, left + 2*width + Inches(2), top, width, height)
s3.text = "Clear Speech"


# --- SLIDE 2: IDEA TITLE & USERFLOW ---
slide2 = prs.slides.add_slide(blank_slide_layout)
title2 = slide2.shapes.add_textbox(Inches(0.5), Inches(0.2), Inches(9), Inches(1))
title2.text_frame.text = "AI-Powered Adaptive Noise Suppression for Defence Communication"
title2.text_frame.paragraphs[0].font.size = Pt(24)
title2.text_frame.paragraphs[0].font.bold = True
title2.text_frame.paragraphs[0].font.color.rgb = TITLE_COLOR

tx = slide2.shapes.add_textbox(Inches(0.5), Inches(1.2), Inches(9), Inches(2))
tf = tx.text_frame
tf.word_wrap = True
p = tf.add_paragraph()
p.text = "Proposed Solution: A causal, stateful deep-learning speech enhancement system that suppresses stationary, non-stationary and impulsive noise while preserving speech information for low-latency defence communication."
p.font.size = Pt(16)

p2 = tf.add_paragraph()
p2.text = "\nKey Innovation:"
p2.font.bold = True
p2.font.size = Pt(16)

innovations = [
    "Stateful Polar-LSTM maintains temporal context across audio frames.",
    "Predicts magnitude + phase corrections instead of magnitude alone.",
    "Causal processing enables real-time streaming without future audio.",
    "Compact ~1.45M-parameter model for edge deployment."
]
for inv in innovations:
    p_inv = tf.add_paragraph()
    p_inv.text = "• " + inv
    p_inv.font.size = Pt(14)
    
p3 = tf.add_paragraph()
p3.text = "\nUserflow Diagram:"
p3.font.bold = True
p3.font.size = Pt(16)

# Userflow Diagram
nodes = ["Noisy Speech", "Causal STFT", "Polar-LSTM", "Spectral Mask", "Causal iSTFT", "Enhanced Speech"]
start_x = Inches(0.1)
start_y = Inches(5.5)
box_w = Inches(1.3)
box_h = Inches(0.8)
gap = Inches(0.2)

for i, node in enumerate(nodes):
    x = start_x + i * (box_w + gap)
    shape = slide2.shapes.add_shape(MSO_SHAPE.RECTANGLE, x, start_y, box_w, box_h)
    shape.text = node
    shape.text_frame.paragraphs[0].font.size = Pt(12)
    shape.fill.solid()
    shape.fill.fore_color.rgb = RGBColor(220, 230, 242)
    shape.text_frame.paragraphs[0].font.color.rgb = RGBColor(0, 0, 0)
    
    if i < len(nodes) - 1:
        arr_x = x + box_w
        arr_y = start_y + Inches(0.3)
        slide2.shapes.add_shape(MSO_SHAPE.RIGHT_ARROW, arr_x, arr_y, gap, Inches(0.2))


# --- SLIDE 3: TECHNICAL APPROACH ---
slide3 = prs.slides.add_slide(blank_slide_layout)
title3 = slide3.shapes.add_textbox(Inches(0.5), Inches(0.2), Inches(9), Inches(1))
title3.text_frame.text = "Architecture & Technology Stack"
title3.text_frame.paragraphs[0].font.size = Pt(24)
title3.text_frame.paragraphs[0].font.bold = True
title3.text_frame.paragraphs[0].font.color.rgb = TITLE_COLOR

tx3 = slide3.shapes.add_textbox(Inches(0.5), Inches(1), Inches(4.5), Inches(3))
tf3 = tx3.text_frame
tf3.word_wrap = True
tf3.add_paragraph().text = "Signal Processing:"
tf3.paragraphs[-1].font.bold = True
tf3.add_paragraph().text = "• 16 kHz mono, 16 ms frames"
tf3.add_paragraph().text = "• 512 FFT size, 256 hop size (257 bins)"
tf3.add_paragraph().text = "• Causal STFT / iSTFT"

tf3.add_paragraph().text = "\nAI Model (Stateful Polar-LSTM):"
tf3.paragraphs[-1].font.bold = True
tf3.add_paragraph().text = "• Explicit recurrent hidden + cell states"
tf3.add_paragraph().text = "• Input: 514 features (Real + Imag)"
tf3.add_paragraph().text = "• Output: Mag mask [0, 2], Phase [-π, π]"
tf3.add_paragraph().text = "• 1,448,962 parameters"

tx3_r = slide3.shapes.add_textbox(Inches(5.2), Inches(1), Inches(4.5), Inches(3))
tf3_r = tx3_r.text_frame
tf3_r.add_paragraph().text = "Training / Evaluation Data:"
tf3_r.paragraphs[-1].font.bold = True
tf3_r.add_paragraph().text = "• LibriSpeech, MUSAN, ESC-50, UrbanSound8K"
tf3_r.add_paragraph().text = "• IoBT Gunfire Audio Dataset (Defence Domain)"

tf3_r.add_paragraph().text = "\nImplementation Pipeline:"
tf3_r.paragraphs[-1].font.bold = True
tf3_r.add_paragraph().text = "• Python + PyTorch -> Raspberry Pi 5 -> Edge Streaming"

# Technical Architecture Diagram
d_y = Inches(4.5)
slide3.shapes.add_textbox(Inches(0.5), d_y - Inches(0.3), Inches(9), Inches(0.5)).text_frame.text = "Technical Architecture Flow:"
nodes_tech = [
    "Mic / Audio",
    "16 kHz Stream",
    "Causal STFT\n(257 bins)",
    "Polar-LSTM\n(Stateful)",
    "Mag + Phase\nMask",
    "Causal iSTFT",
    "Enhanced\nAudio"
]
start_x = Inches(0.1)
box_w = Inches(1.2)
gap = Inches(0.15)
for i, node in enumerate(nodes_tech):
    x = start_x + i * (box_w + gap)
    shape = slide3.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, x, d_y, box_w, Inches(1))
    shape.text = node
    shape.text_frame.paragraphs[0].font.size = Pt(11)
    
    shape.fill.solid()
    if i == 3: # Polar-LSTM
        shape.fill.fore_color.rgb = RGBColor(153, 204, 255)
    else:
        shape.fill.fore_color.rgb = RGBColor(242, 242, 242)
    shape.text_frame.paragraphs[0].font.color.rgb = RGBColor(0, 0, 0)
    
    if i < len(nodes_tech) - 1:
        slide3.shapes.add_shape(MSO_SHAPE.RIGHT_ARROW, x + box_w, d_y + Inches(0.4), gap, Inches(0.2))


# --- SLIDE 4: FEASIBILITY & VALIDATION ---
slide4 = prs.slides.add_slide(content_slide_layout)
set_title(slide4, "Edge Feasibility + Experimental Validation")
tf4 = slide4.shapes.placeholders[1].text_frame
tf4.clear()
tf4.word_wrap = True

p = tf4.add_paragraph()
p.text = "Raspberry Pi 5 Edge Benchmark (3,600 frames):"
p.font.bold = True
tf4.add_paragraph().text = "• Deadline misses: 0"
tf4.add_paragraph().text = "• p95 processing time: 5.7 ms (Limit: 16 ms)"
tf4.add_paragraph().text = "• Max processing time: 11.7 ms"
tf4.add_paragraph().text = "• Peak temperature: 49.4C | RAM usage: ~258 MB | Throttling: None"

p = tf4.add_paragraph()
p.text = "\nCanonical Model Validation (590 mixtures):"
p.font.bold = True
tf4.add_paragraph().text = "• SI-SDR Improvement: +0.335 dB (p = 3.49 x 10^-28)"
tf4.add_paragraph().text = "• SNR Improvement: +0.129 dB (p = 0.00441)"
tf4.add_paragraph().text = "• Statistically significant changes also observed in STOI and PESQ"

p = tf4.add_paragraph()
p.text = "\nChallenges -> Mitigation:"
p.font.bold = True
tf4.add_paragraph().text = "• Non-stationary noise -> Stateful temporal modeling"
tf4.add_paragraph().text = "• Impulsive/gunfire noise -> Defence-domain training data"
tf4.add_paragraph().text = "• Phase distortion -> Polar complex masking"

# Prototype Status box
stat_box = slide4.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(5), Inches(5.0), Inches(4.5), Inches(1.5))
stat_box.fill.solid()
stat_box.fill.fore_color.rgb = RGBColor(200, 220, 200)
stat_box.text = "PROTOTYPE STATUS:\nAI model + Raspberry Pi edge pipeline validated.\nPhysical microphone/acoustic-loop validation is the next prototype stage."
stat_box.text_frame.paragraphs[0].font.color.rgb = RGBColor(0,0,0)
stat_box.text_frame.paragraphs[0].font.size = Pt(14)
stat_box.text_frame.paragraphs[0].font.bold = True

# --- SLIDE 5: IMPACT & BENEFITS ---
slide5 = prs.slides.add_slide(content_slide_layout)
set_title(slide5, "Impact on Defence Communication")
tf5 = slide5.shapes.placeholders[1].text_frame
tf5.clear()

p = tf5.add_paragraph()
p.text = "Primary Target Applications:"
p.font.bold = True
tf5.add_paragraph().text = "• Tactical Communication: Clearer voice in high-noise operational environments."
tf5.add_paragraph().text = "• Aviation / Helicopter Crews: Speech enhancement under continuous engine noise."
tf5.add_paragraph().text = "• Armoured & Military Vehicles: Suppression of engine and impulsive noise."
tf5.add_paragraph().text = "• Field Communication Systems: Low-latency processing directly at the edge."

p = tf5.add_paragraph()
p.text = "\nKey Benefits:"
p.font.bold = True
tf5.add_paragraph().text = "1. Improved Speech Intelligibility without cloud dependency."
tf5.add_paragraph().text = "2. Low-Latency Edge Processing for real-time operation."
tf5.add_paragraph().text = "3. Adaptive Noise Handling tracking temporal changes."
tf5.add_paragraph().text = "4. Defence-Domain Robustness using gunfire data."
tf5.add_paragraph().text = "5. Local & Portable execution on compact computing hardware."

p = tf5.add_paragraph()
p.text = "\nPotential Extensions: Emergency Response -> Industrial Safety -> Aviation -> Disaster Communication"
p.font.bold = True
p.font.color.rgb = RGBColor(0, 102, 51)


# --- SLIDE 6: RESEARCH & REFERENCES ---
slide6 = prs.slides.add_slide(content_slide_layout)
set_title(slide6, "Research, Datasets & Technical References")
tf6 = slide6.shapes.placeholders[1].text_frame
tf6.clear()

p = tf6.add_paragraph()
p.text = "Datasets Utilized:"
p.font.bold = True
tf6.add_paragraph().text = "• LibriSpeech (clean speech)"
tf6.add_paragraph().text = "• MUSAN, ESC-50, UrbanSound8K (environmental noise)"
tf6.add_paragraph().text = "• IoBT Gunfire Audio Dataset (defence-domain firearm recordings - DOI: 10.5281/zenodo.6836031)"

p = tf6.add_paragraph()
p.text = "\nTechnical Foundations:"
p.font.bold = True
tf6.add_paragraph().text = "• Causal real-time signal processing (STFT / iSTFT)"
tf6.add_paragraph().text = "• Long Short-Term Memory networks (LSTM)"
tf6.add_paragraph().text = "• Complex spectral masking & Objective metrics (SI-SDR, PESQ)"
tf6.add_paragraph().text = "• PyTorch edge inference on Raspberry Pi 5"

p = tf6.add_paragraph()
p.text = "\nCore Research Direction:"
p.font.bold = True
p.font.size = Pt(16)
p.font.color.rgb = TITLE_COLOR
tf6.add_paragraph().text = "Deep-learning speech enhancement + complex-domain spectral processing + recurrent temporal modeling + edge inference."

prs.save("SIH_26052_Presentation.pptx")
print("Presentation generated successfully at SIH_26052_Presentation.pptx")
