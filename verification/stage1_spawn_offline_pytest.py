"""Run the unchanged syscall-denial wrapper without replacing spawn's main file."""
if __name__ == '__main__':
    from pathlib import Path
    path=Path('verification/ah-offline-pytest.py')
    exec(compile(path.read_text(),str(path),'exec'),{'__name__':'stage1_offline_guard','__file__':str(path)})
