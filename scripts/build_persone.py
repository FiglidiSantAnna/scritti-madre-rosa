#!/usr/bin/env python3
"""
build_persone.py
Estrae tutte le voci INDICE DESTINATARI, LE FONDAZIONI, e PERSONE DI RILIEVO
dai file lettere/it/N.json (N = 2, 5, 8, 11, 13, 16) e costruisce:
  - data/lettere/persone.json   (persone / destinatari / persone di rilievo)
  - data/lettere/fondazioni.json (luoghi / fondazioni)
"""

import json, re, unicodedata
from pathlib import Path

BASE = Path(__file__).parent.parent
LETTERE_IT = BASE / 'data' / 'lettere' / 'it'
OUT_DIR    = BASE / 'data' / 'lettere'

# ─── utilità ────────────────────────────────────────────────────────────────

def strip_tags(html):
    return re.sub(r'<[^>]+>', '', html or '').strip()

def norm(s):
    s = s.lower()
    s = unicodedata.normalize('NFD', s)
    s = re.sub(r'[̀-ͯ]', '', s)
    s = re.sub(r"[''`´]", "'", s)
    s = re.sub(r'\s+', ' ', s)
    return s.strip()

def extract_letter_refs(text):
    refs = set()
    for m in re.finditer(r'\bL\s+([\d]+(?:[;,\s]+\d+)*)', text):
        for n in re.split(r'[;,\s]+', m.group(1)):
            n = n.strip()
            if n.isdigit():
                refs.add(int(n))
    m = re.search(r'Lettere nelle quali[^:]+:\s*([\d\s;.]+)', text)
    if m:
        for n in re.split(r'[;,\s.]+', m.group(1)):
            n = n.strip()
            if n.isdigit():
                refs.add(int(n))
    return sorted(refs)

def parse_person_name(raw_name):
    raw_name = raw_name.strip().rstrip(',.')
    titolo = ''
    m = re.search(r'\(([^)]+)\)', raw_name)
    if m:
        titolo = m.group(1).strip()
        raw_name = (raw_name[:m.start()] + ' ' + raw_name[m.end():]).strip()
    parts = raw_name.split()
    if not parts:
        return '', titolo, '', raw_name, []
    cognome = parts[0].title()
    nome = ' '.join(p.title() for p in parts[1:]) if len(parts) > 1 else ''
    if titolo:
        display = f"{cognome} ({titolo}) {nome}".strip()
    else:
        display = f"{cognome} {nome}".strip()
    aliases = []
    if cognome:
        aliases.append(norm(cognome))
    if nome:
        aliases.append(norm(f"{cognome} {nome}"))
    if titolo:
        aliases.append(norm(f"{titolo} {cognome}"))
        aliases.append(norm(f"{cognome} {titolo}"))
    seen = set()
    uniq = []
    for a in aliases:
        if a not in seen:
            seen.add(a)
            uniq.append(a)
    return cognome, titolo, nome, display, uniq

def split_numbered_entries(section_html):
    """Divide la sezione in blocchi numerati. Gestisce <p>N. e <p><strong>N."""
    return re.split(r'(?=<p>(?:<[^>]+>)?\s*\d+\.)', section_html)

def extract_name_from_block(block_html):
    """
    Estrae il nome della persona dall'HTML del blocco.
    Gestisce nomi in <strong> e nomi semplici.
    """
    # Prima: nome in <strong> (es. file 2/5)
    m_strong = re.search(
        r'<strong>(?:\d+\.\s*)?([A-Z\xc0-\xd6\xd8-\xde][^<]*?)[,.]?\s*</strong>',
        block_html
    )
    if m_strong:
        raw_name = m_strong.group(1).strip().rstrip(',.')
        return raw_name

    # Fallback: dal testo plain
    text = strip_tags(block_html)
    m = re.match(r'^\d+\.\s+(.+)', text, re.DOTALL)
    if not m:
        return ''
    rest = m.group(1).strip()
    name_match = re.match(
        r'^([A-Z\xc0-\xd6\xd8-\xde][A-Z\xc0-\xd6\xd8-\xde\s\(\)\'\.]+?)[,.]\s',
        rest
    )
    if name_match:
        return name_match.group(1).strip()
    first_dot = rest.find('. ')
    if first_dot > 0:
        return rest[:first_dot].strip()
    return rest[:60]

def parse_person_entry(block, tipo, file_num, num_str):
    block = block.strip()
    raw_name = extract_name_from_block(block)
    cognome, titolo, nome, display, aliases = parse_person_name(raw_name)
    text = strip_tags(block)
    letter_refs = extract_letter_refs(text)
    prefix = 'dest' if tipo == 'destinatario' else 'pers'
    return {
        'id': f"{prefix}-{file_num}-{num_str}",
        'tipo': tipo,
        'file_source': file_num,
        'voce_num': int(num_str),
        'nome_display': display,
        'cognome': cognome,
        'titolo': titolo,
        'nome': nome,
        'scheda_html': block,
        'lettere_citate': letter_refs,
        'aliases': aliases,
        'refs': []
    }

def parse_destinatari(section_html, file_num):
    entries = []
    for block in split_numbered_entries(section_html):
        block = block.strip()
        if not block:
            continue
        m = re.match(r'^(\d+)\.', strip_tags(block))
        if not m:
            continue
        entries.append(parse_person_entry(block, 'destinatario', file_num, m.group(1)))
    return entries

def parse_persone_di_rilievo(section_html, file_num):
    entries = []
    for block in split_numbered_entries(section_html):
        block = block.strip()
        if not block:
            continue
        m = re.match(r'^(\d+)\.', strip_tags(block))
        if not m:
            continue
        entries.append(parse_person_entry(block, 'persona_di_rilievo', file_num, m.group(1)))
    return entries

def parse_fondazioni(section_html, file_num):
    entries = []
    for block in split_numbered_entries(section_html):
        block = block.strip()
        if not block:
            continue
        text = strip_tags(block)
        m = re.match(r'^(\d+)\.\s+(.+)', text, re.DOTALL)
        if not m:
            continue
        num_str = m.group(1)
        rest = m.group(2).strip()
        name_match = re.match(
            r'^([A-Z\xc0-\xd6\xd8-\xde][A-Z\xc0-\xd6\xd8-\xde\s\(\)\']+?)\.\s',
            rest
        )
        if name_match:
            raw_place = name_match.group(1).strip()
            rest_text = rest[name_match.end():].strip()
        else:
            first_dot = rest.find('. ')
            raw_place = rest[:first_dot].strip() if first_dot > 0 else rest[:40].strip()
            rest_text = rest[first_dot+2:] if first_dot > 0 else rest
        prov_m = re.search(r'\(([^)]+)\)', raw_place)
        provincia = prov_m.group(1).strip() if prov_m else ''
        luogo = re.sub(r'\s*\([^)]*\)', '', raw_place).strip().title()
        tipo_opera_m = re.match(r'^([^\.]+)\.\s', rest_text)
        tipo_opera = tipo_opera_m.group(1).strip() if tipo_opera_m else ''
        display = luogo + (f" ({provincia})" if provincia else '')
        aliases_fond = list(dict.fromkeys([norm(luogo), norm(raw_place)] +
                                          ([norm(f"{luogo} {provincia}")] if provincia else [])))
        letter_refs = extract_letter_refs(text)
        entries.append({
            'id': f"fond-{file_num}-{num_str}",
            'tipo': 'fondazione',
            'file_source': file_num,
            'voce_num': int(num_str),
            'nome_display': display,
            'luogo': luogo,
            'provincia': provincia,
            'tipo_opera': tipo_opera,
            'scheda_html': block,
            'lettere_citate': letter_refs,
            'aliases': aliases_fond,
            'refs': []
        })
    return entries

# ─── main ────────────────────────────────────────────────────────────────────

def get_section_html(html, marker, next_heading_after=100):
    idx = html.find(marker)
    if idx < 0:
        return None
    m_next = re.search(r'<h[34]', html[idx+next_heading_after:])
    if m_next:
        return html[idx : idx+next_heading_after+m_next.start()]
    return html[idx:]

def main():
    all_persone = []
    all_fondazioni = []

    for n in [2, 5, 8, 11, 13, 16]:
        with open(LETTERE_IT / f'{n}.json', encoding='utf-8') as f:
            data = json.load(f)
        html = ''.join(s['h'] for s in data['sections'])
        print(f'\n=== File {n} ===')

        if 'INDICE DEI DESTINAT' in html:
            sec = get_section_html(html, 'INDICE DEI DESTINAT')
            entries = parse_destinatari(sec, n)
            print(f'  DESTINATARI: {len(entries)} voci')
            all_persone.extend(entries)

        if 'LE FONDAZIONI' in html:
            sec = get_section_html(html, 'LE FONDAZIONI')
            entries = parse_fondazioni(sec, n)
            print(f'  FONDAZIONI: {len(entries)} voci')
            all_fondazioni.extend(entries)

        if 'PERSONE DI RILIEVO' in html:
            sec = get_section_html(html, 'PERSONE DI RILIEVO')
            entries = parse_persone_di_rilievo(sec, n)
            print(f'  PERSONE DI RILIEVO: {len(entries)} voci')
            all_persone.extend(entries)

    # Deduplicazione persone per cognome+nome normalizzato
    dedup = {}
    for p in all_persone:
        key = norm(p.get('cognome','') + ' ' + p.get('nome',''))
        if key in dedup:
            ex = dedup[key]
            ex['lettere_citate'] = sorted(set(ex['lettere_citate'] + p['lettere_citate']))
            for a in p['aliases']:
                if a not in ex['aliases']:
                    ex['aliases'].append(a)
            if len(p['scheda_html']) > len(ex['scheda_html']):
                ex['scheda_html'] = p['scheda_html']
        else:
            dedup[key] = p

    final_persone = list(dedup.values())

    print(f'\n=== TOTALI ===')
    print(f'Persone (dopo dedup): {len(final_persone)}')
    print(f'Fondazioni: {len(all_fondazioni)}')

    out_p = OUT_DIR / 'persone.json'
    out_f = OUT_DIR / 'fondazioni.json'
    with open(out_p, 'w', encoding='utf-8') as f:
        json.dump(final_persone, f, ensure_ascii=False, indent=2)
    with open(out_f, 'w', encoding='utf-8') as f:
        json.dump(all_fondazioni, f, ensure_ascii=False, indent=2)

    print(f'Salvato: {out_p}')
    print(f'Salvato: {out_f}')

if __name__ == '__main__':
    main()
