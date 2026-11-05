"""Reference bases imported from one .xlsx workbook, one tab per base, and their lookups.

Standard library only: an .xlsx file is a zip of XML parts.
"""
import io
import re
import unicodedata
import xml.etree.ElementTree as ET
import zipfile

MAX_UPLOAD = 10 * 1024 * 1024  # bytes of the .xlsx file
MAX_PART = 60 * 1024 * 1024  # uncompressed size of one zip part (guards against zip bombs)
MAX_ROWS = 20000
HEADER_SEARCH = 20  # rows scanned for the header line (title rows may come first)
SUGGESTIONS = 10
XLSX_NS = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
REL_NS = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'
PKG_REL_NS = '{http://schemas.openxmlformats.org/package/2006/relationships}'
BASE_LISTS = {'fornecedores': ('transportador', 'fornecedor', 'motivo'),
              'frota': ('placa_caminhao', 'placa_carro', 'condutor', 'auxiliar', 'rota')}
LIST_TYPES = sum(BASE_LISTS.values(), ())
PLATE_TYPES = ('placa_caminhao', 'placa_carro')
PLATE_FORMAT = re.compile(r'[A-Z]{3}[0-9][A-Z0-9][0-9]{2}')
# A tab belongs to the base whose word appears in its name (normalized), e.g. "Acesso de Terceiros".
TAB_WORDS = {'COLABORADOR': 'colaboradores', 'TERCEIR': 'terceirizados', 'FORNECEDOR': 'fornecedores', 'PLACA': 'frota'}
TAB_HINT = 'Colaboradores, Acesso de Terceiros, Fornecedores e Placa do carro e caminhão'

# Spreadsheet header (normalized) -> column key. Columns not listed (birth date, admission, manager…) are not stored.
BASES = {
    'colaboradores': {'columns': {'MATRICULA': 'matricula', 'NOME COMPLETO': 'nome', 'NOME': 'nome', 'CARGO': 'cargo', 'SITUACAO': 'situacao'},
                      'required': ('matricula', 'nome'), 'any_of': (), 'headers': 'Situação, Matricula, Nome Completo, Cargo'},
    'terceirizados': {'columns': {'NOME': 'nome', 'NOME COMPLETO': 'nome', 'CPF': 'cpf', 'RG': 'rg', 'EMPRESA/TRANSPORTADORA': 'empresa', 'EMPRESA': 'empresa', 'TRANSPORTADORA': 'empresa'},
                      'required': ('nome',), 'any_of': ('cpf', 'rg'), 'headers': 'Nome, CPF, RG, Empresa/Transportadora'},
    'fornecedores': {'columns': {'TRANSPORTADOR': 'transportador', 'TRANSPORTADORA': 'transportador', 'FORNECEDOR': 'fornecedor', 'MOTIVO': 'motivo'},
                     'required': (), 'any_of': ('transportador', 'fornecedor', 'motivo'), 'headers': 'Transportador, Fornecedor, Motivo'},
    'frota': {'columns': {'PLACAS DOS CAMINHOES': 'placa_caminhao', 'PLACA DO CAMINHAO': 'placa_caminhao', 'PLACAS DOS CARROS': 'placa_carro', 'PLACA DO CARRO': 'placa_carro', 'CONDUTOR': 'condutor', 'AUXILIAR': 'auxiliar', 'ROTA': 'rota', 'ROTAS': 'rota'},
              'required': (), 'any_of': BASE_LISTS['frota'], 'headers': 'Placas dos Caminhoes, Placa do Carro, Condutor, Auxiliar, Rota'},
}


def create_tables(c):
    c.executescript('''
    CREATE TABLE IF NOT EXISTS base_colaboradores(matricula TEXT PRIMARY KEY, nome TEXT NOT NULL,
      cargo TEXT NOT NULL DEFAULT '', situacao TEXT NOT NULL DEFAULT '', updated_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS base_terceiros(chave TEXT PRIMARY KEY, nome TEXT NOT NULL, cpf TEXT NOT NULL DEFAULT '',
      rg TEXT NOT NULL DEFAULT '', empresa TEXT NOT NULL DEFAULT '', updated_at TEXT NOT NULL);
    CREATE INDEX IF NOT EXISTS base_terceiros_cpf ON base_terceiros(cpf);
    CREATE INDEX IF NOT EXISTS base_terceiros_rg ON base_terceiros(rg);
    CREATE TABLE IF NOT EXISTS base_listas(tipo TEXT NOT NULL, valor TEXT NOT NULL, PRIMARY KEY(tipo, valor));
    ''')


def plain(text):
    """Uppercase without accents and with single spaces: how headers are matched."""
    text = unicodedata.normalize('NFKD', str(text)).encode('ascii', 'ignore').decode()
    return re.sub(r'\s*/\s*', '/', re.sub(r'\s+', ' ', text)).strip().upper()


def digits(value):
    return re.sub(r'\D', '', str(value))


def cpf_key(value):
    """CPF as 11 digits; Excel drops the leading zeros of CPFs typed as numbers."""
    number = digits(value)
    return number.zfill(11) if 0 < len(number) <= 11 else number


def rg_key(value):
    return re.sub(r'[^0-9A-Z]', '', str(value).upper())


def clean_plate(value: str) -> str:
    """Plate as the records store it (ABC1234 or ABC1D23); empty when it is not a valid plate."""
    plate = re.sub(r'[\s-]', '', str(value).upper())
    return plate if PLATE_FORMAT.fullmatch(plate) else ''


def _column(ref, fallback):
    letters = re.match(r'[A-Z]+', ref or '')
    if not letters:
        return fallback
    index = 0
    for ch in letters.group():
        index = index * 26 + ord(ch) - 64
    return index - 1


def _cell_text(cell, shared):
    kind, value = cell.get('t'), cell.find(XLSX_NS + 'v')
    if kind == 'inlineStr':
        return ''.join(t.text or '' for t in cell.iter(XLSX_NS + 't'))
    text = value.text if value is not None and value.text else ''
    if kind == 's':
        return shared[int(text)] if text.isdigit() and int(text) < len(shared) else ''
    if kind in (None, 'n') and text:
        try:
            number = float(text)
            return str(int(number)) if number.is_integer() else text  # matrícula 114993, not 114993.0
        except ValueError:
            return text
    return text


def _workbook_tabs(z: zipfile.ZipFile) -> list[tuple[str, str]]:
    """(tab name, path of its part in the zip) in workbook order."""
    workbook = ET.fromstring(z.read('xl/workbook.xml'))
    rels = ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))
    targets = {r.get('Id'): r.get('Target') for r in rels.iter(PKG_REL_NS + 'Relationship')}
    tabs = []
    for sheet in workbook.iter(XLSX_NS + 'sheet'):
        target = targets[sheet.get(REL_NS + 'id')]
        tabs.append((sheet.get('name') or '', target.lstrip('/') if target.startswith('/') else 'xl/' + target))
    return tabs


def _tab_base(name: str) -> str | None:
    tab = plain(name)
    return next((base for word, base in TAB_WORDS.items() if word in tab), None)


def _sheet_rows(sheet: ET.Element, shared: list[str], tab: str) -> list[list[str]]:
    """Rows of a tab as lists of strings."""
    rows = []
    for row in sheet.iter(XLSX_NS + 'row'):
        cells, position = {}, -1
        for cell in row.iter(XLSX_NS + 'c'):
            position = _column(cell.get('r'), position + 1)
            cells[position] = _cell_text(cell, shared).strip()
        rows.append([cells.get(i, '') for i in range(max(cells) + 1)] if cells else [])
        if len(rows) > MAX_ROWS + HEADER_SEARCH:
            raise ValueError(f'A aba "{tab}" tem mais de {MAX_ROWS} linhas.')
    return rows


def read_workbook(data: bytes) -> tuple[dict[str, tuple[str, list[list[str]]]], list[str]]:
    """{base: (tab name, rows)} for the tabs that belong to a base, and the names of the other tabs."""
    found, ignored = {}, []
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            if any(info.file_size > MAX_PART for info in z.infolist()):
                raise ValueError('A planilha é grande demais. Divida em arquivos menores.')
            shared = []
            if 'xl/sharedStrings.xml' in z.namelist():
                for item in ET.fromstring(z.read('xl/sharedStrings.xml')).iter(XLSX_NS + 'si'):
                    shared.append(''.join(t.text or '' for t in item.iter(XLSX_NS + 't')))
            for tab, part in _workbook_tabs(z):
                base = _tab_base(tab)
                if not base:
                    ignored.append(tab)
                elif base in found:
                    raise ValueError(f'As abas "{found[base][0]}" e "{tab}" são da mesma base. Deixe só uma ou renomeie a outra.')
                else:
                    found[base] = (tab, _sheet_rows(ET.fromstring(z.read(part)), shared, tab))
    except (zipfile.BadZipFile, KeyError, ET.ParseError):
        raise ValueError('O arquivo não é uma planilha .xlsx válida. Salve no Excel como "Pasta de Trabalho do Excel (.xlsx)".')
    if not found:
        raise ValueError(f'Nenhuma aba reconhecida. Use abas com estes nomes: {TAB_HINT}.')
    return found, ignored


def _header(rows, base):
    """Index of the header row and {column key: cell index}."""
    spec = BASES[base]
    for index, row in enumerate(rows[:HEADER_SEARCH]):
        found = {}
        for position, cell in enumerate(row):
            key = spec['columns'].get(plain(cell))
            if key and key not in found:
                found[key] = position
        if found and all(k in found for k in spec['required']) and (not spec['any_of'] or any(k in found for k in spec['any_of'])):
            return index, found
    raise ValueError(f"Não encontrei os cabeçalhos. Colunas esperadas: {spec['headers']}.")


def _records(rows, base):
    start, columns = _header(rows, base)
    for row in rows[start + 1:]:
        values = {k: (row[i] if i < len(row) else '').strip().upper()[:200] for k, i in columns.items()}
        if any(values.values()):
            yield values


def import_workbook(c, data: bytes, stamp: str) -> dict:
    """Imports every recognized tab. Any error is raised naming the tab; the caller's rollback then discards all tabs."""
    tabs, ignored = read_workbook(data)
    imported = {}
    for base, (tab, rows) in tabs.items():
        try:
            imported[base] = import_base(c, base, rows, stamp)
        except ValueError as error:
            raise ValueError(f'Aba "{tab}": {error} Nada foi importado.')
    return {'abas': imported, 'ignoradas': ignored}


def import_base(c, base, rows, stamp):
    """Adds new entries and updates existing ones (by matrícula, CPF/RG or value). Returns counts for the screen."""
    counts = {'novos': 0, 'atualizados': 0, 'ignorados': 0}

    def save(exists_sql, key, upsert_sql, params):
        existed = c.execute(exists_sql, (key,)).fetchone()
        c.execute(upsert_sql, params)
        counts['atualizados' if existed else 'novos'] += 1

    for values in _records(rows, base):
        if base == 'colaboradores':
            matricula = values['matricula'].lstrip('0') or values['matricula']
            if not matricula or not values['nome']:
                counts['ignorados'] += 1
                continue
            save('SELECT 1 FROM base_colaboradores WHERE matricula=?', matricula,
                 'INSERT INTO base_colaboradores VALUES(?,?,?,?,?) ON CONFLICT(matricula) DO UPDATE SET nome=excluded.nome,cargo=excluded.cargo,situacao=excluded.situacao,updated_at=excluded.updated_at',
                 (matricula, values['nome'], values.get('cargo', ''), values.get('situacao', ''), stamp))
        elif base == 'terceirizados':
            cpf, rg = cpf_key(values.get('cpf', '')), rg_key(values.get('rg', ''))
            if not values['nome'] or not (cpf or rg):
                counts['ignorados'] += 1
                continue
            key = 'CPF:' + cpf if cpf else 'RG:' + rg
            save('SELECT 1 FROM base_terceiros WHERE chave=?', key,
                 'INSERT INTO base_terceiros VALUES(?,?,?,?,?,?) ON CONFLICT(chave) DO UPDATE SET nome=excluded.nome,cpf=excluded.cpf,rg=excluded.rg,empresa=excluded.empresa,updated_at=excluded.updated_at',
                 (key, values['nome'], cpf, rg, values.get('empresa', ''), stamp))
        else:
            for kind in BASE_LISTS[base]:
                value = values.get(kind, '')
                if not value:
                    continue
                if kind in PLATE_TYPES:
                    value = clean_plate(value)
                    if not value:  # the record form would refuse it
                        counts['ignorados'] += 1
                        continue
                added = c.execute('INSERT OR IGNORE INTO base_listas VALUES(?,?)', (kind, value)).rowcount
                counts['novos' if added else 'atualizados'] += 1
    if not counts['novos'] and not counts['atualizados']:
        detail = f" ({counts['ignorados']} linhas sem os dados obrigatórios)" if counts['ignorados'] else ''
        raise ValueError(f'Nenhuma linha foi importada{detail}.')
    return counts


def summary(c):
    one = lambda sql: c.execute(sql).fetchone()
    colab, terc = one('SELECT COUNT(*), MAX(updated_at) FROM base_colaboradores'), one('SELECT COUNT(*), MAX(updated_at) FROM base_terceiros')
    lists = dict(c.execute('SELECT tipo, COUNT(*) FROM base_listas GROUP BY tipo').fetchall())
    return {'colaboradores': {'total': colab[0], 'atualizado': colab[1]},
            'terceirizados': {'total': terc[0], 'atualizado': terc[1]},
            **{base: {k: lists.get(k, 0) for k in kinds} for base, kinds in BASE_LISTS.items()}}


def lists(c):
    """Choice lists of the Devoluções, Rotas and Veículos forms, sent to every logged-in user (no documents)."""
    result = {k: [] for k in LIST_TYPES}
    for kind, value in c.execute('SELECT tipo, valor FROM base_listas ORDER BY valor'):
        result[kind].append(value)
    return result


def _like(text):
    return '%' + re.sub(r'([%_\\])', r'\\\1', text.upper()) + '%'


def find_colaboradores(c, query):
    """Exact matrícula first, then names containing the text."""
    query = str(query).strip()[:100]
    if len(query) < 2:
        return []
    found = []
    if digits(query) == query:
        found = c.execute('SELECT matricula,nome,cargo,situacao FROM base_colaboradores WHERE matricula=?', (query.lstrip('0') or query,)).fetchall()
    found += c.execute("SELECT matricula,nome,cargo,situacao FROM base_colaboradores WHERE nome LIKE ? ESCAPE '\\' ORDER BY nome LIMIT ?", (_like(query), SUGGESTIONS)).fetchall()
    unique = {r['matricula']: dict(r) for r in found}
    return list(unique.values())[:SUGGESTIONS]


def find_terceiro_document(c, document):
    """Name and company for a CPF or RG typed in Cadastro de pessoas (the documents themselves are not returned)."""
    cpf, rg = cpf_key(document), rg_key(document)
    if len(rg) < 4:
        return None
    row = c.execute("SELECT nome, empresa FROM base_terceiros WHERE (cpf<>'' AND cpf=?) OR (rg<>'' AND rg=?) LIMIT 1", (cpf, rg)).fetchone()
    return dict(row) if row else None


def find_terceiros(c, query):
    query = str(query).strip()[:100]
    if len(query) < 2:
        return []
    rows = c.execute("SELECT nome, empresa FROM base_terceiros WHERE nome LIKE ? ESCAPE '\\' ORDER BY nome LIMIT ?", (_like(query), SUGGESTIONS))
    return [dict(r) for r in rows]
