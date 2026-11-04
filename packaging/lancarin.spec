# Spesifikasi PyInstaller Lancarin (Windows). Jalankan dari root proyek.
a = Analysis(
    ["..\\app.py"],
    pathex=[".."],
    binaries=[],
    datas=[("..\\assets", "assets")],
    hiddenimports=["config", "brain", "session", "audio", "stt", "keyring.backends.Windows"],
    hookspath=[],
    runtime_hooks=[],
    excludes=["PySide6.QtWebEngineCore", "PySide6.QtPdf"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [], exclude_binaries=True,
    name="Lancarin", console=False, icon="..\\assets\\lancarin.ico",
)
coll = COLLECT(exe, a.binaries, a.datas, name="Lancarin")
