"""
PubVerse NER (distilled) — self-contained modeling + inference.

Iterated Dilated CNN + CRF over static (model2vec / potion) embeddings, trained
with knowledge distillation from a transformer teacher for scientific NER.

Entity types: Method, Material, Metric, Tool.

This single file is everything needed to load `best_model.pt` and run inference —
no external project code required. It is the reference implementation shipped with
https://huggingface.co/jimnoneill/pubverse-ner-distilled

Quick start
-----------
    from modeling_pubverse_ner import PubVerseNER

    ner = PubVerseNER.from_pretrained("jimnoneill/pubverse-ner-distilled")
    print(ner.extract("We used qRT-PCR to measure IL-6 in serum with GraphPad Prism."))
    # [{'text': 'qRT-PCR', 'type': 'Method', 'start': 8, 'end': 15}, ...]

    # Batch (recommended for corpora):
    results = ner.extract_batch(list_of_texts, batch_size=128)

Notes on context
----------------
Static embeddings are context-free token lookups, so there is no transformer-style
maximum sequence length — any length encodes without error. The IDCNN encoder has a
*local* receptive field, though, and the model was trained on <=256-token sentences,
so for best quality feed sentence/passage-sized text (use `extract_document` to let
this module sentence-split for you).

Dependencies: torch, model2vec, pytorch-crf, huggingface_hub, numpy
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

# ── Label set ────────────────────────────────────────────────────────────────
ENTITY_TYPES = ["Method", "Material", "Metric", "Tool"]
BIO_TAGS = ["O"] + [f"B-{t}" for t in ENTITY_TYPES] + [f"I-{t}" for t in ENTITY_TYPES]
TAG2ID = {t: i for i, t in enumerate(BIO_TAGS)}
ID2TAG = {i: t for i, t in enumerate(BIO_TAGS)}
NUM_LABELS = len(BIO_TAGS)  # 9

# ── Tokenizer (must match training) ──────────────────────────────────────────
TOKEN_RE = re.compile(r"\d+\.\d+|\w+|[^\s\w]")

# ── Character vocabulary for CharCNN (must match training; size == 87) ────────
CHAR_PAD = 0
CHAR_UNK = 1
CHAR_VOCAB = {c: i + 2 for i, c in enumerate(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_./()'\",:;!?@#$%^&*+= "
)}
CHAR_VOCAB_SIZE = len(CHAR_VOCAB) + 2
MAX_WORD_LEN = 30


def encode_chars(word: str) -> List[int]:
    chars = [CHAR_VOCAB.get(c, CHAR_UNK) for c in word[:MAX_WORD_LEN]]
    return chars + [CHAR_PAD] * (MAX_WORD_LEN - len(chars))


# ── Architecture ─────────────────────────────────────────────────────────────
class CharCNN(nn.Module):
    """Character-level CNN for morphology (-ase, -tion, CamelCase, digit patterns)."""

    def __init__(self, char_vocab_size=CHAR_VOCAB_SIZE, char_emb_dim=30,
                 num_filters=64, kernel_sizes=(3, 5)):
        super().__init__()
        self.char_embedding = nn.Embedding(char_vocab_size, char_emb_dim, padding_idx=CHAR_PAD)
        self.convs = nn.ModuleList([
            nn.Conv1d(char_emb_dim, num_filters // len(kernel_sizes), k, padding=k // 2)
            for k in kernel_sizes
        ])
        self.output_dim = num_filters

    def forward(self, char_ids):
        B, S, W = char_ids.shape
        x = self.char_embedding(char_ids.view(B * S, W))
        x = x.transpose(1, 2)
        conv_outs = [F.relu(conv(x)).max(dim=2).values for conv in self.convs]
        return torch.cat(conv_outs, dim=1).view(B, S, -1)


def init_crf_bio_constraints(crf):
    """Soft BIO constraints: penalize invalid I-X transitions."""
    with torch.no_grad():
        nn.init.uniform_(crf.transitions, -0.1, 0.1)
        for i in range(NUM_LABELS):
            tag_i = ID2TAG[i]
            if tag_i.startswith("I-"):
                type_i = tag_i[2:]
                for j in range(NUM_LABELS):
                    tag_j = ID2TAG[j]
                    if tag_j == "O" or \
                       (tag_j.startswith("B-") and tag_j[2:] != type_i) or \
                       (tag_j.startswith("I-") and tag_j[2:] != type_i):
                        crf.transitions[i, j] = -5.0


class DilatedCNNBlock(nn.Module):
    def __init__(self, channels, kernel_size=3, dilation=1, dropout=0.2):
        super().__init__()
        padding = dilation * (kernel_size - 1) // 2
        self.conv1 = nn.Conv1d(channels, channels, kernel_size, padding=kernel_size // 2)
        self.conv2 = nn.Conv1d(channels, channels, kernel_size, padding=padding, dilation=dilation)
        self.norm1 = nn.LayerNorm(channels)
        self.norm2 = nn.LayerNorm(channels)
        self.dropout = nn.Dropout(dropout)

    def forward(self, x):
        residual = x
        h = x.transpose(1, 2)
        h = F.gelu(self.conv1(h)).transpose(1, 2)
        h = self.norm1(h)
        h = h.transpose(1, 2)
        h = F.gelu(self.conv2(h)).transpose(1, 2)
        h = self.norm2(h)
        h = self.dropout(h)
        return h + residual


class IDCNNModel(nn.Module):
    """ID-CNN + CRF (Strubell et al. 2017) over static embeddings + CharCNN.

    Layout matches the published checkpoint: input_proj and blocks live at the top
    level (not nested), n_iterations applied in forward.
    """

    def __init__(self, emb_dim=256, hidden_dim=192, char_dim=64,
                 dilations=(1, 2, 4), n_iterations=2, dropout=0.25):
        super().__init__()
        self.emb_dim = emb_dim
        self.char_dim = char_dim
        combined = emb_dim + char_dim

        self.char_cnn = CharCNN(num_filters=char_dim)
        self.input_proj = nn.Sequential(
            nn.Linear(combined, hidden_dim), nn.LayerNorm(hidden_dim),
            nn.GELU(), nn.Dropout(dropout),
        )
        self.blocks = nn.ModuleList([
            DilatedCNNBlock(hidden_dim, 3, d, dropout) for d in dilations
        ])
        self.n_iterations = n_iterations
        self.hidden2tag = nn.Linear(hidden_dim, NUM_LABELS)

        from torchcrf import CRF
        self.crf = CRF(NUM_LABELS, batch_first=True)
        init_crf_bio_constraints(self.crf)

    def forward(self, embeddings, char_ids, tags=None, mask=None):
        char_feats = self.char_cnn(char_ids)
        x = torch.cat([embeddings, char_feats], dim=2)
        h = self.input_proj(x)
        for _ in range(self.n_iterations):
            for block in self.blocks:
                h = block(h)
        emissions = self.hidden2tag(h)
        if tags is not None:
            return -self.crf(emissions, tags, mask=mask, reduction="mean")
        return self.crf.decode(emissions, mask=mask)


# ── Sentence splitter (lightweight, dependency-free) ─────────────────────────
_SENT_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9])")


def split_sentences(text: str, max_tokens: int = 200) -> List[str]:
    """Split text into sentence-ish chunks, hard-wrapping very long spans on
    whitespace so no chunk greatly exceeds `max_tokens` whitespace tokens."""
    out: List[str] = []
    for para in text.split("\n"):
        para = para.strip()
        if not para:
            continue
        for sent in _SENT_SPLIT_RE.split(para):
            sent = sent.strip()
            if not sent:
                continue
            words = sent.split()
            if len(words) <= max_tokens:
                out.append(sent)
            else:
                for i in range(0, len(words), max_tokens):
                    out.append(" ".join(words[i:i + max_tokens]))
    return out


# ── Inference wrapper ────────────────────────────────────────────────────────
class PubVerseNER:
    """Load once, extract many. GPU-aware."""

    def __init__(self, model: IDCNNModel, text_model, id2tag: Dict[int, str],
                 device: Optional[str] = None):
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.model = model.to(self.device).eval()
        self.text_model = text_model
        self.id2tag = {int(k): v for k, v in id2tag.items()}

    # --- construction ---------------------------------------------------------
    @classmethod
    def from_pretrained(cls, repo_or_path: str = "jimnoneill/pubverse-ner-distilled",
                        embedding_model: str = "minishlab/potion-science-32M",
                        model_filename: str = "best_model.pt",
                        device: Optional[str] = None) -> "PubVerseNER":
        import os
        from model2vec import StaticModel

        if os.path.isfile(repo_or_path):
            ckpt_path = repo_or_path
        elif os.path.isdir(repo_or_path):
            ckpt_path = os.path.join(repo_or_path, model_filename)
        else:
            from huggingface_hub import hf_hub_download
            ckpt_path = hf_hub_download(repo_or_path, model_filename)

        ckpt = torch.load(ckpt_path, map_location="cpu", weights_only=False)
        cfg = ckpt.get("model_config", {})
        model = IDCNNModel(emb_dim=cfg.get("emb_dim", 256),
                           char_dim=cfg.get("char_dim", 64), dropout=0.0)
        model.load_state_dict(ckpt["model_state_dict"])
        text_model = StaticModel.from_pretrained(embedding_model)
        return cls(model, text_model, ckpt.get("id2tag", ID2TAG), device=device)

    # --- helpers --------------------------------------------------------------
    @staticmethod
    def _bio_to_entities(tokens, offsets, tags) -> List[Dict[str, Any]]:
        entities, current = [], None
        for i, tag in enumerate(tags):
            if tag.startswith("B-"):
                if current:
                    entities.append(current)
                current = {"text": tokens[i], "type": tag[2:],
                           "start": offsets[i][0], "end": offsets[i][1]}
            elif tag.startswith("I-") and current and current["type"] == tag[2:]:
                current["text"] += " " + tokens[i]
                current["end"] = offsets[i][1]
            else:
                if current:
                    entities.append(current)
                    current = None
        if current:
            entities.append(current)
        return entities

    # --- inference ------------------------------------------------------------
    @torch.no_grad()
    def extract(self, text: str) -> List[Dict[str, Any]]:
        return self.extract_batch([text], batch_size=1)[0]

    @torch.no_grad()
    def extract_batch(self, texts: List[str], batch_size: int = 128) -> List[List[Dict[str, Any]]]:
        all_data: List[Optional[Tuple]] = []
        for text in texts:
            matches = list(TOKEN_RE.finditer(text or ""))
            if not matches:
                all_data.append(None)
                continue
            tokens = [m.group() for m in matches]
            offsets = [(m.start(), m.end()) for m in matches]
            all_data.append((tokens, offsets))

        results: List[List[Dict]] = [[] for _ in texts]
        valid_indices = [i for i, d in enumerate(all_data) if d is not None]

        for bs in range(0, len(valid_indices), batch_size):
            batch_indices = valid_indices[bs:bs + batch_size]
            batch_data = [all_data[i] for i in batch_indices]

            batch_embs, batch_chars = [], []
            for tokens, _ in batch_data:
                batch_embs.append(self.text_model.encode(tokens).astype("float32"))
                batch_chars.append([encode_chars(t) for t in tokens])

            max_len = max(len(e) for e in batch_embs)
            emb_dim = batch_embs[0].shape[1]
            B = len(batch_embs)

            padded_embs = torch.zeros(B, max_len, emb_dim)
            padded_chars = torch.zeros(B, max_len, MAX_WORD_LEN, dtype=torch.long)
            mask = torch.zeros(B, max_len, dtype=torch.bool)
            for j, (embs, chars) in enumerate(zip(batch_embs, batch_chars)):
                L = len(embs)
                padded_embs[j, :L] = torch.tensor(embs)
                padded_chars[j, :L] = torch.tensor(chars, dtype=torch.long)
                mask[j, :L] = True

            pred_list = self.model(padded_embs.to(self.device),
                                   padded_chars.to(self.device),
                                   mask=mask.to(self.device))

            for j, idx in enumerate(batch_indices):
                tokens, offsets = batch_data[j]
                pred_tags = [self.id2tag[p] for p in pred_list[j]]
                results[idx] = self._bio_to_entities(tokens, offsets, pred_tags)
        return results

    @torch.no_grad()
    def extract_document(self, text: str, batch_size: int = 128,
                         max_tokens: int = 200) -> List[Dict[str, Any]]:
        """Sentence-split a long document, run NER per sentence, and return
        entities with offsets remapped to the original document."""
        sents = split_sentences(text, max_tokens=max_tokens)
        # locate each sentence in the original text to remap offsets
        spans, cursor = [], 0
        for s in sents:
            idx = text.find(s, cursor)
            if idx < 0:
                idx = text.find(s)
            spans.append(idx if idx >= 0 else 0)
            cursor = (idx + len(s)) if idx >= 0 else cursor
        per_sent = self.extract_batch(sents, batch_size=batch_size)
        out = []
        for base, ents in zip(spans, per_sent):
            for e in ents:
                out.append({**e, "start": e["start"] + base, "end": e["end"] + base})
        return out


if __name__ == "__main__":
    ner = PubVerseNER.from_pretrained()
    demo = ("Single-cell RNA sequencing of tumor biopsies identified CD8+ T cells; "
            "data were processed with Seurat and aligned using STAR (AUC 0.91).")
    for e in ner.extract(demo):
        print(f"  [{e['type']:8}] {e['text']}")
