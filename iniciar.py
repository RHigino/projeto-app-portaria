"""Opens the browser and starts the local application."""
import sys
if sys.version_info < (3,10):
    raise SystemExit('Instale o Python 3.10 ou superior para iniciar o GateFlow.')
import threading
import webbrowser
import app
if __name__=='__main__':
    opener=threading.Timer(1.2,lambda:webbrowser.open('http://127.0.0.1:8765'))
    opener.daemon=True
    opener.start()
    app.main()
