import zipfile, os

OUTPUT_ZIP = r'C:\Users\Usuario\Desktop\projeto\SmartCity_T1.zip'
BASE       = r'C:\Users\Usuario\Desktop\projeto\SmartCity'

IGNORAR_DIRS = {
    '__pycache__', '.git', 'node_modules', '.idea', 'target',
    '.venv', '.venv-win', '.venv-wsl', 'Scripts', 'Lib', 'lib',
    'bin', 'Include', 'site-packages', 'dist-info'
}
IGNORAR_EXT  = ('.class', '.pyc', '.pyo', '.db', '.pyz', '.dll',
                '.so', '.o', '.a', '.exe', '.DS_Store', '.whl')

# Binários sem extensão na pasta fontes (ELF Linux compilados)
IGNORAR_NOMES_EXATOS = {'camera', 'poste', 'semaforo',
                        'sensor_temperatura', 'sensor_qualidade_ar'}

count = 0
with zipfile.ZipFile(OUTPUT_ZIP, 'w', zipfile.ZIP_DEFLATED) as zf:
    for root, dirs, files in os.walk(BASE):
        dirs[:] = [d for d in dirs if d not in IGNORAR_DIRS
                   and not d.endswith('.dist-info')]
        for fname in files:
            if fname.endswith(IGNORAR_EXT):
                continue
            if fname in IGNORAR_NOMES_EXATOS:
                continue
            fpath   = os.path.join(root, fname)
            rel     = os.path.relpath(fpath, BASE).replace('\\', '/')
            arcname = 'SmartCity/' + rel
            zf.write(fpath, arcname)
            print(arcname)
            count += 1

sz = os.path.getsize(OUTPUT_ZIP)
print(f'\n{count} arquivos  |  {sz/1024:.1f} KB')
