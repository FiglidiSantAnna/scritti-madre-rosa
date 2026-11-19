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
    """Divide la sezione in blocchi numerati. Una nuova voce inizia solo se il
    numero e' il successivo (N+1) di quello precedente: cosi' date come
    "5.5.1836." o riferimenti numerici a inizio paragrafo restano nel testo
    della voce che li contiene."""
    parts = re.split(r'(?=<p>(?:<[^>]+>)?\s*\d+\.)', section_html)
    blocks, last = [], 0
    for part in parts:
        m = re.match(r'<p>(?:<[^>]+>)?\s*(\d+)\.', part)
        if m and int(m.group(1)) == last + 1:
            blocks.append(part)
            last += 1
        elif blocks:
            blocks[-1] += part
        else:
            blocks.append(part)
    return blocks

UP = "A-ZÀ-ÖØ-Þ"
PARTICLES = {'DI', 'DE', 'DEL', 'DELLA', 'DEI', 'DEGLI', 'DA', 'LA', 'LO', 'DAL'}
NAME_RE = re.compile(
    rf"^((?:[{UP}][{UP}'’\-]+(?:\s+|(?=[,.;]|$)))+)?"
    rf"(\((?:[^()]|\([^)]*\))*\))?\s*"
    rf"((?:[{UP}][{UP}'’\-]+(?:\s+|(?=[,.;]|$)))*)")

def parse_name_block(block_html):
    """Ritorna (cognome, titolo, nome) dal blocco della voce (nome in maiuscolo)."""
    text = strip_tags(block_html)
    text = re.sub(r'^\d+\.\s*', '', text).replace('\n', ' ')
    m = NAME_RE.match(text)
    if not m:
        return '', '', ''
    pre = (m.group(1) or '').split()
    titolo = (m.group(2) or '').strip('() ').strip()
    post = (m.group(3) or '').split()
    if not pre and post:          # nessun cognome prima della parentesi
        pre, post = post[:1], post[1:]
    if len(pre) == 1 and not titolo and not post:   # "MARGHERITA di SAVOIA, Regina"
        mm = re.match(r"[A-ZÀ-ÖØ-Þ][A-ZÀ-ÖØ-Þ'’\-]+\s+((?:di|de|del|della|dei|degli|da)\s+[A-ZÀ-ÖØ-Þ][A-Za-zÀ-ÿ'’\-]+)", text)
        if mm:
            pre = pre + mm.group(1).upper().split()
    if len(pre) == 1 and pre[0] in PARTICLES and post:   # "DI (Mons.) MARZO NICCOLA"
        pre, post = pre + post[:1], post[1:]
    if not titolo and len(pre) > 1 and not any(t in PARTICLES for t in pre[1:]):
        pre, post = pre[:1], pre[1:] + post       # "CUSTO CARLOTTA"
    # altrimenti "MARGHERITA DI SAVOIA": il nome resta intero nel cognome
    return ' '.join(pre), titolo, ' '.join(post)

ROMAN = re.compile(r'^(?=[IVXL]+$)(?:X{0,3})(?:IX|IV|V?I{0,3})$')
def tc(s):
    return ' '.join(w if ROMAN.match(w) else w.capitalize() for w in s.split())

# Cognomi che sono anche parole comuni: mai usati da soli come alias
STOP_SURNAME = {'papa', 'speranza', 'conti', 'palma', 'mosso', 'galli', 'grandi',
                'bosco', 'leone', 'mola', 'picco', 'sordi', 'durante', 'merli',
                'cenni', 'gentili', 'colli', 'dosi', 'di', 'margherita', 'custo'}
TITLE_ABBR = {
    'padre': ['padre', 'p.'], 'don': ['don'], 'mons.': ['mons.', 'monsignor'],
    'cardinale': ['card.', 'cardinale'], 'vescovo': ['mons.', 'vescovo'],
    'arcivescovo': ['mons.', 'arcivescovo'], 'avvocato': ['avv.', 'avvocato'],
    'avv.': ['avv.', 'avvocato'], 'mons': ['mons.', 'monsignor'], 'sacerdote': ['don'], 'canonico': ['can.', 'canonico'],
}

def is_nun(titolo):
    return titolo.lower().startswith('sr')

def parse_person_entry(block, tipo, file_num, num_str):
    block = block.strip()
    sur, titolo, giv = parse_name_block(block)
    cognome, nome = tc(sur), tc(giv)
    display = ' '.join(x for x in [cognome, f'({titolo})' if titolo else '', nome] if x)
    text = strip_tags(block)
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
        'lettere_citate': extract_letter_refs(text),
        'aliases': [],
        'refs': []
    }

def li_blocks(section_html):
    out = []
    for n, m in enumerate(re.finditer(r'<li>(.*?)</li>', section_html, re.S), 1):
        out.append(re.sub(r'^<p>', f'<p>{n}. ', m.group(1).strip(), count=1))
    return out

def entries_from_section(section_html, tipo, file_num):
    blocks = li_blocks(section_html) if '<li>' in section_html else split_numbered_entries(section_html)
    entries = []
    for block in blocks:
        m = re.match(r'^(\d+)\.', strip_tags(block).strip())
        if not m:
            continue
        entries.append(parse_person_entry(block, tipo, file_num, m.group(1)))
    return entries

def parse_destinatari(section_html, file_num):
    return entries_from_section(section_html, 'destinatario', file_num)

def parse_persone_di_rilievo(section_html, file_num):
    return entries_from_section(section_html, 'persona_di_rilievo', file_num)

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

def sections_of(html):
    """Ritorna {'dest':..., 'pers':..., 'fond':...} (html) per un file di Lettere.
    Riconosce le intestazioni <h4> (titoli con refusi inclusi: «DESTINARI»,
    «IL INDICE»); per la sezione persone taglia dove inizia «IV. FONDAZIONI»
    quando questa e' un semplice paragrafo (volume 2)."""
    heads = [(m.start(), m.end(), strip_tags(m.group(0)))
             for m in re.finditer(r'<h4[^>]*>.*?</h4>', html, re.S)]
    out = {}
    for i, (st, en, title) in enumerate(heads):
        t = title.upper()
        end = heads[i+1][0] if i+1 < len(heads) else len(html)
        body = html[en:end]
        if 'RILIEVO' in t:
            cut = re.search(r'<p>\s*(?:<[^>]+>)?\s*IV\.\s*FONDAZIONI', body)
            out['pers'] = body[:cut.start()] if cut else body
        elif 'DESTINA' in t or 'DESTINARI' in t:
            out['dest'] = body
        elif 'FONDAZIONI' in t:
            out['fond'] = html[st:end]
    return out


def parse_fondazioni_vol_2_5(sec_html, file_num):
    """Volumi 2 e 5: fondazioni senza la numerazione/formattazione degli altri
    volumi. Vol. 2: voci numerate "1. PIACENZA, Casa Madre."; vol. 5: voci
    introdotte da una riga "LUOGO, opera" tutta in maiuscolo iniziale."""
    paras = re.findall(r'<p>.*?</p>', sec_html, re.S)
    heads = []                      # (indice paragrafo, riga titolo)
    for i, p in enumerate(paras):
        t = strip_tags(p).strip()
        t = re.sub(r'^\d+\.\s*', '', t)
        if len(t) < 110 and re.match(rf"^[{UP}][{UP}' ]{{2,}}[,.]\s*", t) and not re.match(r'^[IVX]+\.', t):
            heads.append((i, t.rstrip('.').strip()))
    entries = []
    for k, (i, title) in enumerate(heads):
        j = heads[k+1][0] if k+1 < len(heads) else len(paras)
        luogo_raw, _, opera = re.sub(r'^([A-ZÀ-ÖØ-Þ\' ]+)\.\s', r'\1, ', title).partition(',')
        luogo = luogo_raw.strip().title()
        opera = opera.strip()
        display = f"{luogo}, {opera}" if opera else luogo
        entries.append({
            'id': f"fond-{file_num}-{k+1}", 'tipo': 'fondazione',
            'file_source': file_num, 'voce_num': k+1,
            'nome_display': display, 'luogo': luogo, 'provincia': '',
            'tipo_opera': opera,
            'scheda_html': ''.join(paras[i:j]),
            'lettere_citate': extract_letter_refs(strip_tags(''.join(paras[i:j]))),
            'aliases': [norm(luogo), norm(display)], 'refs': []})
    return entries

# ─── dedup / unione ──────────────────────────────────────────────────────────

# Voci di volumi diversi che indicano la stessa persona e che la regola
# automatica non riconosce (nome scritto in modo diverso): (id, id)
MANUAL_SAME = [
    ('dest-2-31', 'dest-5-45'),    # Tornatore, Sr. Anna Maria Teresa (superiora)
    ('dest-2-3', 'dest-5-8'),      # «Camusa» (refuso del vol. 2) = Camisa, Sr. Anna Francesca
    ('dest-8-30', 'dest-11-41'),   # Leone XIII = card. Gioacchino Pecci
]

def tokens(p):
    return norm(f"{p['cognome']} {p['nome']}").replace("'", '').split()

def same_person(a, b):
    if is_nun(a['titolo']) != is_nun(b['titolo']):
        return False
    ja, jb = ''.join(tokens(a)), ''.join(tokens(b))
    if ja and ja == jb:
        return True
    ca, cb = norm(a['cognome']).replace(' ', ''), norm(b['cognome']).replace(' ', '')
    if ca != cb and not (ca.startswith(cb) or cb.startswith(ca)):
        return False
    ga, gb = set(norm(a['nome']).split()), set(norm(b['nome']).split())
    if is_nun(a['titolo']):
        # suore: stesso nome di religione (titolo) e nome civile compatibile
        if norm(a['titolo']) != norm(b['titolo']):
            return False
    if not ga or not gb:
        return False
    return ga <= gb or gb <= ga

VOLUMI = {2: (1, '1864-1870'), 5: (2, '1871-1872'), 8: (3, '1873-1874'),
          11: (4, '1875-1877'), 13: (5, '1878-1879'), 16: (6, '1880-1881')}

def merge_people(people):
    by_id = {p['id']: p for p in people}
    groups = []     # liste di voci della stessa persona
    for p in people:
        for g in groups:
            if any(same_person(p, q) or (p['id'], q['id']) in MANUAL_SAME
                   or (q['id'], p['id']) in MANUAL_SAME for q in g):
                g.append(p)
                break
        else:
            groups.append([p])
    merged = []
    for g in groups:
        g.sort(key=lambda x: (x['file_source'], x['voce_num']))
        base = dict(g[0])
        if len(g) > 1:
            # nome visualizzato: la forma piu' completa
            from collections import Counter
            cnt = Counter(x['nome_display'] for x in g)
            best = max(g, key=lambda x: (cnt[x['nome_display']], len(x['nome_display'])))
            for k in ('nome_display', 'cognome', 'titolo', 'nome'):
                base[k] = best[k]
            parts = []
            for x in g:
                v, anni = VOLUMI[x['file_source']]
                parts.append(f'<p class="vol-label"><em>— Dall\'indice del volume {v} delle Lettere ({anni}) —</em></p>'
                             + x['scheda_html'])
            base['scheda_html'] = '\n'.join(parts)
            base['lettere_citate'] = sorted({n for x in g for n in x['lettere_citate']})
            base['unita_da'] = [x['id'] for x in g]
        base['tipo'] = 'destinatario' if any(x['tipo'] == 'destinatario' for x in g) else base['tipo']
        merged.append(base)
    return merged

PREFER = {'padre tornatore': 'Tornatore (Padre) Giovanni Battista',
          'p. tornatore': 'Tornatore (Padre) Giovanni Battista',
          'tornatore': 'Tornatore (Padre) Giovanni Battista'}
EXTRA_ALIASES = {
    'Margherita Di Savoia': ['margherita di savoia', 'regina margherita'],
    'Pio IX': ['papa pio ix', 'pio ix'],
}

def build_aliases(people):
    by_sur = {}
    for p in people:
        by_sur.setdefault(norm(p['cognome']), []).append(p)
    for p in people:
        sur = norm(p['cognome']); giv = norm(p['nome']); tit = norm(p['titolo'].split(',')[0])
        al = []
        if sur and giv:
            al += [f'{sur} {giv}', f'{giv} {sur}']
            # forme senza nomi secondari: "gaspare barbiellini"
            first = giv.split()[0]
            if first != giv:
                al.append(f'{first} {sur}')
        if tit and not is_nun(p['titolo']) and sur:
            head = tit.split()[0]
            for ab in TITLE_ABBR.get(head, [head]):
                al.append(f'{ab} {sur}')
        # cognome da solo: solo se non ambiguo e non parola comune
        same = by_sur[sur]
        bare_ok = False
        if len(same) == 1:
            bare_ok = True
        else:
            non_nuns = [q for q in same if not is_nun(q['titolo'])]
            bare_ok = (len(non_nuns) == 1 and non_nuns[0] is p)
        if bare_ok and len(sur) >= 5 and sur not in STOP_SURNAME:
            al.append(sur)
        seen = []
        for a in al:
            a = a.strip()
            if len(a) >= 5 and a not in seen:
                seen.append(a)
        p['aliases'] = seen
    # alias condivisi da piu' persone: ambigui, tolti (salvo preferenza esplicita)
    owners = {}
    for p in people:
        for a in p['aliases']:
            owners.setdefault(a, []).append(p)
    for a, ps in owners.items():
        if len(ps) > 1:
            pref = [q for q in ps if PREFER.get(a) == q['nome_display']]
            for q in ps:
                if not pref or q is not pref[0]:
                    q['aliases'].remove(a)
    for p in people:
        p['aliases'] += [a for a in EXTRA_ALIASES.get(p['nome_display'], []) if a not in p['aliases']]

def main():
    all_persone = []
    all_fondazioni = []

    for n in [2, 5, 8, 11, 13, 16]:
        with open(LETTERE_IT / f'{n}.json', encoding='utf-8') as f:
            data = json.load(f)
        html = ''.join(s['h'] for s in data['sections'])
        print(f'\n=== File {n} ===')
        secs = sections_of(html)

        if 'dest' in secs:
            entries = parse_destinatari(secs['dest'], n)
            print(f'  DESTINATARI: {len(entries)} voci')
            all_persone.extend(entries)

        if n in (2, 5):
            fs = secs.get('fond')
            if n == 2:
                i0 = html.find('IV. FONDAZIONI'); j0 = html.find('<h4', i0)
                fs = html[i0:j0] if i0 >= 0 else None
            if fs:
                entries = parse_fondazioni_vol_2_5(fs, n)
                print(f'  FONDAZIONI (vol. 2/5): {len(entries)} voci')
                all_fondazioni.extend(entries)
        if 'LE FONDAZIONI' in html:       # fondazioni: solo i volumi con intestazione "LE FONDAZIONI"
            sec = get_section_html(html, 'LE FONDAZIONI')
            entries = parse_fondazioni(sec, n)
            print(f'  FONDAZIONI: {len(entries)} voci')
            all_fondazioni.extend(entries)

        if 'pers' in secs:
            entries = parse_persone_di_rilievo(secs['pers'], n)
            print(f'  PERSONE DI RILIEVO: {len(entries)} voci')
            all_persone.extend(entries)

    all_persone = [p for p in all_persone if p['cognome']]
    final_persone = merge_people(all_persone)
    build_aliases(final_persone)

    print(f'\n=== TOTALI ===')
    print(f'Voci lette: {len(all_persone)}  ->  persone dopo unione: {len(final_persone)}')
    for p in final_persone:
        if p.get('unita_da'):
            print('  UNITE:', p['nome_display'], p['unita_da'])
    # alias di luogo condivisi (es. «piacenza»): vanno alla prima voce
    seen_al = set()
    for fd in all_fondazioni:
        fd['aliases'] = [a for a in dict.fromkeys(fd['aliases']) if a not in seen_al]
        seen_al.update(fd['aliases'])
    print(f'Fondazioni: {len(all_fondazioni)}')

    with open(OUT_DIR / 'persone.json', 'w', encoding='utf-8') as f:
        json.dump(final_persone, f, ensure_ascii=False, indent=2)
    with open(OUT_DIR / 'fondazioni.json', 'w', encoding='utf-8') as f:
        json.dump(all_fondazioni, f, ensure_ascii=False, indent=2)

if __name__ == '__main__':
    main()
