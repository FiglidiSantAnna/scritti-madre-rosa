#!/usr/bin/env python3
"""
build_crossrefs.py
Per ogni persona/fondazione in persone.json e fondazioni.json,
cerca le occorrenze nei testi dell'app (Lettere it, Memorie it, Travagli it)
e popola il campo 'refs' con lista di {corpus, file, section_i, label}.

corpus values: "lettere", "memorie", "travagli"
"""

import json, re, unicodedata
from pathlib import Path

BASE = Path(__file__).parent.parent
DATA = BASE / 'data'
LETTERE_IT = DATA / 'lettere' / 'it'

def norm(s):
    s = s.lower()
    s = unicodedata.normalize('NFD', s)
    s = re.sub(r'[̀-ͯ]', '', s)
    s = re.sub(r"[''`´]", "'", s)
    s = re.sub(r'\s+', ' ', s)
    return s.strip()

def strip_tags(html):
    return re.sub(r'<[^>]+>', '', html or '')

# ─── Costruisce il corpus di testi da scansionare ───────────────────────────

def load_corpus():
    """
    Ritorna lista di dict:
    { corpus, file_num, section_i, section_label, text_norm }
    dove text_norm è il testo normalizzato della sezione.
    """
    corpus = []

    # --- Lettere it (file 0..18) ---
    for path in sorted(LETTERE_IT.glob('*.json')):
        if path.stem == 'index':
            continue
        try:
            file_num = int(path.stem)
        except ValueError:
            continue
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
        for sec in data.get('sections', []):
            h = sec.get('h', '')
            # Cerca l'intestazione della sezione per il label
            label_m = re.search(r'<h[234][^>]*>(.+?)</h[234]>', h)
            if label_m:
                label = strip_tags(label_m.group(1))[:80]
            else:
                label = f"sezione {sec['i']}"
            corpus.append({
                'corpus': 'lettere',
                'file_num': file_num,
                'section_i': sec['i'],
                'section_label': label,
                'text_norm': norm(strip_tags(h))
            })

    # --- Memorie it ---
    mem_dir = DATA / 'memorie' / 'it'
    for path in sorted(mem_dir.glob('[0-9]*.json')):
        try:
            file_num = int(path.stem)
        except ValueError:
            continue
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
        for sec in data.get('sections', []):
            h = sec.get('h', '')
            label_m = re.search(r'<h[234][^>]*>(.+?)</h[234]>', h)
            label = strip_tags(label_m.group(1))[:80] if label_m else f"sezione {sec['i']}"
            corpus.append({
                'corpus': 'memorie',
                'file_num': file_num,
                'section_i': sec['i'],
                'section_label': label,
                'text_norm': norm(strip_tags(h))
            })

    # --- Travagli it ---
    trav_dir = DATA / 'travagli' / 'it'
    for path in sorted(trav_dir.glob('[0-9]*.json')):
        try:
            file_num = int(path.stem)
        except ValueError:
            continue
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
        for sec in data.get('sections', []):
            h = sec.get('h', '')
            label_m = re.search(r'<h[234][^>]*>(.+?)</h[234]>', h)
            label = strip_tags(label_m.group(1))[:80] if label_m else f"sezione {sec['i']}"
            corpus.append({
                'corpus': 'travagli',
                'file_num': file_num,
                'section_i': sec['i'],
                'section_label': label,
                'text_norm': norm(strip_tags(h))
            })

    print(f'Corpus totale: {len(corpus)} sezioni '
          f'(lettere: {sum(1 for c in corpus if c["corpus"]=="lettere")}, '
          f'memorie: {sum(1 for c in corpus if c["corpus"]=="memorie")}, '
          f'travagli: {sum(1 for c in corpus if c["corpus"]=="travagli")})')
    return corpus

# ─── Ricerca ────────────────────────────────────────────────────────────────

def find_refs(aliases, corpus, min_len=4):
    """
    Cerca ogni alias nel corpus. Ritorna lista di ref dict (deduplicati per sezione).
    Solo alias di lunghezza >= min_len per evitare falsi positivi.
    """
    # Prendi gli alias più specifici prima (più lunghi)
    # Un alias corto può dare troppi falsi positivi: usiamo solo quelli >= 4 chars
    search_aliases = [a for a in aliases if len(a) >= min_len]
    if not search_aliases:
        return []

    found_sections = {}  # (corpus, file_num, section_i) -> ref_dict

    for alias in search_aliases:
        # Cerca come parola intera (word boundary approssimativo)
        # Usiamo un pattern che richiede che alias sia preceduto/seguito da non-alfa
        pattern = re.compile(r'(?<![a-z])' + re.escape(alias) + r'(?![a-z])')
        for sec in corpus:
            key = (sec['corpus'], sec['file_num'], sec['section_i'])
            if key in found_sections:
                continue
            if pattern.search(sec['text_norm']):
                found_sections[key] = {
                    'corpus': sec['corpus'],
                    'file_num': sec['file_num'],
                    'section_i': sec['section_i'],
                    'label': sec['section_label']
                }

    return list(found_sections.values())

# ─── main ────────────────────────────────────────────────────────────────────

def main():
    # Carica corpus
    corpus = load_corpus()

    # Carica persone e fondazioni
    persone_path = DATA / 'lettere' / 'persone.json'
    fondazioni_path = DATA / 'lettere' / 'fondazioni.json'

    with open(persone_path, encoding='utf-8') as f:
        persone = json.load(f)
    with open(fondazioni_path, encoding='utf-8') as f:
        fondazioni = json.load(f)

    # Cross-reference persone
    print('\nCross-reference persone...')
    total_refs_p = 0
    for p in persone:
        refs = find_refs(p.get('aliases', []), corpus)
        p['refs'] = refs
        total_refs_p += len(refs)

    # Cross-reference fondazioni
    print('Cross-reference fondazioni...')
    total_refs_f = 0
    for fd in fondazioni:
        refs = find_refs(fd.get('aliases', []), corpus)
        fd['refs'] = refs
        total_refs_f += len(refs)

    print(f'\nPersone: {len(persone)}, refs totali: {total_refs_p}')
    print(f'Fondazioni: {len(fondazioni)}, refs totali: {total_refs_f}')

    # Campione di verifica
    print('\nCampione refs (prime 3 persone con refs):')
    shown = 0
    for p in persone:
        if p['refs'] and shown < 3:
            print(f"  {p['nome_display']}: {len(p['refs'])} refs "
                  f"(es: {p['refs'][0]['corpus']} f{p['refs'][0]['file_num']} s{p['refs'][0]['section_i']})")
            shown += 1

    # Salva
    with open(persone_path, 'w', encoding='utf-8') as f:
        json.dump(persone, f, ensure_ascii=False, indent=2)
    with open(fondazioni_path, 'w', encoding='utf-8') as f:
        json.dump(fondazioni, f, ensure_ascii=False, indent=2)

    print(f'\nAggiornato: {persone_path}')
    print(f'Aggiornato: {fondazioni_path}')

if __name__ == '__main__':
    main()
