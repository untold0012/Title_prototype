import sys
import json
import spacy
from pathlib import Path
from spacy.tokens import DocBin

# Accept 'train' or 'dev' as command-line arg
mode = sys.argv[1] if len(sys.argv) > 1 else "train"
input_file = f"data/{mode}_data.json"
output_file = f"data/{mode}.spacy"

nlp = spacy.blank("en")
db = DocBin()

with open(input_file, "r") as f:
    training_data = json.load(f)

for record in training_data:
    doc = nlp.make_doc(record["text"])
    ents = []
    for start, end, label in record["entities"]:
        span = doc.char_span(start, end, label=label)
        if span:
            ents.append(span)
    doc.ents = ents
    db.add(doc)

db.to_disk(output_file)
print(f"✅ Saved {mode} data to {output_file}")
