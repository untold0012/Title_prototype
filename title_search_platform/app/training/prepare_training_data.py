import json
import random
from pathlib import Path

# ⚠️ Replace this list with more annotated examples later
FULL_DATA = [
    {
        "text": "THIS WARRANTY DEED, made the 23rd day of May, 2025 by Eric B. Zwiebel and Julie Coates-Zwiebel, husband and wife, to Geramy Garcia Rodriguez...",
        "entities": [
            (35, 50, "DATED_DATE"),
            (54, 95, "GRANTOR"),
            (100, 125, "GRANTEE")
        ]
    },
    {
        "text": "Recorded 05/27/2025 at 08:40 AM as Instrument #120236318 in Plat Book 147, Page 47...",
        "entities": [
            (9, 19, "RECORDING_DATE"),
            (45, 54, "INSTRUMENT_NUMBER"),
            (58, 76, "BOOK_PAGE")
        ]
    }
]

# 🔀 Shuffle and split into 80/20 train/dev sets
random.shuffle(FULL_DATA)
split = int(len(FULL_DATA) * 0.8)
train_data = FULL_DATA[:split]
dev_data = FULL_DATA[split:]

# 📁 Write to /data/
output_dir = Path(__file__).resolve().parent / "data"
output_dir.mkdir(parents=True, exist_ok=True)

with open(output_dir / "train_data.json", "w") as f:
    json.dump(train_data, f, indent=2)

with open(output_dir / "dev_data.json", "w") as f:
    json.dump(dev_data, f, indent=2)

print(f"✅ Wrote {len(train_data)} training examples to data/train_data.json")
print(f"✅ Wrote {len(dev_data)} dev examples to data/dev_data.json")
