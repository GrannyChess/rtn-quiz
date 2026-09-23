# fill_answers.py — интерактивно расставляет правильные ответы
# для указанных id в tests/*.json
#
# Запуск:
#   python fill_answers.py tests/b4_3.json 17 30 38 39 49 53 61 62 111 124 128 138 147 152 162 188 198 212 228

import json
import re
import sys
from pathlib import Path

LETTERS = 'АБВГДЕЖЗИК'


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)

    path = Path(sys.argv[1])
    ids = [int(x) for x in sys.argv[2:]]

    data = json.loads(path.read_text(encoding='utf-8'))
    questions = data['questions']
    by_id = {q['id']: q for q in questions}

    edited = 0
    for qid in ids:
        q = by_id.get(qid)
        if not q:
            print(f"⚠  id={qid} не найден — пропускаю")
            continue

        print(f"\n──── Q{qid}")
        print(f"  {q['question']}")
        print()
        for i, opt in enumerate(q['options']):
            print(f"    {LETTERS[i]})  {opt}")

        cur = ''.join(LETTERS[i] for i in sorted(q.get('correct', [])))
        print(f"\n  Текущий ответ: {cur or '(не задан)'}")

        while True:
            raw = input(
                "  Правильные буквы (например А, либо Б,В для мультивыбора; "
                "'s' — пропустить, 'q' — выйти): "
            ).strip().upper()

            if raw in ('S', 'SKIP', ''):
                print("  → пропущено")
                break
            if raw in ('Q', 'QUIT'):
                path.write_text(
                    json.dumps(data, ensure_ascii=False, indent=2),
                    encoding='utf-8')
                print(f"\nСохранено: {path}  (отредактировано {edited})")
                return

            letters = [x for x in re.split(r'[\s,;]+', raw) if x]
            idxs, bad = [], []
            for L in letters:
                if L in LETTERS and LETTERS.index(L) < len(q['options']):
                    idxs.append(LETTERS.index(L))
                else:
                    bad.append(L)

            if bad:
                print(f"  ⚠  неверные буквы: {bad}  (всего вариантов: {len(q['options'])})")
                continue

            if not idxs:
                print("  ⚠  пустой ответ — введите хотя бы одну букву")
                continue

            q['correct'] = sorted(set(idxs))
            if len(q['correct']) > 1:
                q['multi'] = True
            elif 'multi' in q:
                del q['multi']

            print(f"  ✅  записано: {''.join(LETTERS[i] for i in q['correct'])}")
            edited += 1
            break

    path.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                    encoding='utf-8')
    print(f"\nСохранено: {path}  (отредактировано {edited})")


if __name__ == '__main__':
    main()