# diagnose_docx.py
import sys, zipfile, re
from pathlib import Path

path = Path(sys.argv[1] if len(sys.argv) > 1 else input("Путь к .docx: ").strip('"'))

sig = path.read_bytes()[:8]
print(f"Размер: {path.stat().st_size} байт")
print(f"Первые байты: {sig!r}")
print(f"Настоящий .docx (ZIP): {sig[:2] == b'PK'}")

if sig[:2] != b'PK':
    print("\n⚠ Это не .docx — файл переименован из другого формата.")
    sys.exit(0)

with zipfile.ZipFile(path) as z:
    names = z.namelist()
    print(f"\nВ архиве {len(names)} файлов, есть word/document.xml: {'word/document.xml' in names}")
    xml = z.read('word/document.xml').decode('utf-8')
    print(f"\nРазмер document.xml: {len(xml):,} символов")
    print(f"<w:p>       : {len(re.findall(r'<w:p[ >]', xml))}")
    print(f"<w:r>       : {len(re.findall(r'<w:r[ >]', xml))}")
    print(f"<w:b/>      : {xml.count('<w:b/>')}")
    print(f"<w:b ...>   : {len(re.findall(r'<w:b [^/>]*/?>', xml))}")
    print(f"<w:b w:val=0: {len(re.findall(chr(60)+'w:b w:val=\"(?:0|false)\"', xml))}")
    print(f"<w:i/>      : {xml.count('<w:i/>')}")
    print(f"<w:u ...>   : {len(re.findall(r'<w:u [^/>]*/?>', xml))}")
    print(f"<w:highlight: {xml.count('<w:highlight')}")

print("\n=== Первые 3 непустых абзаца с runs ===")
from docx import Document
doc = Document(str(path))
shown = 0
for p in doc.paragraphs:
    if not p.text.strip():
        continue
    shown += 1
    print(f"\nАбзац: {p.text[:80]!r}")
    print(f"  style: {p.style.name if p.style else None}")
    for r in p.runs[:4]:
        print(f"  run: {r.text[:50]!r}")
        print(f"       bold={r.bold}  italic={r.italic}  underline={r.underline}")
        print(f"       XML: {r._r.xml[:220]}")
    if shown >= 3:
        break