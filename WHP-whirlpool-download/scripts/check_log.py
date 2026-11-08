import os
log_path = r'E:\SKILLS\WHP-whirlpool-download\scripts\logs\report_downloader.log'
print('Log exists:', os.path.exists(log_path))
if os.path.exists(log_path):
    with open(log_path, 'r', encoding='utf-8') as f:
        content = f.read()
    print(f'Size: {len(content)} chars, Lines: {len(content.split(chr(10)))}')
