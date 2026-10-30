"""GateFlow — Python 3.10+ standard library and SQLite. No dependencies."""
import argparse
from contextlib import closing
import datetime as dt
import hashlib
import hmac
import json
import mimetypes
import os
from pathlib import Path
import re
import secrets
import sqlite3
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from http.cookies import SimpleCookie
from urllib.parse import parse_qs, urlsplit
import bases

ROOT = Path(__file__).resolve().parent  # bundled files (schema, static)
# Folder of the .exe when packaged, so config.json and local data live beside it.
APP_DIR = Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else ROOT
CONFIG = APP_DIR / 'config.json'
SCHEMA = json.loads((ROOT / 'schema.json').read_text(encoding='utf-8'))
MODULES = {m['id']: m for m in SCHEMA}
STATUSES = ['Em aberto', 'Concluído', 'Ocorrência']
DB_NAME = 'portaria.db'
DB = APP_DIR / 'dados' / DB_NAME
DEFAULT_PORT = 8780
BACKUP_EVERY = 6 * 3600  # seconds between automatic backups
BACKUP_KEEP = 60
BACKUP_CHECK = 600  # how often the background thread checks whether a backup is due
LOCK = threading.Lock()
RATE = {}
ONLINE_WINDOW = 120  # seconds without activity before a user shows as offline
SEEN_THROTTLE = 30  # avoid a database write on every request
UPPERCASE_KINDS = ('text', 'textarea')  # typed text is stored in uppercase; options, dates and numbers are not
ESCANINHOS = 216  # doors drawn in static/escaninhos.svg
ARMARIOS = 200  # doors per locker room in static/vestiario.svg (shared by both rooms)
# Door maps of the "chaves" module: payload field, door count, locker room filter and settings key of blocked doors.
DOOR_MAPS = {
    'escaninhos': {'field': 'escaninho', 'total': ESCANINHOS, 'name': 'escaninho', 'vestiario': None, 'setting': 'escaninhos_bloqueados'},
    'masculino': {'field': 'armario', 'total': ARMARIOS, 'name': 'armário masculino', 'vestiario': 'Masculino', 'setting': 'armarios_masculino_bloqueados'},
    'feminino': {'field': 'armario', 'total': ARMARIOS, 'name': 'armário feminino', 'vestiario': 'Feminino', 'setting': 'armarios_feminino_bloqueados'},
}

class Conflict(ValueError):
    """Valid request that clashes with the current data (answered with 409)."""

def now():
    return dt.datetime.now(dt.timezone(dt.timedelta(hours=-3))).isoformat(timespec='seconds')

def connect():
    c = sqlite3.connect(DB, timeout=20)
    c.row_factory = sqlite3.Row
    c.execute('PRAGMA foreign_keys=ON')
    return c

def initialize():
    DB.parent.mkdir(parents=True, exist_ok=True)
    # closing() is required: sqlite3's own context manager commits but never closes,
    # which keeps the file locked on Windows.
    with closing(connect()) as c, c:
        if c.execute('PRAGMA quick_check').fetchone()[0]!='ok':
            raise SystemExit(f'O banco {DB} está danificado. Não use o sistema e restaure a cópia mais recente da pasta {DB.parent / "backups"}.')
        # Rollback journal, not WAL: WAL needs shared memory on one machine and breaks on network folders.
        c.executescript('''
        PRAGMA journal_mode=DELETE;
        CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, name TEXT NOT NULL,
          username TEXT NOT NULL UNIQUE COLLATE NOCASE, password TEXT NOT NULL,
          role TEXT NOT NULL CHECK(role IN ('admin','operador')), active INTEGER NOT NULL DEFAULT 1,
          created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY, user_id INTEGER REFERENCES users(id),
          csrf TEXT NOT NULL, expires REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS records(id INTEGER PRIMARY KEY, module TEXT NOT NULL,
          payload TEXT NOT NULL, status TEXT NOT NULL, created_by INTEGER REFERENCES users(id),
          created_at TEXT NOT NULL, updated_at TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1);
        CREATE INDEX IF NOT EXISTS records_module ON records(module,created_at);
        CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY, actor TEXT NOT NULL,
          action TEXT NOT NULL, entity TEXT NOT NULL, details TEXT NOT NULL, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
        INSERT OR IGNORE INTO settings VALUES('unidade','CD Bahia');
        ''')
        bases.create_tables(c)
        columns={r[1] for r in c.execute('PRAGMA table_info(records)')}
        if 'returned_by' not in columns:
            c.execute('ALTER TABLE records ADD COLUMN returned_by INTEGER REFERENCES users(id)')
            c.execute('ALTER TABLE records ADD COLUMN returned_at TEXT')
        user_columns={r[1] for r in c.execute('PRAGMA table_info(users)')}
        if 'last_seen' not in user_columns:
            c.execute('ALTER TABLE users ADD COLUMN last_seen REAL')
        if 'modules' not in user_columns:
            # JSON list of module ids an operator may use; NULL means every module.
            c.execute('ALTER TABLE users ADD COLUMN modules TEXT')
        # Cadastro de pessoas: CPF and RG became a single "documento" field.
        for rid,raw in c.execute("SELECT id,payload FROM records WHERE module='pessoas'").fetchall():
            payload=json.loads(raw)
            if 'cpf' in payload or 'rg' in payload:
                cpf,rg=payload.pop('cpf',''),payload.pop('rg','')
                payload['documento']=payload.get('documento') or cpf or rg
                c.execute('UPDATE records SET payload=? WHERE id=?',(json.dumps(payload,ensure_ascii=False),rid))
        # Saída de materiais no longer has "cargo".
        for rid,raw in c.execute("SELECT id,payload FROM records WHERE module='materiais'").fetchall():
            payload=json.loads(raw)
            if 'cargo' in payload:
                payload.pop('cargo')
                c.execute('UPDATE records SET payload=? WHERE id=?',(json.dumps(payload,ensure_ascii=False),rid))
        # Modules without a life cycle are always stored as concluded, so they never count as open.
        for module in [m['id'] for m in SCHEMA if m.get('status') is False]:
            c.execute("UPDATE records SET status='Concluído' WHERE module=? AND status!='Concluído'",(module,))
        # Typed text is stored in uppercase; records saved before that rule are converted once.
        if not c.execute("SELECT 1 FROM settings WHERE key='texto_maiusculo'").fetchone():
            for rid,module,raw in c.execute('SELECT id,module,payload FROM records').fetchall():
                if module not in MODULES:continue
                keys={f[0] for f in MODULES[module]['fields'] if f[2] in UPPERCASE_KINDS}|{'observacoes'}
                payload=json.loads(raw)
                upper={k:(v.upper() if k in keys and isinstance(v,str) else v) for k,v in payload.items()}
                if upper!=payload:c.execute('UPDATE records SET payload=? WHERE id=?',(json.dumps(upper,ensure_ascii=False),rid))
            c.execute("INSERT INTO settings VALUES('texto_maiusculo','1')")

def backup_database(force=False):
    """Copies the database to <db folder>/backups unless a recent copy exists (any machine may have made it)."""
    folder=DB.parent/'backups';folder.mkdir(exist_ok=True)
    copies=sorted(folder.glob('portaria-*.db'))
    if not force and copies and time.time()-copies[-1].stat().st_mtime<BACKUP_EVERY:return None
    target=folder/f'portaria-{dt.datetime.now():%Y%m%d-%H%M%S}.db'
    with closing(connect()) as source, closing(sqlite3.connect(target)) as dest:source.backup(dest)
    for old in sorted(folder.glob('portaria-*.db'))[:-BACKUP_KEEP]:old.unlink(missing_ok=True)
    return target

def backup_loop():
    while True:
        try:
            done=backup_database()
            if done:print(f'Backup salvo em {done}',flush=True)
        except (OSError,sqlite3.Error) as e:
            print(f'ATENÇÃO: backup automático falhou ({e}). Verifique a pasta de rede.',flush=True)
        time.sleep(BACKUP_CHECK)

def configured_db(ask=input):
    """Database path from config.json beside the app; asks for the network folder on first use."""
    if CONFIG.exists():
        folder=json.loads(CONFIG.read_text(encoding='utf-8')).get('pasta_banco','')
    else:
        folder=ask('Informe a pasta de rede do banco (ex.: \\\\servidor\\portaria): ').strip().strip('"')
        if not folder:raise SystemExit('Nenhuma pasta informada.')
        CONFIG.write_text(json.dumps({'pasta_banco':folder},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    if not folder:raise SystemExit(f'Informe "pasta_banco" em {CONFIG}.')
    path=Path(folder)
    if not path.is_dir():
        raise SystemExit(f'Pasta do banco não encontrada: {path}\nVerifique a conexão com a rede ou corrija "pasta_banco" em {CONFIG}.')
    return path/DB_NAME

def password_hash(value):
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac('sha256', value.encode(), salt.encode(), 600000).hex()
    return f'{salt}:{digest}'

def password_ok(value, stored):
    salt, digest = stored.split(':')
    return hmac.compare_digest(hashlib.pbkdf2_hmac('sha256',value.encode(),salt.encode(),600000).hex(),digest)

def audit(c, user, action, entity, details=''):
    c.execute('INSERT INTO audit(actor,action,entity,details,created_at) VALUES(?,?,?,?,?)',
              (user['username'] if user else 'sistema', action, str(entity), details, now()))

def valid_user(data):
    name = data.get('name','')
    username = data.get('username','')
    password = data.get('password','')
    role = data.get('role','operador')
    if not all(isinstance(x,str) for x in (name,username,password,role)):
        raise ValueError('Dados de usuário inválidos.')
    if not 2 <= len(name.strip()) <= 100 or not re.fullmatch(r'[A-Za-z0-9_.-]{3,50}',username):
        raise ValueError('Informe nome e login de 3 a 50 caracteres (letras, números, ponto, hífen ou sublinhado).')
    if len(password)<10 or len(password)>200:
        raise ValueError('A senha deve ter entre 10 e 200 caracteres.')
    if role not in ('admin','operador'):
        raise ValueError('Perfil inválido.')
    return name.strip(), username, password_hash(password), role

def valid_modules(value,role):
    """Stored form of an operator's allowed modules: None (all) or a JSON list in schema order."""
    if role=='admin' or value is None:return None
    if not isinstance(value,list) or not value or not all(isinstance(m,str) and m in MODULES for m in value):
        raise ValueError('Selecione ao menos uma aba válida para o operador.')
    return json.dumps([m for m in MODULES if m in value])

def allowed_modules(user):
    if user['role']=='admin' or not user['modules']:return set(MODULES)
    return set(json.loads(user['modules']))&set(MODULES)

def validate_record(data):
    module = data.get('module')
    if not isinstance(module,str) or module not in MODULES:
        raise ValueError('Módulo inválido.')
    payload = data.get('payload')
    if not isinstance(payload,dict): raise ValueError('Informe os campos do registro em payload.')
    allowed = {f[0] for f in MODULES[module]['fields']} | {'observacoes'}
    if set(payload)-allowed: raise ValueError('O registro contém campos desconhecidos.')
    clean = {}
    for f in MODULES[module]['fields'] + [['observacoes','Observações','textarea',False]]:
        key,label,kind,required,*options = f
        value = payload.get(key,'')
        if not isinstance(value,(str,int,float)) or isinstance(value,bool): raise ValueError(f'{label}: valor inválido.')
        value = str(value).strip()
        if kind in UPPERCASE_KINDS: value = value.upper()
        if required and not value: raise ValueError(f'Preencha {label}.')
        if len(value)> (3000 if kind=='textarea' else 200): raise ValueError(f'{label}: texto muito longo.')
        if value and kind=='number':
            try:
                n=float(value)
                if not 0<=n<=1000000000: raise ValueError()
                if key in ('quantidade','volumes') and n<=0: raise ValueError()
                if key in ('volumes',) or (module=='grupos' and key=='quantidade'):
                    if not n.is_integer(): raise ValueError()
            except ValueError: raise ValueError(f'{label}: número inválido.')
        if value and kind=='select' and value not in options[0]: raise ValueError(f'{label}: opção inválida.')
        if value and kind=='datetime-local':
            try:
                parsed=dt.datetime.fromisoformat(value)
                if parsed.tzinfo is not None or 'T' not in value: raise ValueError()
                value=parsed.isoformat(timespec='seconds')
            except ValueError: raise ValueError(f'{label}: data/hora inválida; use horário local sem fuso.')
        if value and key=='placa':
            value=re.sub(r'[ -]','',value.upper())
            if not re.fullmatch(r'[A-Z]{3}[0-9][A-Z0-9][0-9]{2}',value): raise ValueError('Placa inválida. Use ABC1234 ou ABC1D23.')
        if value and module=='chaves' and key in ('escaninho','armario'):
            limit,name=(ESCANINHOS,'Escaninho') if key=='escaninho' else (ARMARIOS,'Armário')
            if not re.fullmatch(r'[0-9]{1,3}',value) or not 1<=int(value)<=limit: raise ValueError(f'{name}: informe um número de 1 a {limit}.')
            value=str(int(value))
        clean[key]=value
    if module=='chaves':
        if not clean.get('armario') and not clean.get('escaninho'): raise ValueError('Informe o armário ou o escaninho.')
        if bool(clean.get('armario'))!=bool(clean.get('vestiario')): raise ValueError('Informe o vestiário e o número do armário juntos.')
    for a,b in [('entrada','saida'),('saida','retorno'),('retirada','devolucao')]:
        if clean.get(a) and clean.get(b) and clean[b]<clean[a]: raise ValueError('O retorno/saída não pode ser anterior à entrada/retirada.')
    if clean.get('km_final') and float(clean['km_final'])<float(clean['km_inicial']): raise ValueError('KM final menor que o KM inicial.')
    status=data.get('status','Em aberto')
    if status not in STATUSES: raise ValueError('Situação inválida.')
    if MODULES[module].get('status') is False: status='Concluído'  # no open/closed life cycle
    return module,clean,status

def merge_return(old,data):
    """Return fields any user may fill once on an open record; filled values stay admin-only."""
    fields=MODULES[old['module']].get('return',[])
    if not fields:raise ValueError('Este tipo de registro não tem retorno.')
    if old['status']!='Em aberto':raise ValueError('O retorno só pode ser registrado em registros em aberto.')
    given=data.get('payload')
    if not isinstance(given,dict) or set(given)-set(fields):raise ValueError('Informe apenas os campos de retorno.')
    current=json.loads(old['payload'])
    if any(current.get(k) and str(v).strip() for k,v in given.items()):
        raise ValueError('Campo de retorno já preenchido. Peça a correção ao administrador.')
    merged={**current,**{k:v for k,v in given.items() if not current.get(k)}}
    _,clean,_=validate_record({'module':old['module'],'payload':merged})
    missing=[f[1] for f in MODULES[old['module']]['fields'] if f[0] in fields and not clean.get(f[0])]
    if missing:raise ValueError('Preencha '+', '.join(missing)+'.')
    return clean

def blocked_doors(c,mapa):
    row=c.execute('SELECT value FROM settings WHERE key=?',(DOOR_MAPS[mapa]['setting'],)).fetchone()
    return set(json.loads(row[0])) if row else set()

def door_holder(c,mapa,number,exclude=None):
    """Id of the active record linked to this door (open and without key return), if any."""
    door=DOOR_MAPS[mapa]
    sql="SELECT id FROM records WHERE module='chaves' AND status='Em aberto' AND json_extract(payload,?)=? AND COALESCE(json_extract(payload,'$.devolucao'),'')='' AND id IS NOT ?"
    params=['$.'+door['field'],str(number),exclude]
    if door['vestiario']:
        sql+=" AND json_extract(payload,'$.vestiario')=?";params.append(door['vestiario'])
    row=c.execute(sql,params).fetchone()
    return row[0] if row else None

def door_links(payload):
    """(map, door number) pairs held by a validated "chaves" payload."""
    links=[('escaninhos',int(payload['escaninho']))] if payload.get('escaninho') else []
    if payload.get('armario'):links.append((payload['vestiario'].lower(),int(payload['armario'])))
    return links

def check_doors(c,module,payload,status,exclude=None):
    """Call inside BEGIN IMMEDIATE so two computers cannot take the same door at once."""
    if module!='chaves' or status!='Em aberto' or payload.get('devolucao'):return
    for mapa,number in door_links(payload):
        name=DOOR_MAPS[mapa]['name']
        if number in blocked_doors(c,mapa):raise Conflict(f'O {name} {number} está bloqueado.')
        if door_holder(c,mapa,number,exclude):raise Conflict(f'O {name} {number} já está ocupado. Libere-o antes de vincular outra pessoa.')

def record_dict(row):
    d=dict(row);d['payload']=json.loads(d['payload']);return d

class Handler(BaseHTTPRequestHandler):
    server_version='GateFlow'
    def log_message(self,fmt,*args):
        # Do not log payloads, names, documents or credentials.
        pass
    def send(self,status,obj=None,headers=None,raw=None,ctype='application/json; charset=utf-8'):
        body=raw if raw is not None else json.dumps(obj,ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type',ctype)
        self.send_header('Content-Length',str(len(body)))
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('X-Frame-Options','DENY')
        self.send_header('Referrer-Policy','same-origin')
        self.send_header('Content-Security-Policy',"default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        for k,v in (headers or {}).items(): self.send_header(k,v)
        self.end_headers();self.wfile.write(body)
    def xlsx_body(self):
        length=int(self.headers.get('Content-Length','0'))
        if not 0<length<=bases.MAX_UPLOAD: raise ValueError(f'Envie uma planilha .xlsx de até {bases.MAX_UPLOAD//1024//1024} MB.')
        if self.headers.get('Content-Type','').split(';')[0] not in ('application/vnd.openxmlformats-officedocument.spreadsheetml.sheet','application/octet-stream'):
            raise ValueError('Envie um arquivo .xlsx.')
        return self.rfile.read(length)
    def body(self):
        length=int(self.headers.get('Content-Length','0'))
        if not 0<length<=2_000_000: raise ValueError('Envie um JSON de até 2 MB.')
        if self.headers.get('Content-Type','').split(';')[0]!='application/json': raise ValueError('Use Content-Type application/json.')
        try: data=json.loads(self.rfile.read(length))
        except (ValueError,UnicodeDecodeError): raise ValueError('JSON inválido.')
        if not isinstance(data,dict): raise ValueError('O corpo deve ser um objeto JSON.')
        return data
    def current(self,c):
        cookie=SimpleCookie()
        try: cookie.load(self.headers.get('Cookie',''))
        except Exception: return None
        token=cookie.get('gateflow_session')
        if not token:return None
        user=c.execute('SELECT u.id,u.name,u.username,u.role,u.last_seen,u.modules,s.csrf,s.token FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token=? AND s.expires>? AND u.active=1',
                       (hashlib.sha256(token.value.encode()).hexdigest(),time.time())).fetchone()
        if user and (user['last_seen'] or 0)<time.time()-SEEN_THROTTLE:
            # Committed at once so routes that open BEGIN IMMEDIATE are not inside a transaction.
            c.execute('UPDATE users SET last_seen=? WHERE id=?',(time.time(),user['id']));c.commit()
        return user
    def allowed_origin(self):
        origin=self.headers.get('Origin')
        if origin and origin not in ('http://'+self.headers.get('Host',''),'https://'+self.headers.get('Host','')): return False
        return self.headers.get('Sec-Fetch-Site') not in ('cross-site',)
    def do_GET(self): self.dispatch('GET')
    def do_POST(self): self.dispatch('POST')
    def do_PATCH(self): self.dispatch('PATCH')
    def do_DELETE(self): self.dispatch('DELETE')
    def dispatch(self,method):
        try: self.route(method)
        except Conflict as e:self.send(409,{'error':str(e)})
        except ValueError as e:self.send(400,{'error':str(e)})
        except sqlite3.IntegrityError:self.send(409,{'error':'Login já utilizado ou conflito de dados.'})
        except Exception:
            self.send(500,{'error':'Não foi possível concluir. Consulte o administrador.'})
    def route(self,method):
        path=urlsplit(self.path).path.rstrip('/') or '/'
        if not path.startswith('/api/'):
            if method!='GET':return self.send(405,{'error':'Método inválido.'})
            files={'/':('index.html','text/html; charset=utf-8'),'/app.js':('app.js','text/javascript; charset=utf-8'),'/style.css':('style.css','text/css; charset=utf-8'),'/logo.png':('logo.png','image/png'),'/mapas.js':('mapas.js','text/javascript; charset=utf-8'),'/bases.js':('bases.js','text/javascript; charset=utf-8'),'/layout_cd.svg':('layout_cd.svg','image/svg+xml; charset=utf-8'),'/escaninhos.svg':('escaninhos.svg','image/svg+xml; charset=utf-8'),'/vestiario.svg':('vestiario.svg','image/svg+xml; charset=utf-8')}
            if path not in files:return self.send(404,{'error':'Não encontrado.'})
            f,ct=files[path];return self.send(200,raw=(ROOT/'static'/f).read_bytes(),ctype=ct)
        if method!='GET' and not self.allowed_origin():return self.send(403,{'error':'Origem não autorizada.'})
        with closing(connect()) as c, c:
            user=self.current(c)
            if path=='/api/session' and method=='GET':
                return self.send(200,{'setup':not bool(c.execute('SELECT 1 FROM users LIMIT 1').fetchone()),'user':{k:user[k] for k in ('id','name','username','role','csrf')} if user else None})
            if path=='/api/setup' and method=='POST':
                if self.client_address[0] not in ('127.0.0.1','::1'):return self.send(403,{'error':'Crie o primeiro administrador no computador servidor.'})
                values=valid_user({**self.body(),'role':'admin'})
                c.execute('BEGIN IMMEDIATE')
                if c.execute('SELECT 1 FROM users LIMIT 1').fetchone():return self.send(409,{'error':'Administrador já configurado.'})
                c.execute('INSERT INTO users(name,username,password,role,created_at) VALUES(?,?,?,?,?)',(*values,now()))
                audit(c,None,'Configuração inicial','administrador');c.commit()
                return self.send(201,{'ok':True})
            if path=='/api/login' and method=='POST':
                data=self.body();username=data.get('username');password=data.get('password')
                if not isinstance(username,str) or not isinstance(password,str) or len(password)>200:raise ValueError('Credenciais inválidas.')
                address=self.client_address[0]
                with LOCK:
                    attempts=[t for t in RATE.get(address,[]) if t>time.time()-300]
                    if len(attempts)>=12:return self.send(429,{'error':'Muitas tentativas. Aguarde cinco minutos.'})
                    attempts.append(time.time());RATE[address]=attempts
                u=c.execute('SELECT * FROM users WHERE username=?',(username,)).fetchone()
                # Equal-cost verification even for unknown accounts.
                stored=u['password'] if u else '0'*32+':'+('0'*64)
                if not password_ok(password,stored) or not u:return self.send(401,{'error':'Usuário ou senha inválidos.'})
                # Revealed only after a correct password, so it does not expose which logins exist.
                if not u['active']:return self.send(403,{'error':'Usuário bloqueado. Procure o administrador.'})
                with LOCK:RATE.pop(address,None)
                token=secrets.token_urlsafe(32);csrf=secrets.token_urlsafe(32)
                c.execute('DELETE FROM sessions WHERE expires<?',(time.time(),))
                c.execute('INSERT INTO sessions VALUES(?,?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),u['id'],csrf,time.time()+28800))
                c.execute('UPDATE users SET last_seen=? WHERE id=?',(time.time(),u['id']))
                audit(c,u,'Login','sessão');c.commit()
                secure='; Secure' if os.environ.get('GATEFLOW_SECURE_COOKIE')=='1' else ''
                return self.send(200,{'ok':True},{'Set-Cookie':f'gateflow_session={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=28800{secure}'})
            if not user:return self.send(401,{'error':'Faça login para continuar.'})
            if method!='GET' and not hmac.compare_digest(self.headers.get('X-CSRF-Token',''),user['csrf']):return self.send(403,{'error':'Sessão inválida. Recarregue a página.'})
            admin=user['role']=='admin';allowed=allowed_modules(user)
            if path=='/api/logout' and method=='POST':
                c.execute('DELETE FROM sessions WHERE token=?',(user['token'],));c.commit()
                return self.send(200,{'ok':True},{'Set-Cookie':'gateflow_session=; Path=/; Max-Age=0; HttpOnly; SameSite=Strict'})
            if path=='/api/bootstrap' and method=='GET':
                return self.send(200,{'schema':[m for m in SCHEMA if m['id'] in allowed],'settings':dict(c.execute('SELECT key,value FROM settings').fetchall()),'statuses':STATUSES,'listas':bases.lists(c)})
            if path=='/api/bases/colaboradores' and method=='GET':
                return self.send(200,bases.find_colaboradores(c,parse_qs(urlsplit(self.path).query).get('q',[''])[0]))
            if path=='/api/bases/terceirizados' and method=='GET':
                query=parse_qs(urlsplit(self.path).query)
                if 'documento' in query:return self.send(200,{'pessoa':bases.find_terceiro_document(c,query['documento'][0])})
                return self.send(200,bases.find_terceiros(c,query.get('q',[''])[0]))
            if path=='/api/records' and method=='GET':
                rows=c.execute('SELECT r.*,u.name creator,ru.name returner FROM records r JOIN users u ON u.id=r.created_by LEFT JOIN users ru ON ru.id=r.returned_by ORDER BY r.id DESC').fetchall()
                return self.send(200,[record_dict(r) for r in rows if r['module'] in allowed])
            if path=='/api/records' and method=='POST':
                data=self.body();module,payload,status=validate_record(data)
                if module not in allowed:return self.send(403,{'error':'Você não tem acesso a esta aba.'})
                if not admin and data.get('status','Em aberto')!='Em aberto':return self.send(403,{'error':'Operadores só podem cadastrar registros em aberto.'})
                c.execute('BEGIN IMMEDIATE');check_doors(c,module,payload,status)
                stamp=now();cursor=c.execute('INSERT INTO records(module,payload,status,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?)',(module,json.dumps(payload,ensure_ascii=False),status,user['id'],stamp,stamp))
                audit(c,user,'Novo registro',cursor.lastrowid,module);c.commit();return self.send(201,{'id':cursor.lastrowid})
            if path.startswith('/api/records/') and path.endswith('/retorno') and method=='POST':
                rid=int(path.split('/')[-2]);data=self.body();old=c.execute('SELECT * FROM records WHERE id=?',(rid,)).fetchone()
                if not old or old['module'] not in allowed:return self.send(404,{'error':'Registro não encontrado.'})
                payload=merge_return(old,data);stamp=now()
                cursor=c.execute("UPDATE records SET payload=?,status='Concluído',updated_at=?,returned_by=?,returned_at=?,version=version+1 WHERE id=? AND version=? AND status='Em aberto'",(json.dumps(payload,ensure_ascii=False),stamp,user['id'],stamp,rid,data.get('version')))
                if cursor.rowcount!=1:return self.send(409,{'error':'Este registro mudou. Atualize a tela antes de registrar o retorno.'})
                audit(c,user,'Retorno registrado',rid,old['module']);c.commit();return self.send(200,{'ok':True})
            if not admin:return self.send(403,{'error':'Apenas o administrador pode realizar esta ação.'})
            if path=='/api/bases' and method=='GET':return self.send(200,bases.summary(c))
            if path.startswith('/api/bases/') and method=='POST':
                base=path.split('/')[-1]
                if base not in bases.BASES:return self.send(404,{'error':'Base não encontrada.'})
                data=self.xlsx_body();c.execute('BEGIN IMMEDIATE')
                counts=bases.import_base(c,base,data,now())
                audit(c,user,'Importação de base',base,f"{counts['novos']} novos, {counts['atualizados']} atualizados, {counts['ignorados']} ignorados");c.commit()
                return self.send(200,counts)
            if path.startswith('/api/records/') and method in ('PATCH','DELETE'):
                rid=int(path.split('/')[-1]);old=c.execute('SELECT * FROM records WHERE id=?',(rid,)).fetchone()
                if not old:return self.send(404,{'error':'Registro não encontrado.'})
                if method=='DELETE':c.execute('DELETE FROM records WHERE id=?',(rid,))
                else:
                    data=self.body();module,payload,status=validate_record(data)
                    if module!=old['module']:raise ValueError('Não é permitido trocar o módulo de um registro.')
                    c.execute('BEGIN IMMEDIATE');check_doors(c,module,payload,status,rid)
                    cursor=c.execute('UPDATE records SET payload=?,status=?,updated_at=?,version=version+1 WHERE id=? AND version=?',(json.dumps(payload,ensure_ascii=False),status,now(),rid,data.get('version')))
                    if cursor.rowcount!=1:return self.send(409,{'error':'Este registro mudou. Atualize a tela antes de editar.'})
                audit(c,user,'Exclusão' if method=='DELETE' else 'Edição',rid,old['module']);c.commit();return self.send(200,{'ok':True})
            if path=='/api/users' and method=='GET':
                rows=c.execute('SELECT id,name,username,role,active,created_at,last_seen,modules,(active=1 AND last_seen>? AND EXISTS(SELECT 1 FROM sessions s WHERE s.user_id=users.id AND s.expires>?)) online FROM users ORDER BY id',(time.time()-ONLINE_WINDOW,time.time()))
                return self.send(200,[{**dict(r),'online':bool(r['online']),'modules':json.loads(r['modules']) if r['modules'] else None} for r in rows])
            if path=='/api/users' and method=='POST':
                data=self.body();values=valid_user(data);modules=valid_modules(data.get('modules'),values[3])
                cursor=c.execute('INSERT INTO users(name,username,password,role,created_at,modules) VALUES(?,?,?,?,?,?)',(*values,now(),modules));audit(c,user,'Novo usuário',cursor.lastrowid);c.commit();return self.send(201,{'id':cursor.lastrowid})
            if path.startswith('/api/users/') and method=='PATCH':
                uid=int(path.split('/')[-1]);data=self.body()
                c.execute('BEGIN IMMEDIATE')
                old=c.execute('SELECT * FROM users WHERE id=?',(uid,)).fetchone()
                if not old:return self.send(404,{'error':'Usuário não encontrado.'})
                name=data.get('name',old['name']);role=data.get('role',old['role']);active=data.get('active',old['active'])
                if not isinstance(name,str) or not 2<=len(name.strip())<=100 or role not in ('admin','operador') or type(active) not in (bool,int) or active not in (0,1):raise ValueError('Dados de usuário inválidos.')
                if uid==user['id'] and (role!='admin' or not active):raise ValueError('Você não pode remover seu próprio acesso de administrador.')
                if old['role']=='admin' and old['active'] and (role!='admin' or not active):
                    if c.execute("SELECT COUNT(*) FROM users WHERE role='admin' AND active=1").fetchone()[0]<=1:raise ValueError('Mantenha pelo menos um administrador ativo.')
                hashed=old['password']
                if data.get('password'):
                    _,_,hashed,_=valid_user({'name':name,'username':old['username'],'password':data['password'],'role':role})
                modules=valid_modules(data['modules'],role) if 'modules' in data else (None if role=='admin' else old['modules'])
                c.execute('UPDATE users SET name=?,role=?,active=?,password=?,modules=? WHERE id=?',(name.strip(),role,active,hashed,modules,uid))
                c.execute('DELETE FROM sessions WHERE user_id=?',(uid,));audit(c,user,'Atualização de usuário',uid);c.commit();return self.send(200,{'ok':True})
            if path=='/api/audit' and method=='GET':return self.send(200,[dict(r) for r in c.execute('SELECT * FROM audit ORDER BY id DESC LIMIT 1000')])
            if path=='/api/export' and method=='GET':
                audit(c,user,'Exportação JSON','registros');c.commit()
                rows=c.execute('SELECT * FROM records ORDER BY id').fetchall()
                return self.send(200,{'format':'gateflow.records.v1','exported_at':now(),'records':[record_dict(r) for r in rows]}, {'Content-Disposition':'attachment; filename="gateflow-registros.json"'})
            if path=='/api/import' and method=='POST':
                data=self.body();items=data.get('records')
                if data.get('format')!='gateflow.records.v1' or not isinstance(items,list) or len(items)>5000:raise ValueError('Use o formato gateflow.records.v1, com até 5.000 registros por arquivo.')
                validated=[]
                for i,item in enumerate(items):
                    try:
                        if not isinstance(item,dict):raise ValueError('Registro deve ser um objeto.')
                        validated.append(validate_record(item))
                    except ValueError as e:raise ValueError(f'Linha {i+1}: {e}')
                c.execute('BEGIN IMMEDIATE')
                for i,(module,payload,status) in enumerate(validated):
                    try:check_doors(c,module,payload,status)
                    except Conflict as e:raise Conflict(f'Linha {i+1}: {e}')
                    stamp=now();c.execute('INSERT INTO records(module,payload,status,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?)',(module,json.dumps(payload,ensure_ascii=False),status,user['id'],stamp,stamp))
                audit(c,user,'Importação JSON','registros',str(len(items)));c.commit();return self.send(201,{'imported':len(items)})
            if path=='/api/backup' and method=='GET':
                import tempfile
                audit(c,user,'Backup SQLite','banco');c.commit()
                with tempfile.TemporaryDirectory() as folder:
                    target=Path(folder)/'backup.db'
                    with closing(sqlite3.connect(target)) as dest:c.backup(dest)
                    return self.send(200,raw=target.read_bytes(),ctype='application/octet-stream',headers={'Content-Disposition':'attachment; filename="gateflow-backup.db"'})
            if path=='/api/mapas/bloqueio' and method=='POST':
                data=self.body();mapa=data.get('mapa');number=data.get('numero');blocked=data.get('bloqueado')
                if not isinstance(mapa,str) or mapa not in DOOR_MAPS:raise ValueError('Mapa inválido.')
                door=DOOR_MAPS[mapa]
                if type(number) is not int or not 1<=number<=door['total'] or type(blocked) is not bool:raise ValueError('Número ou situação inválida.')
                c.execute('BEGIN IMMEDIATE')
                if blocked and door_holder(c,mapa,number):raise Conflict(f"O {door['name']} {number} está ocupado. Libere-o antes de bloquear.")
                current=blocked_doors(c,mapa);updated=sorted(current|{number} if blocked else current-{number})
                c.execute("INSERT INTO settings VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(door['setting'],json.dumps(updated)))
                audit(c,user,'Bloqueio' if blocked else 'Desbloqueio',f"{door['name']} {number}");c.commit();return self.send(200,{'ok':True})
            if path=='/api/settings' and method=='PATCH':
                value=self.body().get('unidade','')
                if not isinstance(value,str) or not 2<=len(value.strip())<=80:raise ValueError('Nome da unidade inválido.')
                c.execute("UPDATE settings SET value=? WHERE key='unidade'",(value.strip(),));audit(c,user,'Configuração','unidade');c.commit();return self.send(200,{'ok':True})
            return self.send(404,{'error':'Recurso não encontrado.'})

def reset_password(username,ask):
    """Server-side recovery: only someone with access to this computer can run it."""
    with closing(connect()) as c, c:
        u=c.execute('SELECT * FROM users WHERE username=?',(username,)).fetchone()
        if not u:raise ValueError(f'Usuário "{username}" não encontrado.')
        password=ask('Nova senha (mínimo 10 caracteres): ')
        if password!=ask('Repita a nova senha: '):raise ValueError('As senhas não conferem.')
        _,_,hashed,_=valid_user({'name':u['name'],'username':u['username'],'password':password,'role':u['role']})
        c.execute('UPDATE users SET password=?,active=1 WHERE id=?',(hashed,u['id']))
        c.execute('DELETE FROM sessions WHERE user_id=?',(u['id'],))
        audit(c,None,'Redefinição de senha no servidor',u['id'])
    return u['username']

def is_running_here(url):
    """True when the program answering on url is this system (identified by its Server header)."""
    import urllib.request
    try:
        with urllib.request.urlopen(url+'/api/session',timeout=3) as r:return r.headers.get('Server','').startswith(Handler.server_version)
    except OSError:return False

class Server(ThreadingHTTPServer):
    # On Windows SO_REUSEADDR lets a second copy bind the same port silently.
    allow_reuse_address=False

def main(open_browser=False):
    global DB
    parser=argparse.ArgumentParser(description='Prevenção de Perdas — Portaria logística')
    parser.add_argument('--host',default='127.0.0.1');parser.add_argument('--port',type=int,help=f'Porta local (padrão: "porta" do config.json ou {DEFAULT_PORT}).')
    parser.add_argument('--db',type=Path,help='Arquivo do banco; sem ele, usa config.json (ou dados/ ao rodar pelo código).')
    parser.add_argument('--redefinir-senha',metavar='LOGIN',help='Define uma nova senha para o usuário e encerra.')
    parser.add_argument('--sem-navegador',action='store_true',help='Não abre o navegador ao iniciar.')
    args=parser.parse_args();open_browser=open_browser and not args.sem_navegador
    DB=(args.db or (configured_db() if getattr(sys,'frozen',False) or CONFIG.exists() else DB)).resolve()
    print(f'Banco de dados: {DB}',flush=True);initialize()
    if args.redefinir_senha:
        import getpass
        try:print(f'Senha de {reset_password(args.redefinir_senha,getpass.getpass)} redefinida. Faça login com a nova senha.')
        except ValueError as e:raise SystemExit(str(e))
        return
    port=args.port or (json.loads(CONFIG.read_text(encoding='utf-8')).get('porta') if CONFIG.exists() else None) or DEFAULT_PORT
    url=f'http://127.0.0.1:{port}'
    try:server=Server((args.host,port),Handler)
    except OSError:
        if not is_running_here(url):
            raise SystemExit(f'A porta {port} está em uso por outro programa. Defina outra no config.json, por exemplo "porta": {port+1}.')
        # Already running on this computer: just bring the page up again.
        print(f'O sistema já está aberto neste computador ({url}).')
        if open_browser:
            import webbrowser;webbrowser.open(url)
        return
    threading.Thread(target=backup_loop,daemon=True).start()
    if open_browser:
        import webbrowser;webbrowser.open(url)
    print(f'Sistema no ar: {url} — mantenha esta janela aberta. Ctrl+C para encerrar.',flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()
if __name__=='__main__':main()
