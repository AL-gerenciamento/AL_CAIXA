# packaging/orvyn_master.spec
# Uso: pyinstaller packaging/orvyn_master.spec  (rodar a partir da raiz do projeto)
# Mesma logica do orvyn.spec: onefile no Windows/Linux, .app no macOS.
import sys, os, shutil
from PyInstaller.utils.hooks import collect_all

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(SPEC)))

# --- Segurança: NUNCA empacotar o .env real (credenciais de produção).
# Ver mesma explicação em orvyn.spec. ---
_stub_dir = os.path.join(ROOT, "packaging", "_build_stub")
os.makedirs(_stub_dir, exist_ok=True)
_env_stub = os.path.join(_stub_dir, ".env")
shutil.copyfile(os.path.join(ROOT, ".env.example"), _env_stub)

datas = [(os.path.join(ROOT, "assets"), "assets"), (os.path.join(ROOT, "version.txt"), "."), (_env_stub, ".")]
binaries = []
hiddenimports = []
for pkg in ("customtkinter", "matplotlib", "reportlab"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

a = Analysis(
    [os.path.join(ROOT, "admin_panel", "app.py")],
    pathex=[ROOT],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data)

ICON = os.path.join(ROOT, "assets", "icons", "orvyn_master.ico") if sys.platform == "win32" else None

if sys.platform == "darwin":
    exe = EXE(
        pyz, a.scripts, [], exclude_binaries=True, name="ALGL mercado",
        debug=False, strip=False, upx=True, console=False, icon=os.path.join(ROOT, "assets", "icons", "orvyn_master.icns"),
    )
    coll = COLLECT(exe, a.binaries, a.zipfiles, a.datas, strip=False, upx=True, name="ALGL mercado")
    app = BUNDLE(coll, name="ALGL mercado.app", icon=os.path.join(ROOT, "assets", "icons", "orvyn_master.icns"),
                 bundle_identifier="com.aykon.orvynmaster")
else:
    exe = EXE(
        pyz, a.scripts, a.binaries, a.zipfiles, a.datas, [],
        name="ALGL mercado", debug=False, strip=False, upx=True, console=False, icon=ICON,
    )
