"""Opens the browser and starts the local application (also the entry point of the .exe)."""
import sys
if sys.version_info < (3,10):
    raise SystemExit('Instale o Python 3.10 ou superior para iniciar o sistema.')
import app

if __name__=='__main__':
    try:
        app.main(open_browser=True)
    except SystemExit as e:
        # In the .exe the console closes at once; keep error messages readable.
        if getattr(sys,'frozen',False) and isinstance(e.code,str):
            print(e.code);input('\nPressione Enter para fechar...')
        raise
    except Exception as e:
        if getattr(sys,'frozen',False):
            print(f'Erro inesperado: {e}');input('\nPressione Enter para fechar...')
        raise
