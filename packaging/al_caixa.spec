# packaging/orvyn.spec
# Uso: pyinstaller packaging/al_caixa.spec  (rodar a partir da raiz do projeto)
#
# Windows/Linux: gera um unico arquivo executavel (dist/AL Caixa.exe ou
# dist/AL Caixa) - nada de pasta cheia de dlls/arquivos soltos.
# macOS: gera dist/AL Caixa.app (bundle nativo, ja aparece como 1 icone so).
import sys, os, shutil
from PyInstaller.utils.hooks import collect_all

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(SPEC)))

# --- Segurança: NUNCA empacotar o .env real (tem credenciais de produção:
# SMTP, DATABASE_URL, etc). O executável leva só um .env "em branco" (a
# partir de .env.example); cada instalação recebe as credenciais reais
# depois, editando o .env na pasta persistente (ver utils/paths.py). ---
_stub_dir = os.path.join(ROOT, "packaging", "_build_stub")
os.makedirs(_stub_dir, exist_ok=True)
_env_stub = os.path.join(_stub_dir, ".env")
shutil.copyfile(os.path.join(ROOT, ".env.example"), _env_stub)

datas = [
    (os.path.join(ROOT, "assets"), "assets"),
    (os.path.join(ROOT, "version.txt"), "."),
    (_env_stub, "."),
]
binaries = []
hiddenimports = []

for pkg in ("customtkinter", "matplotlib", "reportlab"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

a = Analysis(
    [os.path.join(ROOT, "main.py")],
    pathex=[ROOT],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data)

ICON = os.path.join(ROOT, "assets", "icons", "orvyn.ico") if sys.platform == "win32" else None

if sys.platform == "darwin":
    exe = EXE(
        pyz, a.scripts, [], exclude_binaries=True, name="AL Caixa",
        debug=False, strip=False, upx=True, console=False, icon=os.path.join(ROOT, "assets", "icons", "orvyn.icns"),
    )
    coll = COLLECT(exe, a.binaries, a.zipfiles, a.datas, strip=False, upx=True, name="AL Caixa")
    app = BUNDLE(
        coll, name="AL Caixa.app", icon=os.path.join(ROOT, "assets", "icons", "orvyn.icns"),
        bundle_identifier="com.aykon.orvyn",
    )
else:
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.zipfiles,
        a.datas,
        [],
        name="AL Caixa",
        debug=False,
        strip=False,
        upx=True,
        console=False,
        icon=ICON,
        version=os.path.join(ROOT, "packaging", "version_info.txt") if sys.platform == "win32" else None,
    )
