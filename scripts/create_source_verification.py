import csv

def main():
    records = [
        {
            "dataset": "MAD (Military Audio Dataset)",
            "official_url": "https://github.com/kaen2891/military_audio_dataset",
            "doi": "10.1038/s41597-024-03223-2",
            "authors": "Kim, J.W. et al.",
            "license_exact": "CC BY 4.0 (for annotations/code) / YouTube Copyright (for audio)",
            "commercial_use": "UNCLEAR",
            "derivatives_allowed": "UNCLEAR",
            "redistribution_allowed": "UNCLEAR",
            "attribution_required": "YES",
            "audio_license_verified": "NO",
            "source_recording_unit": "YouTube Video",
            "estimated_independent_sources": "Unknown (Likely <100 videos)",
            "estimated_audio_files": "8075",
            "categories": "Communication, Gunshot, Footsteps, Shelling, Vehicle, Helicopter, Fighter",
            "defence_domain_status": "DIRECT",
            "provenance_status": "UNCLEAR",
            "license_status": "REJECT",
            "acquisition_status": "REJECT",
            "notes": "Audio is ripped from YouTube. Authors only hold copyright to their annotations, not the underlying audio. Distributing or using this audio commercially violates underlying creator copyrights."
        },
        {
            "dataset": "Gunshot/Gunfire Audio Dataset",
            "official_url": "https://zenodo.org/record/6836031",
            "doi": "10.5281/zenodo.6836031",
            "authors": "IoBT Researchers",
            "license_exact": "CC BY 4.0",
            "commercial_use": "YES",
            "derivatives_allowed": "YES",
            "redistribution_allowed": "YES",
            "attribution_required": "YES",
            "audio_license_verified": "YES",
            "source_recording_unit": "Firing Event / Session",
            "estimated_independent_sources": "Unknown (Fewer than files due to multi-device sync)",
            "estimated_audio_files": "15000+",
            "categories": "Gunshot, Gunfire",
            "defence_domain_status": "DIRECT",
            "provenance_status": "VERIFIED",
            "license_status": "VERIFIED",
            "acquisition_status": "APPROVED_FOR_DOWNLOAD",
            "notes": "Original recordings collected directly by the authors at a firing range. License fully applies to the audio files."
        }
    ]

    keys = records[0].keys()
    with open("sih26052_defence_dataset_source_verification.csv", "w") as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        for r in records:
            writer.writerow(r)

    md = "# SIH26052 Defence Dataset Source Verification\n\n"
    md += "## 1. MAD (Military Audio Dataset)\n"
    md += "- **Dataset Identity**: MAD (Scientific Data, 2024)\n"
    md += "- **Official Repository**: `kaen2891/military_audio_dataset`\n"
    md += "- **Audio Licensing**: The metadata and code are CC BY 4.0, but the **audio files are ripped directly from YouTube**. The authors do not hold the copyright to the audio. Using these files for commercial or derivative AI models violates the original creators' rights.\n"
    md += "- **Data Leakage Risk**: The highest-level independent source unit is the *YouTube Video*, not the individual WAV clip. Thousands of clips may originate from a handful of videos, leading to massive train/test leakage if split natively.\n"
    md += "- **Acquisition Status**: **REJECT** (Fails audio license verification).\n\n"

    md += "## 2. Gunshot/Gunfire Audio Dataset (IoBT)\n"
    md += "- **Dataset Identity**: Gunshot/Gunfire Audio Dataset (Zenodo)\n"
    md += "- **DOI**: `10.5281/zenodo.6836031`\n"
    md += "- **Audio Licensing**: The authors physically recorded the audio at an outdoor range. The CC BY 4.0 license explicitly covers the audio files.\n"
    md += "- **Data Leakage Risk**: The highest-level unit is the *Firing Event*. Because multiple edge devices recorded the *same* gunshot, splitting files natively will cause identical acoustic events to leak across train/val splits. Great care must be taken to split by event/session, not by file.\n"
    md += "- **Acquisition Status**: **APPROVED_FOR_DOWNLOAD**.\n"

    with open("sih26052_defence_dataset_source_verification.md", "w") as f:
        f.write(md)
        
    print(f"MAD_LICENSE=CC BY 4.0 (Metadata) / YouTube Copyright (Audio)")
    print(f"MAD_AUDIO_LICENSE_VERIFIED=NO")
    print(f"MAD_DEFENCE_STATUS=DIRECT")
    print(f"MAD_ACQUISITION_STATUS=REJECT\n")
    
    print(f"GUNFIRE_LICENSE=CC BY 4.0")
    print(f"GUNFIRE_AUDIO_LICENSE_VERIFIED=YES")
    print(f"GUNFIRE_DEFENCE_STATUS=DIRECT")
    print(f"GUNFIRE_ACQUISITION_STATUS=APPROVED_FOR_DOWNLOAD\n")
    
    print(f"FINAL_SOURCE_GATE=PARTIAL_APPROVAL")

if __name__ == "__main__":
    main()
