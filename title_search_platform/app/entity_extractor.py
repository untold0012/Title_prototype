from typing import Dict, List
from sentence_transformers import SentenceTransformer, util
import nltk

# Ensure punkt is downloaded
nltk.download("punkt", quiet=True)
from nltk.tokenize import sent_tokenize

from app.model_loader import model

ENTITY_PROMPTS = {
    "deed": {
        "grantor": [
            "Who is the grantor?",
            "Who is the seller?",
            "Who is transferring the property?"
        ],
        "grantee": [
            "Who is the grantee?",
            "Who is the buyer?",
            "Who is receiving the property?"
        ],
        "recording_date": [
            "When was this document recorded?",
            "Recording date"
        ],
        "dated_date": [
            "When was this document signed?",
            "Execution date",
            "Dated this day"
        ],
        "consideration_amount": [
            "What is the consideration amount?",
            "What amount was paid?",
            "Monetary value exchanged"
        ]
    }
}

def clean_sentences(text: str) -> List[str]:
    noise_keywords = [
        "Instr#", "Page", "JK-", "SEAL", "Notary", "Commission", "My commission expires",
        "Prepared by", "Doc Stamps", "Appraisers", "SPACE ABOVE THIS LINE"
    ]
    return [
        s.strip()
        for s in sent_tokenize(text)
        if s.strip() and not any(nk.lower() in s.lower() for nk in noise_keywords)
    ]

def extract_entities_semantic(text: str, doc_type: str) -> Dict[str, str]:
    cleaned_sentences = clean_sentences(text)
    if not cleaned_sentences or doc_type not in ENTITY_PROMPTS:
        return {}

    sentence_embeddings = model.encode(cleaned_sentences, convert_to_tensor=True)

    extracted = {}
    for entity, prompt_variants in ENTITY_PROMPTS[doc_type].items():
        prompt_embeddings = model.encode(prompt_variants, convert_to_tensor=True)
        avg_prompt_embedding = prompt_embeddings.mean(dim=0)
        cosine_scores = util.cos_sim(avg_prompt_embedding, sentence_embeddings)[0]
        best_idx = int(cosine_scores.argmax())
        best_score = float(cosine_scores[best_idx])
        extracted[entity] = cleaned_sentences[best_idx] if best_score > 0.5 else ""
    return extracted
