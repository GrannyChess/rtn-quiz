# peek.py
import re
import sys
from collections import Counter
from docx import Document

if len(sys.argv) < 2:
    print("Использование: python peek.py b12.docx")
    sys.exit(1)

doc = Document(sys.argv[1])

def strip_ns(xml: str) -> str:
    """Убирает xmlns-объявления, чтобы XML было видно глазами."""
    return re.sub(r'\sxmlns(:\w+)?="[^"]*"', '', xml)

# 1. Какие стили абзацев вообще есть
styles = Counter(p.style.name for p in doc.paragraphs if p.text.strip())
print("=== Стили абзацев (топ-15) ===")
for name, cnt in styles.most_common(15):
    print(f"  {cnt:>5}  {name}")

# 2. Уникальные теги в <w:rPr> и <w:pPr> — что вообще есть в документе
doc_xml = "\n".join(p._p.xml for p in doc.paragraphs)
rpr_tags = Counter(re.findall(r'<w:(\w+)[ />]', doc_xml))
interesting = ('b', 'i', 'u', 'color', 'highlight', 'shd', 'sz', 'rStyle',
               'pStyle', 'bdr', 'outlineLvl', 'em', 'szCs', 'vertAlign',
               'rtl', 'spacing', 'position', 'smallCaps', 'strike')
print("\n=== Теги, встречающиеся в документе (только интересные) ===")
for tag in interesting:
    if tag in rpr_tags:
        print(f"  <w:{tag}>: {rpr_tags[tag]}")

# 3. Полный XML двух абзацев-ответов (правильный + неправильный) для Q1
print("\n=== Полный XML абзацев Q1 (эталон и неверный) ===")
targets = [
    "Значение безопасного тока",
    "Длительный воспламеняющий ток",
    "Безопасный импульс воспламенения",
]
for t in targets:
    for p in doc.paragraphs:
        if t in p.text and len(p.text) < 200:
            print(f"\n--- Абзац: {t!r} ---")
            print(f"  style: {p.style.name}")
            print(f"  pPr:   {strip_ns(p._p.pPr.xml) if p._p.pPr is not None else '(нет)'}")
            for i, r in enumerate(p.runs):
                print(f"  run[{i}] text={r.text[:60]!r}")
                if r._r.rPr is not None:
                    print(f"    rPr: {strip_ns(r._r.rPr.xml)}")
                else:
                    print(f"    rPr: (нет)")
            break

# 4. Сравним ещё несколько вопросов — вдруг правильный ответ = что-то регулярное
print("\n=== Проверка гипотез ===")
print("Q1 (эталон): ищем все абзацы с 'Значение безопасного тока'")
for i, p in enumerate(doc.paragraphs):
    if 'Значение безопасного тока' in p.text:
        print(f"  абзац №{i}, style={p.style.name}, len={len(p.text)}")

# 5. Может, у правильного ответа есть пустой run или кавычка, или пробел до буквы?
print("\n=== Сырые начала всех вариантов Q1 и Q2 ===")
for p in doc.paragraphs:
    t = p.text.strip()
    if t and (t.startswith(('А)', 'Б)', 'В)', 'Г)', 'Д)', 'Е)'))):
        # первые 3 варианта каждого вопроса
        print(f"  {t[:90]!r}   style={p.style.name}")
        if "Ростехнадзором" in t:
            break