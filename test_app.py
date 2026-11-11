import http.cookiejar
import http.server
import io
import zipfile
from xml.sax.saxutils import escape
import importlib.util
import json
import re
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
import app

def make_book(sheets,shared=True):
    """Minimal .xlsx from {tab name: rows}: strings in sharedStrings (or inline), ints as numeric cells."""
    strings=[];parts=[]
    for rows in sheets.values():
        cells=[]
        for r,row in enumerate(rows,1):
            xml=[]
            for col,value in enumerate(row):
                ref=chr(65+col)+str(r)
                if isinstance(value,int):xml.append(f'<c r="{ref}"><v>{value}</v></c>')
                elif shared:strings.append(value);xml.append(f'<c r="{ref}" t="s"><v>{len(strings)-1}</v></c>')
                else:xml.append(f'<c r="{ref}" t="inlineStr"><is><t>{escape(value)}</t></is></c>')
            cells.append(f'<row r="{r}">{"".join(xml)}</row>')
        parts.append("".join(cells))
    ns='xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
    tabs=''.join(f'<sheet name="{escape(name)}" sheetId="{i}" r:id="rId{i}"/>' for i,name in enumerate(sheets,1))
    rels=''.join(f'<Relationship Id="rId{i}" Type="worksheet" Target="worksheets/sheet{i}.xml"/>' for i in range(1,len(sheets)+1))
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w') as z:
        z.writestr('[Content_Types].xml','<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>')
        z.writestr('xl/workbook.xml',f'<workbook {ns} xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>{tabs}</sheets></workbook>')
        z.writestr('xl/_rels/workbook.xml.rels',f'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">{rels}</Relationships>')
        for i,part in enumerate(parts,1):z.writestr(f'xl/worksheets/sheet{i}.xml',f'<worksheet {ns}><sheetData>{part}</sheetData></worksheet>')
        if shared:z.writestr('xl/sharedStrings.xml',f'<sst {ns}>'+''.join(f'<si><t>{escape(v)}</t></si>' for v in strings)+'</sst>')
    return out.getvalue()

class IntegrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();app.DB=Path(cls.tmp.name)/'test.db';app.initialize()
        cls.server=ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
        cls.base='http://127.0.0.1:'+str(cls.server.server_port)
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.thread.join();cls.tmp.cleanup()
    def client(self):
        return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    def req(self,client,path,method='GET',data=None,csrf='',origin=None):
        headers={'Content-Type':'application/json','X-CSRF-Token':csrf}
        if origin:headers['Origin']=origin
        r=urllib.request.Request(self.base+'/api/'+path,method=method,headers=headers,data=json.dumps(data).encode() if data is not None else None)
        try:response=client.open(r)
        except urllib.error.HTTPError as e:response=e
        raw=response.read()
        return response.code,json.loads(raw) if 'application/json' in response.headers.get('Content-Type','') else raw
    def test_complete_workflow_and_permissions(self):
        admin=self.client();op=self.client();anonymous=self.client()
        self.assertEqual(self.req(anonymous,'records')[0],401)
        self.assertEqual(self.req(admin,'setup','POST',{'name':'Gestor CD','username':'gestor','password':'senha-forte-123'})[0],201)
        self.assertEqual(self.req(admin,'setup','POST',{'name':'Outro gestor','username':'gestor2','password':'senha-forte-123'})[0],409)
        self.assertEqual(self.req(admin,'login','POST',{'username':'gestor','password':'errada'})[0],401)
        self.assertEqual(self.req(admin,'login','POST',{'username':'gestor','password':'senha-forte-123'})[0],200)
        session=self.req(admin,'session')[1]['user'];token=session['csrf']
        self.assertEqual(self.req(admin,'users','POST',{'name':'Operador Um','username':'operador','password':'senha-operador-123'})[0],403)
        code,user=self.req(admin,'users','POST',{'name':'Operador Um','username':'operador','password':'senha-operador-123'},token);self.assertEqual(code,201);uid=user['id']
        self.assertEqual(self.req(op,'login','POST',{'username':'operador','password':'senha-operador-123'})[0],200)
        ot=self.req(op,'session')[1]['user']['csrf']
        record={'module':'rotas','payload':{'rota':'Rota Teste','tipo':'Regular','placa':'ABC1D23','condutor':'Condutor Teste','lacre':'LACRE-001','saida':'2026-10-28T10:00','liberado_por':'L'}}
        bad={**record,'payload':{**record['payload'],'tipo':'invalida'}}
        self.assertEqual(self.req(op,'records','POST',bad,ot)[0],400)
        self.assertEqual(self.req(op,'records','POST',{**record,'status':'Concluído'},ot)[0],403)
        self.assertEqual(self.req(op,'records','POST',record,ot,'https://outro.invalid')[0],403)
        code,r=self.req(op,'records','POST',record,ot);self.assertEqual(code,201);rid=r['id']
        for endpoint,method,data in [('users','GET',None),('audit','GET',None),('export','GET',None),('backup','GET',None),('settings','PATCH',{'unidade':'Outra'}),('import','POST',{'format':'gateflow.records.v1','records':[]}),('records/'+str(rid),'DELETE',None),('records/'+str(rid),'PATCH',record),('users','POST',{'name':'Tentativa'})]:
            self.assertEqual(self.req(op,endpoint,method,data,ot)[0],403,(endpoint,method))
        self.assertEqual(len(self.req(op,'records')[1]),1)
        self.assertEqual(self.req(admin,'records','POST',record,token)[0],201)
        self.assertEqual(len(self.req(op,'records')[1]),2)  # operators see every record
        edit={**record,'status':'Concluído','version':1}
        self.assertEqual(self.req(admin,'records/'+str(rid),'PATCH',edit,token)[0],200)
        self.assertEqual(self.req(admin,'records/'+str(rid),'PATCH',edit,token)[0],409)
        before=len(self.req(admin,'records')[1])
        self.assertEqual(self.req(admin,'import','POST',{'format':'gateflow.records.v1','records':[record,bad]},token)[0],400)
        self.assertEqual(len(self.req(admin,'records')[1]),before)
        self.assertEqual(self.req(admin,'import','POST',{'format':'gateflow.records.v1','records':[record]},token)[0],201)
        self.assertEqual(len(self.req(admin,'export')[1]['records']),before+1)
        code,backup=self.req(admin,'backup');self.assertEqual(code,200);self.assertTrue(backup.startswith(b'SQLite format 3'))
        with closing(app.connect()) as c:
            stored=c.execute('SELECT password FROM users WHERE id=?',(uid,)).fetchone()[0]
            self.assertNotIn('senha-operador-123',stored)
            self.assertGreater(c.execute('SELECT COUNT(*) FROM audit').fetchone()[0],5)
        self.assertEqual(self.req(admin,'users/'+str(session['id']),'PATCH',{'active':0},token)[0],400)
        self.assertEqual(self.req(admin,'users/'+str(uid),'PATCH',{'active':0},token)[0],200)
        self.assertEqual(self.req(op,'records')[0],401)
        code,blocked=self.req(op,'login','POST',{'username':'operador','password':'senha-operador-123'})
        self.assertEqual((code,blocked['error']),(403,'Usuário bloqueado. Procure o administrador.'))
        self.assertEqual(self.req(op,'login','POST',{'username':'operador','password':'senha-errada-123'})[0],401)
        self.assertEqual(self.req(admin,'records/'+str(rid),'DELETE',None,token)[0],200)
        self.assertEqual(self.req(admin,'logout','POST',{},token)[0],200)
        self.assertEqual(self.req(admin,'records')[0],401)
    def test_field_validation(self):
        data={'module':'veiculos','payload':{'placa':'ABC1D23','motorista':'Condutor Teste','itinerario':'Local','saida':'2026-10-28T12:00','km_inicial':100,'km_final':90}}
        with self.assertRaises(ValueError):app.validate_record(data)
        data['payload']['km_final']=110
        self.assertEqual(app.validate_record(data)[1]['km_final'],'110')
        data['payload']['retorno']='2026-10-28T11:00'
        with self.assertRaises(ValueError):app.validate_record(data)
        data['payload'].pop('retorno');data['payload']['placa']='sem placa'
        with self.assertRaises(ValueError):app.validate_record(data)

    def test_password_reset(self):
        with closing(app.connect()) as c, c:
            c.execute('INSERT INTO users(name,username,password,role,created_at) VALUES(?,?,?,?,?)',(*app.valid_user({'name':'Esquecido','username':'esquecido','password':'senha-antiga-123','role':'admin'}),app.now()))
        with self.assertRaises(ValueError):app.reset_password('nao-existe',lambda _:'senha-nova-1234')
        with self.assertRaises(ValueError):app.reset_password('esquecido',lambda _:'curta')
        answers=iter(['senha-nova-1234','outra-senha-123'])
        with self.assertRaises(ValueError):app.reset_password('esquecido',lambda _:next(answers))
        app.reset_password('esquecido',lambda _:'senha-nova-1234')
        client=self.client()
        self.assertEqual(self.req(client,'login','POST',{'username':'esquecido','password':'senha-antiga-123'})[0],401)
        self.assertEqual(self.req(client,'login','POST',{'username':'esquecido','password':'senha-nova-1234'})[0],200)

    def test_operator_registers_return(self):
        with closing(app.connect()) as c, c:
            for login in ('retorno-admin','retorno-op'):
                c.execute('INSERT INTO users(name,username,password,role,created_at) VALUES(?,?,?,?,?)',(*app.valid_user({'name':'Usuario '+login,'username':login,'password':'senha-retorno-123','role':'admin' if login=='retorno-admin' else 'operador'}),app.now()))
        admin,op=self.client(),self.client()
        for client,login in ((admin,'retorno-admin'),(op,'retorno-op')):
            self.assertEqual(self.req(client,'login','POST',{'username':login,'password':'senha-retorno-123'})[0],200)
        at,ot=self.req(admin,'session')[1]['user']['csrf'],self.req(op,'session')[1]['user']['csrf']
        rid=self.req(admin,'records','POST',{'module':'rotas','payload':{'rota':'R1','tipo':'Extra','placa':'ABC1D23','condutor':'C','lacre':'L1','saida':'2026-10-28T10:00','liberado_por':'L'}},at)[1]['id']
        url=f'records/{rid}/retorno'
        self.assertEqual(self.req(op,url,'POST',{'payload':{'retorno':'2026-10-28T09:00','lacre_retorno':'L2'},'version':1},ot)[0],400)
        self.assertEqual(self.req(op,url,'POST',{'payload':{'retorno':'2026-10-28T12:00'},'version':1},ot)[0],400)
        self.assertEqual(self.req(op,url,'POST',{'payload':{'retorno':'2026-10-28T12:00','lacre_retorno':'L2','placa':'XYZ1234'},'version':1},ot)[0],400)
        self.assertEqual(self.req(op,url,'POST',{'payload':{'retorno':'2026-10-28T12:00','lacre_retorno':'L2'},'version':9},ot)[0],409)
        self.assertEqual(self.req(op,url,'POST',{'payload':{'retorno':'2026-10-28T12:00','lacre_retorno':'L2'},'version':1},ot)[0],200)
        saved=next(r for r in self.req(op,'records')[1] if r['id']==rid)
        self.assertEqual((saved['status'],saved['returner'],saved['payload']['lacre_retorno'],saved['payload']['placa']),('Concluído','USUARIO RETORNO-OP','L2','ABC1D23'))
        self.assertEqual(self.req(op,url,'POST',{'payload':{'retorno':'2026-10-28T13:00','lacre_retorno':'L3'},'version':2},ot)[0],400)
        pessoa=self.req(admin,'records','POST',{'module':'pessoas','payload':{'nome':'P','documento':'123','empresa':'E','motivo':'Visita','area':'RH','entrada':'2026-10-28T09:00'}},at)[1]['id']
        self.assertEqual(self.req(op,f'records/{pessoa}/retorno','POST',{'payload':{},'version':1},ot)[0],400)

    def test_escaninho_map_rules(self):
        with closing(app.connect()) as c, c:
            for login in ('esc-admin','esc-op'):
                c.execute('INSERT INTO users(name,username,password,role,created_at) VALUES(?,?,?,?,?)',(*app.valid_user({'name':login,'username':login,'password':'senha-escaninho-1','role':'admin' if login=='esc-admin' else 'operador'}),app.now()))
        admin,op=self.client(),self.client()
        for client,login in ((admin,'esc-admin'),(op,'esc-op')):
            self.assertEqual(self.req(client,'login','POST',{'username':login,'password':'senha-escaninho-1'})[0],200)
        at,ot=self.req(admin,'session')[1]['user']['csrf'],self.req(op,'session')[1]['user']['csrf']
        def link(client,csrf,number,name='Colaborador'):
            return self.req(client,'records','POST',{'module':'chaves','payload':{'nome':name,'setor':'Expedição','escaninho':number,'retirada':'2026-10-29T08:00'}},csrf)
        for bad in ('0','217','abc','12a'):
            self.assertEqual(link(op,ot,bad)[0],400,bad)
        self.assertEqual(self.req(op,'records','POST',{'module':'chaves','payload':{'nome':'Sem vínculo','setor':'S','retirada':'2026-10-29T08:00'}},ot)[0],400)  # armário or escaninho
        code,first=link(op,ot,'007','Ana');self.assertEqual(code,201)
        saved=next(r for r in self.req(op,'records')[1] if r['id']==first['id'])
        self.assertEqual(saved['payload']['escaninho'],'7')  # stored without leading zeros
        code,body=link(op,ot,'7','Bruno');self.assertEqual(code,409);self.assertIn('ocupado',body['error'])
        self.assertEqual(self.req(admin,'mapas/bloqueio','POST',{'mapa':'escaninhos','numero':7,'bloqueado':True,'motivo':'Teste'},at)[0],409)  # occupied
        self.assertEqual(self.req(op,'mapas/bloqueio','POST',{'mapa':'escaninhos','numero':8,'bloqueado':True,'motivo':'Teste'},ot)[0],403)
        for bad in ({'numero':0,'bloqueado':True},{'numero':'8','bloqueado':True},{'numero':8,'bloqueado':'sim'}):
            self.assertEqual(self.req(admin,'mapas/bloqueio','POST',{'mapa':'escaninhos',**bad},at)[0],400,bad)
        self.assertEqual(self.req(admin,'mapas/bloqueio','POST',{'mapa':'vestiario','numero':8,'bloqueado':True},at)[0],400)  # unknown map
        self.assertEqual(self.req(admin,'mapas/bloqueio','POST',{'mapa':'escaninhos','numero':8,'bloqueado':True,'motivo':'Teste'},at)[0],200)
        self.assertEqual(json.loads(self.req(op,'bootstrap')[1]['settings']['escaninhos_bloqueados']),[8])
        code,body=link(op,ot,'8');self.assertEqual(code,409);self.assertIn('bloqueado',body['error'])
        other=link(admin,at,'9','Carla')[1]['id']
        edit={'module':'chaves','payload':{'nome':'Carla','setor':'Expedição','escaninho':'7','retirada':'2026-10-29T08:00'},'version':1}
        self.assertEqual(self.req(admin,f'records/{other}','PATCH',edit,at)[0],409)  # moving onto an occupied one
        self.assertEqual(self.req(admin,f'records/{other}','PATCH',{**edit,'payload':{**edit['payload'],'escaninho':'9','cargo':'Líder'}},at)[0],200)  # same one is fine
        self.assertEqual(self.req(op,f'records/{first["id"]}/retorno','POST',{'payload':{'devolucao':'2026-10-29T18:00'},'version':1},ot)[0],200)  # release
        self.assertEqual(link(op,ot,'7','Bruno')[0],201)  # free again after the release
        self.assertEqual(self.req(admin,'mapas/bloqueio','POST',{'mapa':'escaninhos','numero':8,'bloqueado':False},at)[0],200)
        self.assertEqual(link(op,ot,'8')[0],201)
        dup={'format':'gateflow.records.v1','records':[{'module':'chaves','payload':{'nome':'X','setor':'S','escaninho':'50','retirada':'2026-10-29T08:00'}}]*2}
        self.assertEqual(self.req(admin,'import','POST',dup,at)[0],409)  # duplicates inside one import
        self.assertFalse(any(r['payload'].get('escaninho')=='50' for r in self.req(admin,'records')[1]))
        raw=urllib.request.urlopen(self.base+'/escaninhos.svg').read().decode('utf-8')
        self.assertEqual(raw.count('class="armario"'),216);self.assertIn('id="armario-216"',raw);self.assertNotIn('<style',raw)

    def test_vestiario_locker_maps(self):
        with closing(app.connect()) as c, c:
            for login in ('arm-admin','arm-op'):
                c.execute('INSERT INTO users(name,username,password,role,created_at) VALUES(?,?,?,?,?)',(*app.valid_user({'name':login,'username':login,'password':'senha-armario-1','role':'admin' if login=='arm-admin' else 'operador'}),app.now()))
        admin,op=self.client(),self.client()
        for client,login in ((admin,'arm-admin'),(op,'arm-op')):
            self.assertEqual(self.req(client,'login','POST',{'username':login,'password':'senha-armario-1'})[0],200)
        at,ot=self.req(admin,'session')[1]['user']['csrf'],self.req(op,'session')[1]['user']['csrf']
        def link(vestiario,number,name='Pessoa',escaninho=''):
            payload={'nome':name,'setor':'Expedição','vestiario':vestiario,'armario':number,'retirada':'2026-10-30T08:00'}
            if escaninho:payload['escaninho']=escaninho
            return self.req(op,'records','POST',{'module':'chaves','payload':payload},ot)
        for vestiario,bad in (('Masculino','0'),('Masculino','301'),('Masculino','x1'),('','12'),('Unissex','12')):
            self.assertEqual(link(vestiario,bad)[0],400,(vestiario,bad))
        self.assertEqual(self.req(op,'records','POST',{'module':'chaves','payload':{'nome':'P','setor':'S','vestiario':'Masculino','retirada':'2026-10-30T08:00'}},ot)[0],400)  # vestiário without number
        code,first=link('Masculino','012','Diego');self.assertEqual(code,201)
        saved=next(r for r in self.req(op,'records')[1] if r['id']==first['id'])
        self.assertEqual((saved['payload']['vestiario'],saved['payload']['armario']),('Masculino','12'))
        code,body=link('Masculino','12');self.assertEqual(code,409);self.assertIn('armário masculino 12',body['error'])
        self.assertEqual(link('Masculino','160','Lia')[0],201);self.assertEqual(link('Feminino','160','Elisa')[0],201)  # same number, other locker room
        self.assertEqual(self.req(admin,'mapas/bloqueio','POST',{'mapa':'masculino','numero':12,'bloqueado':True,'motivo':'Teste'},at)[0],409)  # occupied
        self.assertEqual(self.req(admin,'mapas/bloqueio','POST',{'mapa':'masculino','numero':301,'bloqueado':True},at)[0],400)
        self.assertEqual(self.req(admin,'mapas/bloqueio','POST',{'mapa':'feminino','numero':161,'bloqueado':True,'motivo':'Teste'},at)[0],200)
        self.assertEqual(json.loads(self.req(op,'bootstrap')[1]['settings']['armarios_feminino_bloqueados']),[161])
        code,body=link('Feminino','161');self.assertEqual(code,409);self.assertIn('bloqueado',body['error'])
        self.assertEqual(link('Masculino','161','Fábio')[0],201)  # block is per locker room
        code,both=link('Masculino','20','Gustavo','60');self.assertEqual(code,201)  # locker and escaninho in one record
        self.assertEqual(self.req(op,'records','POST',{'module':'chaves','payload':{'nome':'H','setor':'S','escaninho':'60','retirada':'2026-10-30T08:00'}},ot)[0],409)
        self.assertEqual(link('Masculino','20')[0],409)
        self.assertEqual(self.req(op,f'records/{both["id"]}/retorno','POST',{'payload':{'devolucao':'2026-10-30T18:00'},'version':1},ot)[0],200)
        self.assertEqual(link('Masculino','20','Igor','60')[0],201)  # both freed by one release
        raw=urllib.request.urlopen(self.base+'/vestiario.svg').read().decode('utf-8')  # one drawing for both rooms
        self.assertEqual(raw.count('class="armario"'),300);self.assertIn('id="armario-300"',raw);self.assertNotIn('<style',raw)
        numbers=[int(n) for n in re.findall(r'class="armario" data-numero="(\d+)"',raw)]
        self.assertEqual(numbers,list(range(1,301)))  # every door once, in order
        towers=re.split(r'<g id="torre-\d+"',raw)[1:]
        self.assertEqual([t.count('class="armario"') for t in towers],[12]*25)  # no shorter set: 3 columns and 4 rows in all of them
        self.assertEqual(link('Masculino','300','Joana')[0],201);self.assertEqual(link('Feminino','300','Karla')[0],201)  # the new last door
        self.assertEqual(self.req(admin,'mapas/bloqueio','POST',{'mapa':'feminino','numero':299,'bloqueado':True,'motivo':'Teste'},at)[0],200)
        self.assertEqual(self.req(admin,'mapas/bloqueio','POST',{'mapa':'feminino','numero':299,'bloqueado':False},at)[0],200)
        self.assertEqual(self.req(op,'records','POST',{'module':'chaves','payload':{'nome':'L','setor':'S','escaninho':'217','retirada':'2026-10-30T08:00'}},ot)[0],400)  # escaninhos stay at 216
        self.assertEqual(app.DOOR_MAPS['escaninhos']['last'],216)

    def test_door_block_requires_reason(self):  # named to run after the first-setup test, which needs an empty users table
        with closing(app.connect()) as c, c:
            c.execute('INSERT INTO users(name,username,password,role,created_at) VALUES(?,?,?,?,?)',(*app.valid_user({'name':'Motivo Admin','username':'motivo-admin','password':'senha-motivo-1','role':'admin'}),app.now()))
        admin=self.client()
        self.assertEqual(self.req(admin,'login','POST',{'username':'motivo-admin','password':'senha-motivo-1'})[0],200)
        at=self.req(admin,'session')[1]['user']['csrf']
        block=lambda mapa,n,**extra:self.req(admin,'mapas/bloqueio','POST',{'mapa':mapa,'numero':n,'bloqueado':True,**extra},at)
        reasons=lambda key:json.loads(self.req(admin,'bootstrap')[1]['settings'].get(key,'{}'))
        for bad in ({},{'motivo':'   '},{'motivo':5},{'motivo':'x'*201}):
            code,body=block('escaninhos',30,**bad);self.assertEqual(code,400,bad);self.assertIn('motivo',body['error'].lower())
        self.assertNotIn(30,json.loads(self.req(admin,'bootstrap')[1]['settings'].get('escaninhos_bloqueados','[]')))
        self.assertEqual(block('escaninhos',30,motivo='  fechadura quebrada ')[0],200)
        saved=reasons('escaninhos_bloqueados_motivos')['30']
        self.assertEqual((saved['motivo'],saved['por']),('FECHADURA QUEBRADA','MOTIVO ADMIN'));self.assertTrue(saved['em'])
        self.assertTrue(any(a['action']=='Bloqueio' and 'FECHADURA QUEBRADA' in a['details'] for a in self.req(admin,'audit')[1]))
        self.assertEqual(block('feminino',170,motivo='Porta empenada')[0],200)  # each map keeps its own reasons
        self.assertEqual(reasons('armarios_feminino_bloqueados_motivos')['170']['motivo'],'PORTA EMPENADA')
        self.assertEqual(self.req(admin,'mapas/bloqueio','POST',{'mapa':'escaninhos','numero':30,'bloqueado':False},at)[0],200)  # no reason to unblock
        self.assertNotIn('30',reasons('escaninhos_bloqueados_motivos'))
        self.assertIn('170',reasons('armarios_feminino_bloqueados_motivos'))
        self.assertEqual(self.req(admin,'mapas/bloqueio','POST',{'mapa':'feminino','numero':170,'bloqueado':False},at)[0],200)  # leave the shared database as found

    def test_key_copy_loans(self):  # named to run after the first-setup test, which needs an empty users table
        with closing(app.connect()) as c, c:
            for login,role,modules in (('copia-admin','admin',None),('copia-op','operador',None),('copia-rotas','operador','["rotas"]')):
                c.execute('INSERT INTO users(name,username,password,role,created_at,modules) VALUES(?,?,?,?,?,?)',(*app.valid_user({'name':login.upper(),'username':login,'password':'senha-copia-123','role':role}),app.now(),modules))
        admin,op,rotas=self.client(),self.client(),self.client()
        for client,login in ((admin,'copia-admin'),(op,'copia-op'),(rotas,'copia-rotas')):
            self.assertEqual(self.req(client,'login','POST',{'username':login,'password':'senha-copia-123'})[0],200)
        at,ot,rt=(self.req(x,'session')[1]['user']['csrf'] for x in (admin,op,rotas))
        rid=self.req(op,'records','POST',{'module':'chaves','payload':{'nome':'Joana','setor':'Expedição','escaninho':'150','retirada':'2026-10-30T08:00'}},ot)[1]['id']
        record=lambda:next(r for r in self.req(admin,'records')[1] if r['id']==rid)
        give=lambda client,csrf,target=rid,**data:self.req(client,f'records/{target}/copias','POST',data,csrf)
        for bad in ({},{'motivo':'Roubou a chave'},{'motivo':'Esqueceu a chave','observacao':'x'*301}):
            self.assertEqual(give(op,ot,**bad)[0],400,bad)
        self.assertEqual(give(rotas,rt,motivo='Esqueceu a chave')[0],404)  # no access to the tab
        code,copy=give(op,ot,motivo='Esqueceu a chave',observacao='devolve no fim do turno');self.assertEqual(code,201)
        self.assertEqual(give(op,ot,motivo='Perdeu a chave')[0],409)  # one copy out at a time
        loans=record()['copias'];self.assertEqual(len(loans),1)
        self.assertEqual((loans[0]['motivo'],loans[0]['observacao'],loans[0]['entregue_por'],loans[0]['devolvida_em']),('Esqueceu a chave','DEVOLVE NO FIM DO TURNO','COPIA-OP',None))
        code,body=self.req(op,f'records/{rid}/retorno','POST',{'payload':{'devolucao':'2026-10-30T18:00'},'version':1},ot)
        self.assertEqual(code,409);self.assertIn('cópia',body['error'])  # release waits for the copy
        edit={'module':'chaves','payload':{'nome':'Joana','setor':'Expedição','escaninho':'150','retirada':'2026-10-30T08:00','devolucao':'2026-10-30T18:00'},'version':1}
        self.assertEqual(self.req(admin,f'records/{rid}','PATCH',edit,at)[0],409)  # nor can the admin close it by editing
        self.assertEqual(self.req(rotas,f'copias/{copy["id"]}/devolucao','POST',{},rt)[0],404)
        self.assertEqual(self.req(op,f'copias/{copy["id"]}/devolucao','POST',{},ot)[0],200)
        self.assertEqual(self.req(op,f'copias/{copy["id"]}/devolucao','POST',{},ot)[0],409)  # already returned
        returned=record()['copias'][0];self.assertTrue(returned['devolvida_em']);self.assertEqual(returned['devolvida_por'],'COPIA-OP')
        self.assertEqual(record()['status'],'Em aberto')  # the main record stays open
        self.assertEqual(give(op,ot,motivo='Perdeu a chave')[0],201)  # a new copy after the first came back
        self.assertEqual(len(record()['copias']),2)
        actions=[a['action'] for a in self.req(admin,'audit')[1]]
        self.assertIn('Cópia de chave entregue',actions);self.assertIn('Cópia de chave devolvida',actions)
        other=self.req(admin,'records','POST',{'module':'rotas','payload':{'rota':'R1','tipo':'Regular','placa':'ABC1D23','condutor':'C','lacre':'L1','saida':'2026-10-30T08:00','liberado_por':'L'}},at)[1]['id']
        self.assertEqual(give(admin,at,other,motivo='Esqueceu a chave')[0],400)  # copies only exist for key records
        self.assertEqual(self.req(admin,f'records/{rid}','DELETE',None,at)[0],200)  # deleting the record removes its copies
        with closing(app.connect()) as c:self.assertEqual(c.execute('SELECT COUNT(*) FROM copias_chave WHERE record_id=?',(rid,)).fetchone()[0],0)

    def test_password_reset_by_admin(self):
        with closing(app.connect()) as c, c:
            for login in ('reset-admin','reset-op'):
                c.execute('INSERT INTO users(name,username,password,role,created_at) VALUES(?,?,?,?,?)',(*app.valid_user({'name':login,'username':login,'password':'senha-original-1','role':'admin' if login=='reset-admin' else 'operador'}),app.now()))
            uid=c.execute("SELECT id FROM users WHERE username='reset-op'").fetchone()[0]
        admin,op=self.client(),self.client()
        self.assertEqual(self.req(admin,'login','POST',{'username':'reset-admin','password':'senha-original-1'})[0],200)
        self.assertEqual(self.req(op,'login','POST',{'username':'reset-op','password':'senha-original-1'})[0],200)
        at=self.req(admin,'session')[1]['user']['csrf']
        self.assertEqual(self.req(admin,f'users/{uid}','PATCH',{'password':'curta'},at)[0],400)
        self.assertEqual(self.req(admin,f'users/{uid}','PATCH',{'password':'senha-nova-123'},at)[0],200)  # only the password
        self.assertIsNone(self.req(op,'session')[1]['user'])  # the operator's open session ends
        self.assertEqual(self.req(op,'login','POST',{'username':'reset-op','password':'senha-original-1'})[0],401)
        self.assertEqual(self.req(op,'login','POST',{'username':'reset-op','password':'senha-nova-123'})[0],200)
        user=next(u for u in self.req(admin,'users')[1] if u['id']==uid)
        self.assertEqual((user['role'],user['active'],user['modules']),('operador',1,None))  # nothing else changed

    def test_presence(self):
        with closing(app.connect()) as c, c:
            for login in ('presenca-admin','presenca-op','presenca-nunca'):
                c.execute('INSERT INTO users(name,username,password,role,created_at) VALUES(?,?,?,?,?)',(*app.valid_user({'name':login,'username':login,'password':'senha-presenca-1','role':'admin' if login=='presenca-admin' else 'operador'}),app.now()))
        admin,op=self.client(),self.client()
        for client,login in ((admin,'presenca-admin'),(op,'presenca-op')):
            self.assertEqual(self.req(client,'login','POST',{'username':login,'password':'senha-presenca-1'})[0],200)
        users=lambda:{u['username'].lower():u for u in self.req(admin,'users')[1]}
        listed=users()
        self.assertTrue(listed['presenca-admin']['online']);self.assertTrue(listed['presenca-op']['online'])
        self.assertFalse(listed['presenca-nunca']['online']);self.assertIsNone(listed['presenca-nunca']['last_seen'])
        self.assertEqual(self.req(op,'logout','POST',{},self.req(op,'session')[1]['user']['csrf'])[0],200)
        listed=users()
        self.assertFalse(listed['presenca-op']['online']);self.assertIsNotNone(listed['presenca-op']['last_seen'])

    def test_operator_module_permissions(self):
        with closing(app.connect()) as c, c:
            c.execute('INSERT INTO users(name,username,password,role,created_at) VALUES(?,?,?,?,?)',(*app.valid_user({'name':'Abas Admin','username':'abas-admin','password':'senha-abas-123','role':'admin'}),app.now()))
        admin,op=self.client(),self.client()
        self.assertEqual(self.req(admin,'login','POST',{'username':'abas-admin','password':'senha-abas-123'})[0],200)
        at=self.req(admin,'session')[1]['user']['csrf']
        new={'name':'So Pessoas','username':'so-pessoas','password':'senha-abas-123','role':'operador'}
        self.assertEqual(self.req(admin,'users','POST',{**new,'modules':[]},at)[0],400)
        self.assertEqual(self.req(admin,'users','POST',{**new,'modules':['inexistente']},at)[0],400)
        uid=self.req(admin,'users','POST',{**new,'modules':['pessoas']},at)[1]['id']
        rota=self.req(admin,'records','POST',{'module':'rotas','payload':{'rota':'R','tipo':'Regular','placa':'ABC1D23','condutor':'C','lacre':'L','saida':'2026-10-28T10:00','liberado_por':'L'}},at)[1]['id']
        self.assertEqual(self.req(admin,'records','POST',{'module':'pessoas','payload':{'nome':'P','documento':'123','empresa':'E','motivo':'Visita','area':'RH','entrada':'2026-10-28T09:00'}},at)[0],201)
        self.assertEqual(self.req(op,'login','POST',{'username':'so-pessoas','password':'senha-abas-123'})[0],200)
        ot=self.req(op,'session')[1]['user']['csrf']
        self.assertEqual([m['id'] for m in self.req(op,'bootstrap')[1]['schema']],['pessoas'])
        self.assertEqual({r['module'] for r in self.req(op,'records')[1]},{'pessoas'})
        self.assertEqual(self.req(op,'records','POST',{'module':'rotas','payload':{'rota':'R','tipo':'Regular','placa':'ABC1D23','condutor':'C','lacre':'L','saida':'2026-10-28T10:00','liberado_por':'L'}},ot)[0],403)
        self.assertEqual(self.req(op,f'records/{rota}/retorno','POST',{'payload':{'retorno':'2026-10-28T12:00','lacre_retorno':'L2'},'version':1},ot)[0],404)
        self.assertEqual(self.req(op,'records','POST',{'module':'pessoas','payload':{'nome':'Q','documento':'123','empresa':'E','motivo':'Visita','area':'RH','entrada':'2026-10-28T09:00'}},ot)[0],201)
        listed={u['username'].lower():u for u in self.req(admin,'users')[1]}
        self.assertEqual(listed['so-pessoas']['modules'],['pessoas']);self.assertIsNone(listed['abas-admin']['modules'])
        self.assertEqual(self.req(admin,f'users/{uid}','PATCH',{'modules':None},at)[0],200)
        self.assertEqual(self.req(op,'login','POST',{'username':'so-pessoas','password':'senha-abas-123'})[0],200)
        self.assertIn('rotas',[m['id'] for m in self.req(op,'bootstrap')[1]['schema']])

    def test_people_have_single_document_and_no_status(self):
        data={'module':'pessoas','status':'Em aberto','payload':{'nome':'P','documento':'CNH 123','empresa':'E','motivo':'Entrevista','area':'RH','entrada':'2026-10-28T09:00'}}
        self.assertEqual(app.validate_record(data)[2],'Concluído')
        with self.assertRaises(ValueError):app.validate_record({**data,'payload':{**data['payload'],'cpf':'1'}})
        with self.assertRaises(ValueError):app.validate_record({**data,'payload':{**data['payload'],'documento':''}})
        with closing(app.connect()) as c, c:
            uid=c.execute('SELECT id FROM users LIMIT 1').fetchone()[0]
            rid=c.execute("INSERT INTO records(module,payload,status,created_by,created_at,updated_at) VALUES('pessoas',?,'Concluído',?,?,?)",(json.dumps({'nome':'Antigo','cpf':'','rg':'RG 9','empresa':'E'}),uid,app.now(),app.now())).lastrowid
        app.initialize()
        with closing(app.connect()) as c:
            payload=json.loads(c.execute('SELECT payload FROM records WHERE id=?',(rid,)).fetchone()[0])
        self.assertEqual(payload,{'nome':'Antigo','documento':'RG 9','empresa':'E'})

    def test_devolucao_accepts_zero_volumes_and_requires_prevention_checker(self):
        data={'module':'devolucoes','payload':{'transportador':'T','fornecedor':'F','nota_fiscal':'1','motivo':'M','volumes':0,'situacao':'Integral',
              'conferente':'C','conferente_prevencao':'fulano','recebimento':'2026-11-06T11:12'}}
        clean=app.validate_record(data)[1]
        self.assertEqual(clean['volumes'],'0');self.assertEqual(clean['conferente_prevencao'],'FULANO')
        for bad in (-1,1.5):
            with self.assertRaises(ValueError):app.validate_record({**data,'payload':{**data['payload'],'volumes':bad}})
        with self.assertRaises(ValueError):app.validate_record({**data,'payload':{**data['payload'],'conferente_prevencao':''}})
        material={'module':'materiais','payload':{'nome':'C','material':'Caixa','quantidade':0,'unidade':'Caixa','autorizacao':'G','liberacao':'Escrito','saida':'2026-10-28T10:00'}}
        with self.assertRaises(ValueError):app.validate_record(material)  # material leaving still needs at least one

    def test_person_access_keeps_the_day_they_came_in(self):
        self.assertIn(['entrada','Entrada','datetime-local',True],app.MODULES['pessoas']['fields'])
        data={'module':'pessoas','payload':{'nome':'P','documento':'CNH 1','empresa':'E','motivo':'M','area':'RH','entrada':'2026-11-03T08:15'}}
        self.assertEqual(app.validate_record(data)[1]['entrada'],'2026-11-03T08:15:00')  # a past day is accepted
        with self.assertRaises(ValueError):app.validate_record({**data,'payload':{**data['payload'],'entrada':''}})

    def test_equipment_return_names_who_brought_it_back(self):
        m=app.MODULES['equipamentos']
        self.assertEqual(m['return'],['devolucao','colaborador_retorno','conferente_prevencao'])
        keys=[f[0] for f in m['fields']];self.assertEqual(keys[keys.index('devolucao')+1],'colaborador_retorno')
        _,clean,_=app.validate_record({'module':'equipamentos','payload':{'nome':'ANA','matricula':'1','equipamento':'JET 01','retirada':'2026-11-10T08:00'}})
        old={'module':'equipamentos','status':'Em aberto','payload':json.dumps(clean)}
        with self.assertRaises(ValueError):app.merge_return(old,{'payload':{'devolucao':'2026-11-10T18:00','conferente_prevencao':'P'}})
        done=app.merge_return(old,{'payload':{'devolucao':'2026-11-10T18:00','colaborador_retorno':'bia','conferente_prevencao':'P'}})
        self.assertEqual((done['nome'],done['colaborador_retorno']),('ANA','BIA'))

    def test_equipment_is_picked_from_a_fixed_list(self):
        names=[f'{kind} {n:02d}' for kind in ('EMPILHADEIRA','PATOLADA','JET') for n in (1,2,3)]
        self.assertIn(['equipamento','Equipamento','select',True,names],app.MODULES['equipamentos']['fields'])
        data={'module':'equipamentos','payload':{'nome':'ANA','matricula':'1','equipamento':'JET 02','retirada':'2026-11-10T08:00'}}
        self.assertEqual(app.validate_record(data)[1]['equipamento'],'JET 02')
        with self.assertRaises(ValueError):app.validate_record({**data,'payload':{**data['payload'],'equipamento':'COLETOR'}})
        self.assertEqual(app.MODULES['equipamentos']['returnOptional'],['conferente_prevencao'])
        raw=urllib.request.urlopen(self.base+'/app.js').read().decode('utf-8')
        self.assertIn("m.returnOptional?.includes(f[0])",raw)  # the return form leaves it unstarred

    def test_records_saved_before_the_equipment_list_can_still_be_returned(self):
        legacy={'matricula':'9001','nome':'ANA','equipamento':'EMPILHADEIRA','retirada':'2026-11-06T15:10'}  # saved as free text
        old={'module':'equipamentos','status':'Em aberto','payload':json.dumps(legacy)}
        done=app.merge_return(old,{'payload':{'devolucao':'2026-11-10T21:28','colaborador_retorno':'PAULO'}})
        self.assertEqual(done['equipamento'],'EMPILHADEIRA')
        self.assertEqual(app.validate_record({'module':'equipamentos','payload':legacy},saved=legacy)[1]['equipamento'],'EMPILHADEIRA')  # admin edit keeps it
        with self.assertRaises(ValueError):app.validate_record({'module':'equipamentos','payload':legacy})  # a new record must use the list
        with self.assertRaises(ValueError):app.validate_record({'module':'equipamentos','payload':{**legacy,'equipamento':'COLETOR'}},saved=legacy)  # nor swap to another free value
        raw=urllib.request.urlopen(self.base+'/app.js').read().decode('utf-8')
        self.assertIn("value&&!options.includes(value)",raw)  # the edit form shows the saved value

    def test_route_table_stacks_pairs_to_fit(self):
        m=app.MODULES['rotas']
        self.assertEqual(m['stack'],{'auxiliar':['condutor','Aux.'],'lacre':['saida','Lacre'],'lacre_retorno':['retorno','Lacre']})
        keys=[f[0] for f in m['fields']]
        for field,(host,_) in m['stack'].items():self.assertIn(host,keys);self.assertIn(field,keys)
        raw=urllib.request.urlopen(self.base+'/app.js').read().decode('utf-8')
        self.assertIn("if(m.stack?.[f[0]])return ''",raw);self.assertIn('m.fields.filter(f=>!m.stack?.[f[0]])',raw)

    def test_matricula_comes_before_the_name(self):
        for module in ('materiais','equipamentos','chaves'):
            keys=[f[0] for f in app.MODULES[module]['fields']];self.assertEqual(keys[:2],['matricula','nome'],module)
        raw=urllib.request.urlopen(self.base+'/app.js').read().decode('utf-8')
        self.assertIn("i===mainColumn(m)",raw)  # the name stays highlighted

    def test_route_names_are_suggested_from_the_employee_base(self):
        raw=urllib.request.urlopen(self.base+'/bases.js').read().decode('utf-8')
        self.assertIn("rotas:{rota:'rota',placa:'placa_caminhao'}",raw)  # condutor and auxiliar are no longer fixed lists
        self.assertIn("rotas:['condutor','auxiliar']",raw);self.assertIn("equipamentos:['colaborador_retorno']",raw)

    def test_route_records_who_released_it(self):
        keys=[f[0] for f in app.MODULES['rotas']['fields']]
        self.assertEqual(keys[keys.index('saida')+1],'liberado_por')
        route={'module':'rotas','payload':{'rota':'R1','tipo':'Regular','placa':'ABC1D23','condutor':'C','lacre':'L1','saida':'2026-11-09T10:00','liberado_por':'fulano'}}
        self.assertEqual(app.validate_record(route)[1]['liberado_por'],'FULANO')
        with self.assertRaises(ValueError):app.validate_record({**route,'payload':{**route['payload'],'liberado_por':''}})

    def test_return_asks_who_checked_for_prevention(self):
        for module,payload,ret in [
            ('equipamentos',{'nome':'C','matricula':'1','equipamento':'EMPILHADEIRA 01','retirada':'2026-11-06T10:00'},{'devolucao':'2026-11-06T15:00','colaborador_retorno':'Bia'}),
            ('veiculos',{'placa':'ABC1234','motorista':'M','itinerario':'I','saida':'2026-11-06T10:00','km_inicial':10},{'retorno':'2026-11-06T15:00','km_final':20})]:
            self.assertEqual(app.MODULES[module]['columns']['conferente_prevencao'],'Prevenção')
            _,clean,status=app.validate_record({'module':module,'payload':payload})  # not asked when the record is opened
            self.assertEqual(status,'Em aberto')
            old={'module':module,'status':'Em aberto','payload':json.dumps(clean)}
            if module=='equipamentos':self.assertEqual(app.merge_return(old,{'payload':ret}).get('conferente_prevencao',''),'')  # optional here
            else:
                with self.assertRaises(ValueError):app.merge_return(old,{'payload':ret})
            done=app.merge_return(old,{'payload':{**ret,'conferente_prevencao':'fulano'}})
            self.assertEqual(done['conferente_prevencao'],'FULANO')

    def test_status_only_where_it_matters(self):
        material={'module':'materiais','payload':{'nome':'C','material':'Caixa','quantidade':2,'unidade':'Caixa','autorizacao':'G','liberacao':'Escrito','saida':'2026-10-28T10:00'}}
        self.assertEqual(app.validate_record(material)[2],'Concluído')
        with self.assertRaises(ValueError):app.validate_record({**material,'payload':{**material['payload'],'cargo':'X'}})
        equipamento={'module':'equipamentos','payload':{'nome':'C','matricula':'1','equipamento':'EMPILHADEIRA 01','retirada':'2026-10-28T10:00'}}
        self.assertEqual(app.validate_record(equipamento)[2],'Em aberto')  # still open until "Registrar retorno"
        self.assertFalse(app.MODULES['equipamentos'].get('showStatus',True))

    def test_footer_credits_the_author_and_opens_about(self):
        raw=urllib.request.urlopen(self.base+'/app.js').read().decode('utf-8')
        self.assertIn('Desenvolvido por Rafael Higino',raw);self.assertIn('data-action="about"',raw);self.assertIn("case 'about':aboutModal()",raw)

    def test_equipment_receiver_is_the_logged_in_user(self):
        m=app.MODULES['equipamentos']
        self.assertNotIn('recebedor',[f[0] for f in m['fields']]);self.assertEqual(m['return'],['devolucao','colaborador_retorno','conferente_prevencao']);self.assertEqual(m['returnerLabel'],'Recebido por')
        with closing(app.connect()) as c, c:
            for login in ('entrega-manha','recebe-tarde'):
                c.execute('INSERT INTO users(name,username,password,role,created_at) VALUES(?,?,?,?,?)',(*app.valid_user({'name':login,'username':login,'password':'senha-recebe-123','role':'operador'}),app.now()))
        morning,afternoon=self.client(),self.client()
        for client,login in ((morning,'entrega-manha'),(afternoon,'recebe-tarde')):
            self.assertEqual(self.req(client,'login','POST',{'username':login,'password':'senha-recebe-123'})[0],200)
        mt,tt=self.req(morning,'session')[1]['user']['csrf'],self.req(afternoon,'session')[1]['user']['csrf']
        code,made=self.req(morning,'records','POST',{'module':'equipamentos','payload':{'nome':'Ana','matricula':'1','equipamento':'PATOLADA 01','retirada':'2026-11-05T08:00'}},mt);self.assertEqual(code,201)
        typed=self.req(afternoon,f'records/{made["id"]}/retorno','POST',{'payload':{'devolucao':'2026-11-05T14:00','recebedor':'Outro'},'version':1},tt)
        self.assertEqual(typed[0],400)  # nobody types the receiver anymore
        self.assertEqual(self.req(afternoon,f'records/{made["id"]}/retorno','POST',{'payload':{'devolucao':'2026-11-05T14:00','colaborador_retorno':'Ana','conferente_prevencao':'Fulano'},'version':1},tt)[0],200)
        record=next(r for r in self.req(afternoon,'records')[1] if r['id']==made['id'])
        self.assertEqual((record['creator'],record['returner'],record['status']),('ENTREGA-MANHA','RECEBE-TARDE','Concluído'))
        self.assertEqual(app.validate_record({'module':'equipamentos','payload':{'nome':'A','matricula':'1','equipamento':'JET 01','retirada':'2026-11-05T08:00','recebedor':'Bia'}})[1]['recebedor'],'Bia')  # names typed before the change stay

    def test_patrimonio_left_the_form_but_old_values_survive(self):
        self.assertNotIn('patrimonio',[f[0] for f in app.MODULES['equipamentos']['fields']])
        with closing(app.connect()) as c, c:
            c.execute('INSERT INTO users(name,username,password,role,created_at) VALUES(?,?,?,?,?)',(*app.valid_user({'name':'patrimonio-admin','username':'patrimonio-admin','password':'senha-patrimonio-1','role':'admin'}),app.now()))
        admin=self.client();self.assertEqual(self.req(admin,'login','POST',{'username':'patrimonio-admin','password':'senha-patrimonio-1'})[0],200)
        at=self.req(admin,'session')[1]['user']['csrf']
        new={'module':'equipamentos','payload':{'nome':'Ana','matricula':'1','equipamento':'EMPILHADEIRA 01','retirada':'2026-10-28T10:00'}}
        self.assertEqual(self.req(admin,'records','POST',new,at)[0],201)  # no longer required
        old_payload={**new['payload'],'patrimonio':'P-77'}
        with closing(app.connect()) as c, c:  # records saved while the field still existed
            uid=c.execute("SELECT id FROM users WHERE username='patrimonio-admin'").fetchone()[0]
            edited,returned=[c.execute("INSERT INTO records(module,payload,status,created_by,created_at,updated_at) VALUES('equipamentos',?,'Em aberto',?,?,?)",(json.dumps(old_payload),uid,app.now(),app.now())).lastrowid for _ in range(2)]
        saved=lambda rid:next(r for r in self.req(admin,'records')[1] if r['id']==rid)['payload']
        code,_=self.req(admin,f'records/{edited}','PATCH',{**new,'status':'Em aberto','version':1,'payload':{**new['payload'],'equipamento':'JET 02'}},at);self.assertEqual(code,200)  # the form no longer sends it
        self.assertEqual((saved(edited)['equipamento'],saved(edited)['patrimonio']),('JET 02','P-77'))
        code,_=self.req(admin,f'records/{returned}/retorno','POST',{'payload':{'devolucao':'2026-10-28T12:00','colaborador_retorno':'Ana','conferente_prevencao':'Fulano'},'version':1},at);self.assertEqual(code,200)
        self.assertEqual(saved(returned)['patrimonio'],'P-77')
        self.assertEqual(app.validate_record({'module':'equipamentos','payload':old_payload})[1]['patrimonio'],'P-77')  # old JSON exports still import
        with self.assertRaises(ValueError):app.validate_record({'module':'equipamentos','payload':{**new['payload'],'outro':'x'}})

    def test_network_ready_database(self):
        with closing(app.connect()) as c:
            self.assertEqual(c.execute('PRAGMA journal_mode').fetchone()[0],'delete')  # WAL breaks on network folders
        keep=app.BACKUP_KEEP;app.BACKUP_KEEP=2
        try:
            first=app.backup_database(force=True);self.assertTrue(first.exists())
            self.assertIsNone(app.backup_database())  # a recent copy already exists
            for _ in range(3):time.sleep(1.1);app.backup_database(force=True)
            self.assertEqual(len(list(first.parent.glob('portaria-*.db'))),2)
            with closing(sqlite3.connect(first.parent/sorted(p.name for p in first.parent.glob('portaria-*.db'))[-1])) as c:
                self.assertGreater(c.execute('SELECT COUNT(*) FROM users').fetchone()[0],0)
        finally:app.BACKUP_KEEP=keep
    def test_database_folder_from_config(self):
        folder=Path(self.tmp.name)/'rede';folder.mkdir();config=app.CONFIG
        app.CONFIG=Path(self.tmp.name)/'config.json'
        try:
            self.assertEqual(app.configured_db(lambda _:f'"{folder}"'),folder/'portaria.db')  # first run asks and saves
            self.assertEqual(json.loads(app.CONFIG.read_text(encoding='utf-8'))['pasta_banco'],str(folder))
            self.assertEqual(app.configured_db(lambda _:self.fail('should not ask again')),folder/'portaria.db')
            app.CONFIG.write_text(json.dumps({'pasta_banco':str(folder/'fora-do-ar')}),encoding='utf-8')
            with self.assertRaises(SystemExit):app.configured_db()
        finally:app.CONFIG=config

    def test_recognizes_its_own_server(self):
        self.assertTrue(app.is_running_here(self.base))
        other=ThreadingHTTPServer(('127.0.0.1',0),http.server.SimpleHTTPRequestHandler)  # some other program
        threading.Thread(target=other.serve_forever,daemon=True).start()
        try:self.assertFalse(app.is_running_here(f'http://127.0.0.1:{other.server_port}'))
        finally:other.shutdown();other.server_close()

    def door_clients(self,prefix):
        """Logged-in admin and operator of the door tests: (admin, admin csrf, operator, operator csrf)."""
        with closing(app.connect()) as c, c:
            for login,role in ((prefix+'-admin','admin'),(prefix+'-op','operador')):
                c.execute('INSERT INTO users(name,username,password,role,created_at) VALUES(?,?,?,?,?)',(*app.valid_user({'name':login,'username':login,'password':'senha-portas-123','role':role}),app.now()))
        admin,op=self.client(),self.client()
        for client,login in ((admin,prefix+'-admin'),(op,prefix+'-op')):
            self.assertEqual(self.req(client,'login','POST',{'username':login,'password':'senha-portas-123'})[0],200)
        return admin,self.req(admin,'session')[1]['user']['csrf'],op,self.req(op,'session')[1]['user']['csrf']

    def test_feminino_lockers_start_at_157(self):
        admin,at,op,ot=self.door_clients('faixa')
        def payload(room,number):return {'nome':'Pessoa','setor':'RH','vestiario':room,'armario':number,'retirada':'2026-10-30T08:00'}
        link=lambda room,number:self.req(op,'records','POST',{'module':'chaves','payload':payload(room,number)},ot)
        code,body=link('Feminino','156');self.assertEqual(code,409);self.assertIn('157 a 300',body['error'])
        self.assertEqual(link('Feminino','157')[0],201)
        self.assertEqual(link('Masculino','156')[0],201)  # the men's room keeps 1 to 300
        self.assertEqual(self.req(admin,'mapas/bloqueio','POST',{'mapa':'feminino','numero':156,'bloqueado':True,'motivo':'Teste'},at)[0],400)
        self.assertEqual(self.req(admin,'mapas/terceirizado','POST',{'mapa':'feminino','numero':156,'terceirizado':True},at)[0],400)
        with closing(app.connect()) as c, c:  # a record saved before the rule keeps working
            uid=c.execute("SELECT id FROM users WHERE username='FAIXA-ADMIN'").fetchone()[0]
            rid=c.execute('INSERT INTO records(module,payload,status,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?)',('chaves',json.dumps(payload('Feminino','10')),'Em aberto',uid,app.now(),app.now())).lastrowid
        edit={'module':'chaves','status':'Em aberto','version':1}
        self.assertEqual(self.req(admin,f'records/{rid}','PATCH',{**edit,'payload':payload('Feminino','11')},at)[0],409)  # cannot move to another door out of the range
        self.assertEqual(self.req(admin,f'records/{rid}','PATCH',{**edit,'payload':{**payload('Feminino','10'),'setor':'TI'}},at)[0],200)  # same door is fine
        self.assertEqual(self.req(op,f'records/{rid}/retorno','POST',{'payload':{'devolucao':'2026-10-30T18:00'},'version':2},ot)[0],200)  # and it can be released

    def test_door_sequence_block(self):
        admin,at,op,ot=self.door_clients('sequencia')
        seq=lambda client,csrf,**data:self.req(client,'mapas/bloqueio-sequencia','POST',data,csrf)
        settings=lambda:self.req(admin,'bootstrap')[1]['settings']
        good={'mapa':'masculino','de':240,'ate':245,'bloqueado':True,'motivo':'reforma'}
        self.assertEqual(seq(op,ot,**good)[0],403)
        for bad in ({'mapa':'outro'},{'de':245,'ate':240},{'de':0},{'ate':301},{'de':'240'},{'ate':True},{'bloqueado':'sim'},{'motivo':'  '},{'motivo':'x'*201}):
            self.assertEqual(seq(admin,at,**{**good,**bad})[0],400,bad)
        self.assertEqual(seq(admin,at,**{**good,'mapa':'feminino','de':150,'ate':160})[0],400)  # women's room starts at 157
        self.assertEqual(self.req(op,'records','POST',{'module':'chaves','payload':{'nome':'Ana','setor':'RH','vestiario':'Masculino','armario':'242','retirada':'2026-10-30T08:00'}},ot)[0],201)
        self.assertEqual(self.req(admin,'mapas/bloqueio','POST',{'mapa':'masculino','numero':243,'bloqueado':True,'motivo':'fechadura'},at)[0],200)
        code,body=seq(admin,at,**good);self.assertEqual(code,200)
        self.assertEqual((body['alterados'],body['ocupados'],body['ja_estavam']),([240,241,244,245],[242],[243]))
        self.assertEqual(json.loads(settings()['armarios_masculino_bloqueados']),[240,241,243,244,245])
        reasons=json.loads(settings()['armarios_masculino_bloqueados_motivos'])
        self.assertEqual((reasons['240']['motivo'],reasons['243']['motivo']),('REFORMA','FECHADURA'))  # the older reason is kept
        log=[a for a in self.req(admin,'audit')[1] if a['action']=='Bloqueio em sequência' and a['entity']=='armário masculino 240 a 245']
        self.assertEqual(len(log),1);self.assertIn('REFORMA',log[0]['details'])
        code,body=seq(admin,at,mapa='masculino',de=240,ate=245,bloqueado=False);self.assertEqual(code,200)  # no reason to unblock
        self.assertEqual((body['alterados'],body['ocupados'],body['ja_estavam']),([240,241,243,244,245],[],[242,]))
        self.assertEqual(json.loads(settings()['armarios_masculino_bloqueados']),[])
        self.assertEqual(json.loads(settings()['armarios_masculino_bloqueados_motivos']),{})
        code,body=seq(admin,at,mapa='escaninhos',de=210,ate=216,bloqueado=True,motivo='Teste');self.assertEqual((code,len(body['alterados'])),(200,7))
        self.assertEqual(seq(admin,at,mapa='escaninhos',de=210,ate=216,bloqueado=False)[0],200)

    def test_door_terceirizado_mark(self):
        admin,at,op,ot=self.door_clients('terceiro')
        mark=lambda client,csrf,**data:self.req(client,'mapas/terceirizado','POST',data,csrf)
        marked=lambda key:json.loads(self.req(op,'bootstrap')[1]['settings'].get(key,'[]'))
        good={'mapa':'masculino','numero':250,'terceirizado':True}
        self.assertEqual(mark(op,ot,**good)[0],403)
        for bad in ({'mapa':'outro'},{'numero':0},{'numero':301},{'numero':'250'},{'terceirizado':'sim'}):
            self.assertEqual(mark(admin,at,**{**good,**bad})[0],400,bad)
        self.assertEqual(mark(admin,at,**good)[0],200)
        self.assertEqual(mark(admin,at,mapa='escaninhos',numero=200,terceirizado=True)[0],200)
        self.assertEqual((marked('terceirizados_masculino'),marked('terceirizados_escaninhos'),marked('terceirizados_feminino')),([250],[200],[]))
        self.assertTrue(any(a['action']=='Marca de terceirizado' and a['entity']=='armário masculino 250' for a in self.req(admin,'audit')[1]))
        code,linked=self.req(op,'records','POST',{'module':'chaves','payload':{'nome':'Bia','setor':'RH','vestiario':'Masculino','armario':'250','retirada':'2026-10-30T08:00'}},ot)  # the mark only signals: anyone can be linked
        self.assertEqual(code,201)
        self.assertEqual(self.req(op,f"records/{linked['id']}/retorno",'POST',{'payload':{'devolucao':'2026-10-30T18:00'},'version':1},ot)[0],200)
        self.assertEqual(self.req(admin,'mapas/bloqueio','POST',{'mapa':'masculino','numero':250,'bloqueado':True,'motivo':'Teste'},at)[0],200)  # block is independent
        self.assertEqual(self.req(admin,'mapas/bloqueio','POST',{'mapa':'masculino','numero':250,'bloqueado':False},at)[0],200)
        self.assertEqual(marked('terceirizados_masculino'),[250])
        self.assertEqual(mark(admin,at,**{**good,'terceirizado':False})[0],200)
        self.assertEqual(mark(admin,at,mapa='escaninhos',numero=200,terceirizado=False)[0],200)
        self.assertEqual((marked('terceirizados_masculino'),marked('terceirizados_escaninhos')),([],[]))

    def test_text_fields_saved_uppercase(self):
        _,clean,_=app.validate_record({'module':'rotas','payload':{'rota':'rota feira','tipo':'Regular','placa':'abc1d23','condutor':'joão da silva','lacre':'lc-01','saida':'2026-10-30T08:00','liberado_por':'L','observacoes':'chegou às 8h'}})
        self.assertEqual((clean['rota'],clean['condutor'],clean['lacre'],clean['placa'],clean['observacoes']),('ROTA FEIRA','JOÃO DA SILVA','LC-01','ABC1D23','CHEGOU ÀS 8H'))
        self.assertEqual((clean['tipo'],clean['saida']),('Regular','2026-10-30T08:00:00'))  # options and dates untouched
        _,clean,_=app.validate_record({'module':'chaves','payload':{'nome':'ana','setor':'rh','vestiario':'Feminino','armario':'3','retirada':'2026-10-30T08:00'}})
        self.assertEqual((clean['nome'],clean['setor'],clean['vestiario']),('ANA','RH','Feminino'))
        with closing(app.connect()) as c, c:
            uid=c.execute('INSERT INTO users(name,username,password,role,created_at) VALUES(?,?,?,?,?)',(*app.valid_user({'name':'Caixa','username':'caixa-alta','password':'senha-caixa-123','role':'admin'}),app.now())).lastrowid
            old={'nome':'pedro antigo','documento':'123','empresa':'empresa x','motivo':'visita','area':'rh'}
            rid=c.execute('INSERT INTO records(module,payload,status,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?)',('pessoas',json.dumps(old),'Concluído',uid,app.now(),app.now())).lastrowid
            c.execute("DELETE FROM settings WHERE key='texto_maiusculo'")
        app.initialize()  # existing records are converted once
        with closing(app.connect()) as c:
            saved=json.loads(c.execute('SELECT payload FROM records WHERE id=?',(rid,)).fetchone()[0])
            self.assertEqual((saved['nome'],saved['empresa'],saved['area']),('PEDRO ANTIGO','EMPRESA X','RH'))
            self.assertTrue(c.execute("SELECT 1 FROM settings WHERE key='texto_maiusculo'").fetchone())

    def test_user_and_unit_text_saved_uppercase(self):
        with closing(app.connect()) as c, c:
            c.execute('INSERT INTO users(name,username,password,role,created_at) VALUES(?,?,?,?,?)',(*app.valid_user({'name':'gestão maiúscula','username':'gestor.caixa','password':'Senha-Caixa-123','role':'admin'}),app.now()))
            c.execute("INSERT INTO users(name,username,password,role,created_at) VALUES('Login Antigo','login.antigo',?,'admin',?)",(app.password_hash('Senha-Antiga-123'),app.now()))
            saved=c.execute("SELECT name,username FROM users WHERE username='gestor.caixa'").fetchone()
        self.assertEqual((saved['name'],saved['username']),('GESTÃO MAIÚSCULA','GESTOR.CAIXA'))
        self.assertEqual(self.req(self.client(),'login','POST',{'username':'login.antigo','password':'Senha-Antiga-123'})[0],200)  # logins saved before the rule still work
        self.assertEqual(self.req(self.client(),'login','POST',{'username':'LOGIN.ANTIGO','password':'Senha-Antiga-123'})[0],200)
        self.assertEqual(self.req(self.client(),'login','POST',{'username':'GESTOR.CAIXA','password':'senha-caixa-123'})[0],401)  # the password stays case sensitive
        admin=self.client()
        self.assertEqual(self.req(admin,'login','POST',{'username':'gestor.caixa','password':'Senha-Caixa-123'})[0],200)
        csrf=self.req(admin,'session')[1]['user']['csrf']
        uid=self.req(admin,'users','POST',{'name':'novo operador','username':'novo.operador','password':'senha-operador-1','role':'admin'},csrf)[1]['id']
        self.assertEqual(self.req(admin,'users/'+str(uid),'PATCH',{'name':'operador editado'},csrf)[0],200)
        self.assertEqual(self.req(admin,'settings','PATCH',{'unidade':'cd bahia'},csrf)[0],200)
        with closing(app.connect()) as c:
            user=c.execute('SELECT name,username FROM users WHERE id=?',(uid,)).fetchone()
            self.assertEqual((user['name'],user['username']),('OPERADOR EDITADO','NOVO.OPERADOR'))
            self.assertEqual(c.execute("SELECT value FROM settings WHERE key='unidade'").fetchone()[0],'CD BAHIA')

    def upload(self,client,csrf,data):
        r=urllib.request.Request(self.base+'/api/bases',method='POST',data=data,headers={'Content-Type':'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet','X-CSRF-Token':csrf})
        try:response=client.open(r)
        except urllib.error.HTTPError as e:response=e
        return response.code,json.loads(response.read())
    def test_spreadsheet_bases(self):
        with closing(app.connect()) as c, c:
            for login in ('base-admin','base-op'):
                c.execute('INSERT INTO users(name,username,password,role,created_at) VALUES(?,?,?,?,?)',(*app.valid_user({'name':login,'username':login,'password':'senha-base-1234','role':'admin' if login=='base-admin' else 'operador'}),app.now()))
        admin,op,anonymous=self.client(),self.client(),self.client()
        for client,login in ((admin,'base-admin'),(op,'base-op')):
            self.assertEqual(self.req(client,'login','POST',{'username':login,'password':'senha-base-1234'})[0],200)
        at,ot=self.req(admin,'session')[1]['user']['csrf'],self.req(op,'session')[1]['user']['csrf']
        colaboradores=[['Base de colaboradores - CD'],['Situação','Matricula','Nome Completo','Data da Admissão','Data do Nascimento','Cargo','Gestor'],
                       ['Ativo',114993,'rafael higino santos',45000,33000,'supervisor de inventário','Fulano'],['Desligado',2001,'Maria Souza',44000,32000,'Conferente','Ciclano'],['','','','','','','']]
        self.assertEqual(self.upload(op,ot,make_book({'Colaboradores':colaboradores}))[0],403)
        self.assertEqual(self.upload(admin,at,b'nao e planilha')[0],400)
        code,body=self.upload(admin,at,make_book({'Terceirizados':colaboradores}));self.assertEqual(code,400);self.assertIn('CPF',body['error'])  # wrong columns: no CPF/RG
        code,body=self.upload(admin,at,make_book({'Colaboradores':colaboradores}));self.assertEqual(code,200)
        self.assertEqual(body['abas'],{'colaboradores':{'novos':2,'atualizados':0,'ignorados':0}})
        found=self.req(op,'bases/colaboradores?q=114993')[1]
        self.assertEqual(found[0],{'matricula':'114993','nome':'RAFAEL HIGINO SANTOS','cargo':'SUPERVISOR DE INVENTÁRIO','situacao':'ATIVO'})
        self.assertEqual([f['matricula'] for f in self.req(op,'bases/colaboradores?q=souz')[1]],['2001'])  # name search
        self.assertEqual(self.req(anonymous,'bases/colaboradores?q=souz')[0],401)
        with closing(app.connect()) as c:
            self.assertEqual(c.execute('PRAGMA table_info(base_colaboradores)').fetchall()[-1][1],'updated_at')
            self.assertNotIn('NASCIMENTO',json.dumps([list(r) for r in c.execute('SELECT * FROM base_colaboradores')]))  # birth date and manager are not stored
        colaboradores[2][5]='Coordenador';colaboradores.append(['Ativo',3003,'Novo Colaborador',1,1,'Auxiliar','X'])
        self.assertEqual(self.upload(admin,at,make_book({'Colaboradores':colaboradores},shared=False))[1]['abas']['colaboradores'],{'novos':1,'atualizados':2,'ignorados':0})
        self.assertEqual(self.req(op,'bases/colaboradores?q=114993')[1][0]['cargo'],'COORDENADOR')
        terceiros=[['Nome','CPF','RG','Empresa/Transportadora'],['João Motorista',1234567890,'','Transportes Bahia'],['Ana Ajudante','','12.345.678-9','Log Express'],['Sem Documento','','','X']]
        self.assertEqual(self.upload(admin,at,make_book({'Terceirizados':terceiros}))[1]['abas']['terceirizados'],{'novos':2,'atualizados':0,'ignorados':1})
        self.assertEqual(self.req(op,'bases/terceirizados?documento=012.345.678-90')[1]['pessoa'],{'nome':'JOÃO MOTORISTA','empresa':'TRANSPORTES BAHIA'})  # leading zero restored
        self.assertEqual(self.req(op,'bases/terceirizados?documento=123456789')[1]['pessoa']['nome'],'ANA AJUDANTE')  # RG without punctuation
        self.assertIsNone(self.req(op,'bases/terceirizados?documento=999999999')[1]['pessoa'])
        self.assertEqual(self.req(op,'bases/terceirizados?q=moto')[1],[{'nome':'JOÃO MOTORISTA','empresa':'TRANSPORTES BAHIA'}])  # no documents in name search
        fornecedores=[['Transportador','Fornecedor','Motivo'],['Rodonaves','Distribuidora Nordeste','Avaria'],['Braspress','','Falta de pedido'],['rodonaves','Atacado Sul','avaria']]
        self.assertEqual(self.upload(admin,at,make_book({'Fornecedores':fornecedores}))[0],200)
        listas=self.req(op,'bootstrap')[1]['listas']
        self.assertEqual({k:listas[k] for k in ('transportador','fornecedor','motivo')},{'transportador':['BRASPRESS','RODONAVES'],'fornecedor':['ATACADO SUL','DISTRIBUIDORA NORDESTE'],'motivo':['AVARIA','FALTA DE PEDIDO']})
        summary=self.req(admin,'bases')[1]
        self.assertEqual((summary['colaboradores']['total'],summary['terceirizados']['total'],summary['fornecedores']['motivo']),(3,2,2))
        self.assertEqual(self.req(op,'bases')[0],403)
        self.assertTrue(any(a['action']=='Importação de base' for a in self.req(admin,'audit')[1]))

    @unittest.skipUnless(importlib.util.find_spec('openpyxl'),'openpyxl não instalado')
    def test_spreadsheet_saved_by_excel_library(self):
        import openpyxl
        book=openpyxl.Workbook();book.active.title='Placa do carro e caminhão'
        book.active.append(['Placas dos Caminhoes','Placa do Carro','Condutor','Auxiliar']);book.active.append(['FHP-7342','RVK-0D84','',''])
        sheet=book.create_sheet('Colaboradores')
        for row in (['Situação','Matricula','Nome Completo','Data da Admissão','Data do Nascimento','Cargo','Gestor'],['Ativo',55001,'Carla Dias','2020-01-02','1990-03-04','Analista','Gestor X']):
            sheet.append(row)
        buffer=io.BytesIO();book.save(buffer)
        tabs,ignored=app.bases.read_workbook(buffer.getvalue())
        self.assertEqual(set(tabs),{'frota','colaboradores'});self.assertEqual(ignored,[])
        self.assertEqual(tabs['colaboradores'][1][1][:3],['Ativo','55001','Carla Dias'])
        self.assertEqual(tabs['frota'][0],'Placa do carro e caminhão')

    def test_spreadsheet_workbook_with_all_tabs(self):
        with closing(app.connect()) as c, c:
            for login,role in (('book-admin','admin'),('book-op','operador')):
                c.execute('INSERT INTO users(name,username,password,role,created_at) VALUES(?,?,?,?,?)',(*app.valid_user({'name':login,'username':login,'password':'senha-base-1234','role':role}),app.now()))
        admin,op=self.client(),self.client()
        for client,login in ((admin,'book-admin'),(op,'book-op')):
            self.assertEqual(self.req(client,'login','POST',{'username':login,'password':'senha-base-1234'})[0],200)
        at=self.req(admin,'session')[1]['user']['csrf']
        frota=[['Placas dos Caminhoes','Placa do Carro','Condutor','Auxiliar','Rota'],['GDS-8729','RVK-0D84','Zeca Condutor','Beto Auxiliar','Rota Feira'],['FUP- 4280','','',''],['SJP4B25','','',''],['fup4280','','',''],['PLACA ERRADA','','','']]
        book={'Placa do carro e caminhao':frota,'Colaboradores':[['Situação','Matricula','Nome Completo','Cargo'],['Ativo',77001,'Livro Colaborador','Analista']],
              'Acesso de Terceiros':[['Nome','CPF','RG','Empresa/Transportadora'],['Livro Terceiro',98765432100,'','Empresa Livro']],
              'Fornecedores':[['Transportador','Fornecedor','Motivo'],['Livro Transporte','Livro Fornecedor','Livro Motivo']],'Rascunho':[['qualquer']]}
        code,body=self.upload(admin,at,make_book(book));self.assertEqual(code,200,body)
        self.assertEqual(body['ignoradas'],['Rascunho'])
        self.assertEqual(body['abas']['frota'],{'novos':7,'atualizados':1,'ignorados':1})  # fup4280 repeats FUP- 4280; PLACA ERRADA is left out
        self.assertEqual((body['abas']['colaboradores']['novos'],body['abas']['terceirizados']['novos'],body['abas']['fornecedores']['novos']),(1,1,3))
        listas=self.req(op,'bootstrap')[1]['listas']
        self.assertEqual(listas['placa_caminhao'],['FUP4280','GDS8729','SJP4B25']);self.assertEqual(listas['placa_carro'],['RVK0D84'])
        self.assertEqual((listas['condutor'],listas['auxiliar'],listas['rota']),(['ZECA CONDUTOR'],['BETO AUXILIAR'],['ROTA FEIRA']))
        self.assertEqual(self.req(op,'bases/colaboradores?q=77001')[1][0]['nome'],'LIVRO COLABORADOR')
        self.assertEqual(self.req(op,'bases/terceirizados?documento=98765432100')[1]['pessoa']['nome'],'LIVRO TERCEIRO')
        self.assertEqual(self.req(admin,'bases')[1]['frota'],{'placa_caminhao':3,'placa_carro':1,'condutor':1,'auxiliar':1,'rota':1})
        # A plate from the list is accepted as it is by the record form.
        op_csrf=self.req(op,'session')[1]['user']['csrf']
        route={'module':'rotas','payload':{'rota':'R1','tipo':'Regular','placa':listas['placa_caminhao'][0],'condutor':listas['condutor'][0],'lacre':'L1','saida':'2026-10-28T10:00','liberado_por':'L'}}
        self.assertEqual(self.req(op,'records','POST',route,op_csrf)[0],201)
        # Only the tab sent is touched.
        code,body=self.upload(admin,at,make_book({'Colaboradores':[['Matricula','Nome Completo'],[77002,'So Colaborador']]}))
        self.assertEqual((code,list(body['abas'])),(200,['colaboradores']))
        self.assertEqual(self.req(op,'bootstrap')[1]['listas']['placa_caminhao'],['FUP4280','GDS8729','SJP4B25'])
        # An error in one tab saves nothing and names the tab.
        code,body=self.upload(admin,at,make_book({'Colaboradores':[['Matricula','Nome Completo'],[77003,'Nao Deve Gravar']],'Acesso de Terceiros':[['Coluna errada'],['x']]}))
        self.assertEqual(code,400);self.assertIn('Acesso de Terceiros',body['error'])
        self.assertEqual(self.req(op,'bases/colaboradores?q=77003')[1],[])
        # Tabs that belong to no base, or two tabs for the same base, are refused.
        code,body=self.upload(admin,at,make_book({'Planilha1':[['a']]}));self.assertEqual(code,400);self.assertIn('Colaboradores',body['error'])
        code,body=self.upload(admin,at,make_book({'Colaboradores':[['a']],'Colaboradores antigos':[['a']]}));self.assertEqual(code,400);self.assertIn('Colaboradores antigos',body['error'])

if __name__=='__main__':unittest.main(verbosity=2)
