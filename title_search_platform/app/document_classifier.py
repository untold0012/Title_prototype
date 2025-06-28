
from sentence_transformers import SentenceTransformer, util
from app.model_loader import model 
# Load sentence-transformer model once
model = SentenceTransformer("all-MiniLM-L6-v2")

# Define weighted keyword sets per document type
DOCUMENT_KEYWORDS = {
    "deed": [
        "grantor", "grantee", "warranty deed", "quit claim", "executed by",
        "fee simple", "conveys", "property address"
    ],
    "mortgage": [
        "mortgage", "borrower", "lender", "loan amount", "security deed", "deed of trust"
    ],
    "lien": [
        "lien", "recorded lien", "debtor", "creditor", "mechanic's lien", "lis pendens"
    ],
    "judgment": [
        "judgment", "plaintiff", "defendant", "court", "awarded", "final judgment"
    ],
    "release": [
        "satisfaction", "release of mortgage", "discharge", "cancelled", "paid in full"
    ]
}

# Optional fallback reference examples for sentence similarity
REFERENCE_TEXTS = {
    "deed": "This Warranty Deed is made by the grantor to the grantee for the consideration of...",
    "mortgage": "This Mortgage is made between the borrower and the lender to secure a loan amount...",
    "lien": "A lien is hereby recorded against the property of the debtor in favor of the creditor...",
    "judgment": "Final judgment is entered in favor of the plaintiff and against the defendant...",
    "release": "This document is a Satisfaction of Mortgage, fully releasing the borrower..."
}

def classify_doc_type(text: str) -> str:
    text_lower = text.lower()
    scores = {}

    # Step 1: Keyword matching
    for doc_type, keywords in DOCUMENT_KEYWORDS.items():
        matches = sum(1 for keyword in keywords if keyword in text_lower)
        scores[doc_type] = matches

    best_match = max(scores, key=scores.get)
    best_score = scores[best_match]

    # Step 2: Fallback to embeddings if scores are tied or all zero
    sorted_scores = sorted(scores.values(), reverse=True)
    if sorted_scores[0] == 0 or (len(sorted_scores) > 1 and sorted_scores[0] == sorted_scores[1]):
        # Encode the full text
        text_embedding = model.encode(text, convert_to_tensor=True)
        best_sim = -1
        best_type = "unknown"
        for doc_type, reference in REFERENCE_TEXTS.items():
            ref_embedding = model.encode(reference, convert_to_tensor=True)
            sim = util.cos_sim(text_embedding, ref_embedding)[0][0].item()
            if sim > best_sim:
                best_sim = sim
                best_type = doc_type
        return best_type

    return best_match
