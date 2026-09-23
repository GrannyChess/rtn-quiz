# inspect_docx.py
import sys
from docx import Document

path = sys.argv[1] if len(sys.argv) > 1 else input("Путь к .docx: ").strip('"')
doc = Document(path)

print(f"Всего абзацев: {len(doc.paragraphs)}")
print(f"Всего таблиц:  {len(doc.tables)}")

# --- если вопросы в таблицах ---
if doc.tables:
    print("\n=== Содержимое таблиц ===")
    for ti, tbl in enumerate(doc.tables[:3]):
        print(f"\n--- Таблица {ti}: {len(tbl.rows)} строк × {len(tbl.columns)} столбцов ---")
        for ri, row in enumerate(tbl.rows[:10]):
            for ci, cell in enumerate(row.cells):
                txt = cell.text.strip().replace("\n", " ⏎ ")
                if txt:
                    print(f"  [{ri},{ci}] {txt[:120]}")
        print("  ...")

# --- первые 40 абзацев с признаками форматирования ---
print("\n=== Первые 60 абзацев (с разметкой) ===")
for i, p in enumerate(doc.paragraphs[:60]):
    t = p.text.strip()
    if not t:
        continue
    bold_chars = sum(len(r.text) for r in p.runs if r.bold)
    total = sum(len(r.text) for r in p.runs) or 1
    underline = sum(len(r.text) for r in p.runs if r.underline)
    style = p.style.name if p.style else "?"
    flag = "B" if bold_chars / total > 0.5 else " "
    flag += "U" if underline / total > 0.5 else " "
    print(f"[{i:>3}] {flag} ({style[:15]:<15}) {t[:130]}")

# --- проверка: не лежит ли всё в одном абзаце ---
print("\n=== Абзацы длиннее 500 символов ===")
long_paras = [p for p in doc.paragraphs if len(p.text) > 500]
for p in long_paras[:5]:
    print(f"\nДлина {len(p.text)} символов:")
    print(repr(p.text[:400]))
    print("...")