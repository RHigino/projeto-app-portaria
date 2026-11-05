"""Opens the browser and starts the local application (also the entry point of the .exe)."""
import sys
if sys.version_info < (3,10):
    raise SystemExit('Instale o Python 3.10 ou superior para iniciar o sistema.')
import app

TITLE='Prevenção de Perdas'

def windowless():
    """True in the .exe built without a console window (until open_console gives it one)."""
    if not getattr(sys,'frozen',False) or sys.platform!='win32':return False
    import ctypes
    return not ctypes.windll.kernel32.GetConsoleWindow()

def open_console():
    """Gives the windowless .exe a console for the steps that ask something: first setup and password reset."""
    import ctypes
    kernel=ctypes.windll.kernel32
    # Reuse the console of redefinir_senha.bat when there is one; otherwise open a new window.
    if not kernel.AttachConsole(-1):kernel.AllocConsole()
    kernel.SetConsoleCP(65001);kernel.SetConsoleOutputCP(65001)
    sys.stdin=open('CONIN$','r',encoding='utf-8')
    sys.stdout=sys.stderr=open('CONOUT$','w',encoding='utf-8',buffering=1)

def show_error(message):
    if windowless():
        import ctypes
        ctypes.windll.user32.MessageBoxW(None,message,TITLE,0x10)  # 0x10: error icon
    else:
        print(message);input('\nPressione Enter para fechar...')

def needs_console():
    asks_password=any(a=='--redefinir-senha' or a.startswith('--redefinir-senha=') for a in sys.argv[1:])
    return asks_password or not app.CONFIG.exists()

if __name__=='__main__':
    if windowless() and needs_console():open_console()
    try:
        app.main(open_browser=True)
    except SystemExit as e:
        # Without this the message would vanish with the window (or never show, in the windowless .exe).
        if getattr(sys,'frozen',False) and isinstance(e.code,str):
            show_error(e.code);raise SystemExit(1) from None
        raise
    except Exception as e:
        if getattr(sys,'frozen',False):
            show_error(f'Erro inesperado: {e}');raise SystemExit(1) from None
        raise
