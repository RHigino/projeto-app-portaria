import http.cookiejar
import importlib.util
import json
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
import app

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

if __name__=='__main__':unittest.main(verbosity=2)
