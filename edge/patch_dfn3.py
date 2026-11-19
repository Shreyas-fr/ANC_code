import sys
p = "/Users/shreyasdivekar/Downloads/anc_fix 2/dfn3_enhance.py"
with open(p, "r") as f:
    text = f.read()

# Replace DF instantiation
old_line = "df_state = DF(sr=p.sr, fft_size=p.fft_size, hop_size=p.hop_size, nb_bands=p.nb_erb)"
new_line = "df_state = DF(sr=p.sr, fft_size=p.fft_size, hop_size=p.hop_size, nb_bands=p.nb_erb, min_nb_erb_freqs=p.min_nb_freqs)"

if old_line in text:
    text = text.replace(old_line, new_line)
    with open(p, "w") as f:
        f.write(text)
    print("Patched!")
else:
    print("Not found or already patched")
