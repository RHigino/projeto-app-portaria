import http.cookiejar
import http.server
import io
import zipfile
from xml.sax.saxutils import escape
import importlib.util
import json
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

def make_xlsx(rows,shared=True):
    """Minimal .xlsx: strings in sharedStrings (or inline), ints as numeric cells."""
    strings=[];cells=[]
    for r,row in enumerate(rows,1):
        xml=[]
        for col,value in enumerate(row):
            ref=chr(65+col)+str(r)
            if isinstance(value,int):xml.append(f'<c r="{ref}"><v>{value}</v></c>')
            elif shared:strings.append(value);xml.append(f'<c r="{ref}" t="s"><v>{len(strings)-1}</v></c>')
            else:xml.append(f'<c r="{ref}" t="inlineStr"><is><t>{escape(value)}</t></is></c>')
        cells.append(f'<row r="{r}">{"".join(xml)}</row>')
    ns='xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w') as z:
        z.writestr('[Content_Types].xml','<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>')
        z.writestr('xl/workbook.xml',f'<workbook {ns} xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Base" sheetId="1" r:id="rId1"/></sheets></workbook>')
        z.writestr('xl/_rels/workbook.xml.rels','<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="worksheet" Target="worksheets/sheet1.xml"/></Relationships>')
        z.writestr('xl/worksheets/sheet1.xml',f'<worksheet {ns}><sheetData>{"".join(cells)}</sheetData></worksheet>')
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
        record={'module':'rotas','payload':{'rota':'Rota Teste','tipo':'Regular','placa':'ABC1D23','condutor':'Condutor Teste','lacre':'LACRE-001','saida':'2026-10-28T10:00'}}
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
        rid=self.req(admin,'records','POST',{'module':'rotas','payload':{'rota':'R1','tipo':'Extra','placa':'ABC1D23','condutor':'C','lacre':'L1','saida':'2026-10-28T10:00'}},at)[1]['id']
        url=f'records/{rid}/retorno'
        self.assertEqual(self.req(op,url,'POST',{'payload':{'retorno':'2026-10-28T09:00','lacre_retorno':'L2'},'version':1},ot)[0],400)
        self.assertEqual(self.req(op,url,'POST',{'payload':{'retorno':'2026-10-28T12:00'},'version':1},ot)[0],400)
        self.assertEqual(self.req(op,url,'POST',{'payload':{'retorno':'2026-10-28T12:00','lacre_retorno':'L2','placa':'XYZ1234'},'version':1},ot)[0],400)
        self.assertEqual(self.req(op,url,'POST',{'payload':{'retorno':'2026-10-28T12:00','lacre_retorno':'L2'},'version':9},ot)[0],409)
        self.assertEqual(self.req(op,url,'POST',{'payload':{'retorno':'2026-10-28T12:00','lacre_retorno':'L2'},'version':1},ot)[0],200)
        saved=next(r for r in self.req(op,'records')[1] if r['id']==rid)
        self.assertEqual((saved['status'],saved['returner'],saved['payload']['lacre_retorno'],saved['payload']['placa']),('Concluído','Usuario retorno-op','L2','ABC1D23'))
        self.assertEqual(self.req(op,url,'POST',{'payload':{'retorno':'2026-10-28T13:00','lacre_retorno':'L3'},'version':2},ot)[0],400)
        pessoa=self.req(admin,'records','POST',{'module':'pessoas','payload':{'nome':'P','documento':'123','empresa':'E','motivo':'Visita','area':'RH'}},at)[1]['id']
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
        self.assertEqual(self.req(admin,'mapas/bloqueio','POST',{'mapa':'escaninhos','numero':7,'bloqueado':True},at)[0],409)  # occupied
        self.assertEqual(self.req(op,'mapas/bloqueio','POST',{'mapa':'escaninhos','numero':8,'bloqueado':True},ot)[0],403)
        for bad in ({'numero':0,'bloqueado':True},{'numero':'8','bloqueado':True},{'numero':8,'bloqueado':'sim'}):
            self.assertEqual(self.req(admin,'mapas/bloqueio','POST',{'mapa':'escaninhos',**bad},at)[0],400,bad)
        self.assertEqual(self.req(admin,'mapas/bloqueio','POST',{'mapa':'vestiario','numero':8,'bloqueado':True},at)[0],400)  # unknown map
        self.assertEqual(self.req(admin,'mapas/bloqueio','POST',{'mapa':'escaninhos','numero':8,'bloqueado':True},at)[0],200)
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
        for vestiario,bad in (('Masculino','0'),('Masculino','201'),('Masculino','x1'),('','12'),('Unissex','12')):
            self.assertEqual(link(vestiario,bad)[0],400,(vestiario,bad))
        self.assertEqual(self.req(op,'records','POST',{'module':'chaves','payload':{'nome':'P','setor':'S','vestiario':'Masculino','retirada':'2026-10-30T08:00'}},ot)[0],400)  # vestiário without number
        code,first=link('Masculino','012','Diego');self.assertEqual(code,201)
        saved=next(r for r in self.req(op,'records')[1] if r['id']==first['id'])
        self.assertEqual((saved['payload']['vestiario'],saved['payload']['armario']),('Masculino','12'))
        code,body=link('Masculino','12');self.assertEqual(code,409);self.assertIn('armário masculino 12',body['error'])
        self.assertEqual(link('Feminino','12','Elisa')[0],201)  # same number, other locker room
        self.assertEqual(self.req(admin,'mapas/bloqueio','POST',{'mapa':'masculino','numero':12,'bloqueado':True},at)[0],409)  # occupied
        self.assertEqual(self.req(admin,'mapas/bloqueio','POST',{'mapa':'masculino','numero':201,'bloqueado':True},at)[0],400)
        self.assertEqual(self.req(admin,'mapas/bloqueio','POST',{'mapa':'feminino','numero':13,'bloqueado':True},at)[0],200)
        self.assertEqual(json.loads(self.req(op,'bootstrap')[1]['settings']['armarios_feminino_bloqueados']),[13])
        code,body=link('Feminino','13');self.assertEqual(code,409);self.assertIn('bloqueado',body['error'])
        self.assertEqual(link('Masculino','13','Fábio')[0],201)  # block is per locker room
        code,both=link('Masculino','20','Gustavo','60');self.assertEqual(code,201)  # locker and escaninho in one record
        self.assertEqual(self.req(op,'records','POST',{'module':'chaves','payload':{'nome':'H','setor':'S','escaninho':'60','retirada':'2026-10-30T08:00'}},ot)[0],409)
        self.assertEqual(link('Masculino','20')[0],409)
        self.assertEqual(self.req(op,f'records/{both["id"]}/retorno','POST',{'payload':{'devolucao':'2026-10-30T18:00'},'version':1},ot)[0],200)
        self.assertEqual(link('Masculino','20','Igor','60')[0],201)  # both freed by one release
        raw=urllib.request.urlopen(self.base+'/vestiario.svg').read().decode('utf-8')  # one drawing for both rooms
        self.assertEqual(raw.count('class="armario"'),200);self.assertIn('id="armario-200"',raw);self.assertNotIn('<style',raw)

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
        users=lambda:{u['username']:u for u in self.req(admin,'users')[1]}
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
        rota=self.req(admin,'records','POST',{'module':'rotas','payload':{'rota':'R','tipo':'Regular','placa':'ABC1D23','condutor':'C','lacre':'L','saida':'2026-10-28T10:00'}},at)[1]['id']
        self.assertEqual(self.req(admin,'records','POST',{'module':'pessoas','payload':{'nome':'P','documento':'123','empresa':'E','motivo':'Visita','area':'RH'}},at)[0],201)
        self.assertEqual(self.req(op,'login','POST',{'username':'so-pessoas','password':'senha-abas-123'})[0],200)
        ot=self.req(op,'session')[1]['user']['csrf']
        self.assertEqual([m['id'] for m in self.req(op,'bootstrap')[1]['schema']],['pessoas'])
        self.assertEqual({r['module'] for r in self.req(op,'records')[1]},{'pessoas'})
        self.assertEqual(self.req(op,'records','POST',{'module':'rotas','payload':{'rota':'R','tipo':'Regular','placa':'ABC1D23','condutor':'C','lacre':'L','saida':'2026-10-28T10:00'}},ot)[0],403)
        self.assertEqual(self.req(op,f'records/{rota}/retorno','POST',{'payload':{'retorno':'2026-10-28T12:00','lacre_retorno':'L2'},'version':1},ot)[0],404)
        self.assertEqual(self.req(op,'records','POST',{'module':'pessoas','payload':{'nome':'Q','documento':'123','empresa':'E','motivo':'Visita','area':'RH'}},ot)[0],201)
        listed={u['username']:u for u in self.req(admin,'users')[1]}
        self.assertEqual(listed['so-pessoas']['modules'],['pessoas']);self.assertIsNone(listed['abas-admin']['modules'])
        self.assertEqual(self.req(admin,f'users/{uid}','PATCH',{'modules':None},at)[0],200)
        self.assertEqual(self.req(op,'login','POST',{'username':'so-pessoas','password':'senha-abas-123'})[0],200)
        self.assertIn('rotas',[m['id'] for m in self.req(op,'bootstrap')[1]['schema']])

    def test_people_have_single_document_and_no_status(self):
        data={'module':'pessoas','status':'Em aberto','payload':{'nome':'P','documento':'CNH 123','empresa':'E','motivo':'Entrevista','area':'RH'}}
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

    def test_status_only_where_it_matters(self):
        material={'module':'materiais','payload':{'nome':'C','material':'Caixa','quantidade':2,'unidade':'Caixa','autorizacao':'G','liberacao':'Escrito','saida':'2026-10-28T10:00'}}
        self.assertEqual(app.validate_record(material)[2],'Concluído')
        with self.assertRaises(ValueError):app.validate_record({**material,'payload':{**material['payload'],'cargo':'X'}})
        equipamento={'module':'equipamentos','payload':{'nome':'C','matricula':'1','equipamento':'Coletor','patrimonio':'P1','retirada':'2026-10-28T10:00'}}
        self.assertEqual(app.validate_record(equipamento)[2],'Em aberto')  # still open until "Registrar retorno"
        self.assertFalse(app.MODULES['equipamentos'].get('showStatus',True))

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

    def test_text_fields_saved_uppercase(self):
        _,clean,_=app.validate_record({'module':'rotas','payload':{'rota':'rota feira','tipo':'Regular','placa':'abc1d23','condutor':'joão da silva','lacre':'lc-01','saida':'2026-10-30T08:00','observacoes':'chegou às 8h'}})
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

    def upload(self,client,csrf,base,data):
        r=urllib.request.Request(self.base+'/api/bases/'+base,method='POST',data=data,headers={'Content-Type':'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet','X-CSRF-Token':csrf})
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
        self.assertEqual(self.upload(op,ot,'colaboradores',make_xlsx(colaboradores))[0],403)
        self.assertEqual(self.upload(admin,at,'clientes',make_xlsx(colaboradores))[0],404)
        self.assertEqual(self.upload(admin,at,'colaboradores',b'nao e planilha')[0],400)
        code,body=self.upload(admin,at,'terceirizados',make_xlsx(colaboradores));self.assertEqual(code,400);self.assertIn('CPF',body['error'])  # wrong spreadsheet: no nome/documentos
        code,body=self.upload(admin,at,'colaboradores',make_xlsx(colaboradores));self.assertEqual(code,200)
        self.assertEqual(body,{'novos':2,'atualizados':0,'ignorados':0})
        found=self.req(op,'bases/colaboradores?q=114993')[1]
        self.assertEqual(found[0],{'matricula':'114993','nome':'RAFAEL HIGINO SANTOS','cargo':'SUPERVISOR DE INVENTÁRIO','situacao':'ATIVO'})
        self.assertEqual([f['matricula'] for f in self.req(op,'bases/colaboradores?q=souz')[1]],['2001'])  # name search
        self.assertEqual(self.req(anonymous,'bases/colaboradores?q=souz')[0],401)
        with closing(app.connect()) as c:
            self.assertEqual(c.execute('PRAGMA table_info(base_colaboradores)').fetchall()[-1][1],'updated_at')
            self.assertNotIn('NASCIMENTO',json.dumps([list(r) for r in c.execute('SELECT * FROM base_colaboradores')]))  # birth date and manager are not stored
        colaboradores[2][5]='Coordenador';colaboradores.append(['Ativo',3003,'Novo Colaborador',1,1,'Auxiliar','X'])
        self.assertEqual(self.upload(admin,at,'colaboradores',make_xlsx(colaboradores,shared=False))[1],{'novos':1,'atualizados':2,'ignorados':0})
        self.assertEqual(self.req(op,'bases/colaboradores?q=114993')[1][0]['cargo'],'COORDENADOR')
        terceiros=[['Nome','CPF','RG','Empresa/Transportadora'],['João Motorista',1234567890,'','Transportes Bahia'],['Ana Ajudante','','12.345.678-9','Log Express'],['Sem Documento','','','X']]
        self.assertEqual(self.upload(admin,at,'terceirizados',make_xlsx(terceiros))[1],{'novos':2,'atualizados':0,'ignorados':1})
        self.assertEqual(self.req(op,'bases/terceirizados?documento=012.345.678-90')[1]['pessoa'],{'nome':'JOÃO MOTORISTA','empresa':'TRANSPORTES BAHIA'})  # leading zero restored
        self.assertEqual(self.req(op,'bases/terceirizados?documento=123456789')[1]['pessoa']['nome'],'ANA AJUDANTE')  # RG without punctuation
        self.assertIsNone(self.req(op,'bases/terceirizados?documento=999999999')[1]['pessoa'])
        self.assertEqual(self.req(op,'bases/terceirizados?q=moto')[1],[{'nome':'JOÃO MOTORISTA','empresa':'TRANSPORTES BAHIA'}])  # no documents in name search
        fornecedores=[['Transportador','Fornecedor','Motivo'],['Rodonaves','Distribuidora Nordeste','Avaria'],['Braspress','','Falta de pedido'],['rodonaves','Atacado Sul','avaria']]
        self.assertEqual(self.upload(admin,at,'fornecedores',make_xlsx(fornecedores))[0],200)
        listas=self.req(op,'bootstrap')[1]['listas']
        self.assertEqual(listas,{'transportador':['BRASPRESS','RODONAVES'],'fornecedor':['ATACADO SUL','DISTRIBUIDORA NORDESTE'],'motivo':['AVARIA','FALTA DE PEDIDO']})
        summary=self.req(admin,'bases')[1]
        self.assertEqual((summary['colaboradores']['total'],summary['terceirizados']['total'],summary['fornecedores']['motivo']),(3,2,2))
        self.assertEqual(self.req(op,'bases')[0],403)
        self.assertTrue(any(a['action']=='Importação de base' for a in self.req(admin,'audit')[1]))

    @unittest.skipUnless(importlib.util.find_spec('openpyxl'),'openpyxl não instalado')
    def test_spreadsheet_saved_by_excel_library(self):
        import openpyxl
        book=openpyxl.Workbook();sheet=book.active
        for row in (['Situação','Matricula','Nome Completo','Data da Admissão','Data do Nascimento','Cargo','Gestor'],['Ativo',55001,'Carla Dias','2020-01-02','1990-03-04','Analista','Gestor X']):
            sheet.append(row)
        buffer=io.BytesIO();book.save(buffer)
        rows=app.bases.read_xlsx(buffer.getvalue())
        self.assertEqual(rows[1][:3],['Ativo','55001','Carla Dias'])

if __name__=='__main__':unittest.main(verbosity=2)
