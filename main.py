import json
import os
import random
import sqlite3
import sys
import tkinter as tk
from tkinter import messagebox, ttk
from datetime import datetime
from pathlib import Path

# ----------------------------------------------------------------------------
# Пути
# ----------------------------------------------------------------------------
def _resource_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).parent

def _app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).parent

def _user_data_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA")
                    or os.environ.get("APPDATA")
                    or Path.home())
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME")
                    or Path.home() / ".local" / "share")
    d = base / "Quiz_RTN"
    d.mkdir(parents=True, exist_ok=True)
    return d

DB_FILE = _user_data_dir() / "progress.db"
WINDOW_STATE_FILE = _user_data_dir() / "window_state.json"

# ----------------------------------------------------------------------------
# Оформление
# ----------------------------------------------------------------------------
BG     = "#f4f6f8"
CARD   = "#ffffff"
ACCENT = "#2c6fbb"
OK     = "#1e7a3c"
ERR    = "#b3261e"
GREY   = "#888"

KEYS_TO_BIND = [f"<Key-{i}>" for i in range(1, 10)] + \
               ["<Return>", "<KP_Enter>", "<Escape>"]

# ----------------------------------------------------------------------------
# Разработчик
# ----------------------------------------------------------------------------
DEVELOPER = {
    "name":    "Беляев М.М.",
    "role":    "Заместитель директора по производству взрывных работ",
    "email":   "belyaev.m.m@nitros.ru",
    "org":     "АО НИТРО СИБИРЬ Норд Групп",
    "year":    "2026",
    "version": "1.5",
}


# ----------------------------------------------------------------------------
# Загрузка тестов
# ----------------------------------------------------------------------------
def discover_tests() -> list[dict]:
    tests = []
    app_dir = _app_dir()

    tests_dir = app_dir / "tests"
    if tests_dir.is_dir():
        for p in sorted(tests_dir.glob("*.json")):
            meta = {"code": p.stem, "title": ""}
            try:
                with open(p, encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict) and "_meta" in data:
                    meta = {**meta, **data["_meta"]}
            except Exception as e:
                print(f"⚠ Не удалось прочитать {p}: {e}")
                continue
            tests.append({
                "key": p.stem,
                "code": meta.get("code", p.stem),
                "title": meta.get("title", ""),
                "path": p,
            })

    legacy = app_dir / "questions.json"
    if not tests and legacy.exists():
        tests.append({
            "key": "legacy",
            "code": "Без кода",
            "title": legacy.stem,
            "path": legacy,
        })
    return tests


def load_test(path: Path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict) and "questions" in data:
        return data.get("_meta", {}), data["questions"]
    if isinstance(data, list):
        return {"code": path.stem, "title": ""}, data
    raise ValueError(f"Неизвестный формат {path}")


# ----------------------------------------------------------------------------
# Приложение
# ----------------------------------------------------------------------------
class QuizApp:
    def __init__(self, root):
        self.root = root
        self.root.title(
            f"РТН — тесты по промбезопасности  •  v{DEVELOPER['version']}")
        self.root.configure(bg=BG)

        self.conn = sqlite3.connect(str(DB_FILE))
        self._init_db()

        self.tests = discover_tests()
        if not self.tests:
            messagebox.showerror(
                "Нет тестов",
                "Не найдено ни одного теста.\n\n"
                "Положите JSON-файлы в папку tests\\ рядом с программой,\n"
                "или используйте parser_docx.py для их создания.")
            sys.exit(1)

        # выбранный тест
        self.current_test_key = None
        self.current_test = None
        self.questions = []
        self.by_id = {}

        # состояние сессии
        self.session = []
        self.pos = 0
        self.score = 0
        self.wrong_ids = []
        self.answered = False
        self.mode = "all"
        self.current_q = None

        self.option_widgets = []
        self.check_vars = []
        self.selected_var = None

        self._build_style()
        self._restore_window_state()
        self.show_test_select()

    # ---------------------------------------------------------- БД
    def _init_db(self):
        cur = self.conn.cursor()
        cur.execute("""CREATE TABLE IF NOT EXISTS stats(
            test_key TEXT,
            qid INTEGER,
            ok INTEGER DEFAULT 0,
            fail INTEGER DEFAULT 0,
            is_mistake INTEGER DEFAULT 0,
            last TEXT,
            PRIMARY KEY(test_key, qid))""")
        cur.execute("""CREATE TABLE IF NOT EXISTS sessions(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            test_key TEXT,
            mode TEXT,
            total INTEGER,
            score INTEGER,
            date TEXT)""")

        # Миграция: добавляем is_mistake, если база создана ранее
        cur.execute("PRAGMA table_info(stats)")
        cols = {row[1] for row in cur.fetchall()}
        if "is_mistake" not in cols:
            cur.execute(
                "ALTER TABLE stats ADD COLUMN is_mistake INTEGER DEFAULT 0")
            cur.execute(
                "UPDATE stats SET is_mistake = "
                "CASE WHEN fail > 0 THEN 1 ELSE 0 END")
        self.conn.commit()

    def _record(self, qid, is_ok, in_wrong_mode=False):
        cur = self.conn.cursor()
        cur.execute(
            "INSERT OR IGNORE INTO stats(test_key, qid) VALUES(?,?)",
            (self.current_test_key, qid))

        if is_ok:
            cur.execute(
                "UPDATE stats SET ok = ok + 1, last = ? "
                "WHERE test_key = ? AND qid = ?",
                (datetime.now().isoformat(), self.current_test_key, qid))
            if in_wrong_mode:
                cur.execute(
                    "UPDATE stats SET is_mistake = 0 "
                    "WHERE test_key = ? AND qid = ?",
                    (self.current_test_key, qid))
        else:
            cur.execute(
                "UPDATE stats SET fail = fail + 1, is_mistake = 1, last = ? "
                "WHERE test_key = ? AND qid = ?",
                (datetime.now().isoformat(), self.current_test_key, qid))
        self.conn.commit()

    # ---------------------------------------------------------- UI helpers
    def _build_style(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TButton", font=("Segoe UI", 11), padding=8)
        style.configure("Big.TButton",
                        font=("Segoe UI", 12, "bold"), padding=12)
        style.configure("Test.Horizontal.TProgressbar",
                        background=ACCENT,
                        troughcolor="#e4e9ef",
                        borderwidth=0,
                        thickness=10)

    def _unbind_keys(self):
        for k in KEYS_TO_BIND:
            try:
                self.root.unbind_all(k)
            except Exception:
                pass

    def _clear(self):
        self._unbind_keys()
        for w in self.root.winfo_children():
            w.destroy()
        self.option_widgets = []
        self.check_vars = []
        self.selected_var = None

    def _restore_window_state(self):
        default = {"geometry": "1000x780", "zoomed": True}
        state = default
        try:
            if WINDOW_STATE_FILE.exists():
                state = json.loads(WINDOW_STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            state = default

        try:
            self.root.geometry(state.get("geometry", "1000x780"))
        except Exception:
            self.root.geometry("1000x780")

        if state.get("zoomed"):
            try:
                self.root.state("zoomed")
            except tk.TclError:
                try:
                    self.root.attributes("-zoomed", True)
                except tk.TclError:
                    pass

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _on_close(self):
        try:
            zoomed = (self.root.state() == "zoomed")
            geom = self.root.geometry()
            WINDOW_STATE_FILE.write_text(
                json.dumps({"geometry": geom, "zoomed": zoomed}),
                encoding="utf-8")
        except Exception:
            pass
        self.root.destroy()

    def _add_footer(self, parent, compact=False):
        sep = tk.Frame(parent, bg="#d8dde3", height=1)
        sep.pack(side="bottom", fill="x", padx=20, pady=(10, 0))

        holder = tk.Frame(parent, bg=BG)
        holder.pack(side="bottom", fill="x", pady=(6, 10))

        tk.Label(holder, text=f"Прогресс: {DB_FILE}",
                 font=("Segoe UI", 8), bg=BG, fg=GREY).pack()

        if compact:
            tk.Label(
                holder,
                text=(f"Разработчик: {DEVELOPER['name']}  •  "
                      f"v{DEVELOPER['version']}  •  © {DEVELOPER['year']}"),
                font=("Segoe UI", 9), bg=BG, fg="#555",
            ).pack(pady=(2, 0))
            return

        tk.Label(holder,
                 text=f"Разработчик: {DEVELOPER['name']}",
                 font=("Segoe UI", 10, "bold"),
                 bg=BG, fg=ACCENT).pack(pady=(4, 0))
        tk.Label(holder,
                 text=f"{DEVELOPER['role']}  •  {DEVELOPER['email']}",
                 font=("Segoe UI", 9), bg=BG, fg="#555").pack()
        tk.Label(holder,
                 text=f"© {DEVELOPER['year']} {DEVELOPER['org']}  •  "
                      f"Версия {DEVELOPER['version']}",
                 font=("Segoe UI", 9), bg=BG, fg=GREY).pack(pady=(0, 2))

    # ---------------------------------------------------------- выбор теста
    def show_test_select(self):
        self._clear()
        self.current_test = None
        self.current_test_key = None

        f = tk.Frame(self.root, bg=BG)
        f.pack(expand=True, fill="both", padx=20, pady=15)

        tk.Label(f, text="РТН — подготовка к аттестации",
                 font=("Segoe UI", 22, "bold"),
                 bg=BG, fg=ACCENT).pack(pady=(5, 3))
        tk.Label(f, text="Выберите тест",
                 font=("Segoe UI", 12), bg=BG, fg="#444").pack(pady=(0, 15))

        # --- сетка 4 колонки ---
        grid = tk.Frame(f, bg=BG)
        grid.pack(fill="x", padx=10)
        COLS = 4
        for c in range(COLS):
            grid.columnconfigure(c, weight=1, uniform="testcard")

        cur = self.conn.cursor()
        for i, t in enumerate(self.tests):
            covered = cur.execute(
                "SELECT COUNT(*) FROM stats WHERE test_key = ? "
                "AND (ok + fail) > 0",
                (t["key"],)).fetchone()[0]
            ok_sum = cur.execute(
                "SELECT COALESCE(SUM(ok), 0) FROM stats WHERE test_key = ?",
                (t["key"],)).fetchone()[0]
            fail_sum = cur.execute(
                "SELECT COALESCE(SUM(fail), 0) FROM stats WHERE test_key = ?",
                (t["key"],)).fetchone()[0]

            try:
                with open(t["path"], encoding="utf-8") as fp:
                    data = json.load(fp)
                total = (len(data["questions"])
                         if isinstance(data, dict) else len(data))
            except Exception:
                total = 0

            pct = round(covered / total * 100) if total else 0
            acc = round(ok_sum / (ok_sum + fail_sum) * 100) \
                  if (ok_sum + fail_sum) else 0

            self._test_card(grid, i // COLS, i % COLS, t,
                            covered, total, pct, acc)

        ttk.Button(f, text="🚪  Выход", style="Big.TButton",
                   width=30, command=self.root.quit).pack(pady=(20, 5))

        self._add_footer(f)

    def _test_card(self, parent, row, col, test, covered, total, pct, acc):
        """Плитка теста: цветная полоса, крупный процент, бар снизу."""
        CARD_W = 350
        CARD_H = 250
        stripe_color = self._pct_color(pct) if pct > 0 else "#d0d5da"

        card = tk.Frame(parent, bg=CARD, bd=1, relief="solid",
                        width=CARD_W, height=CARD_H)
        card.grid(row=row, column=col, padx=8, pady=8)
        card.pack_propagate(False)

        # Цветная полоса-индикатор сверху
        stripe = tk.Frame(card, bg=stripe_color, height=5)
        stripe.pack(fill="x")

        inner = tk.Frame(card, bg=CARD)
        inner.pack(fill="both", expand=True, padx=14, pady=8)

        # --- верх: код слева, точность справа ---
        top = tk.Frame(inner, bg=CARD)
        top.pack(fill="x")

        tk.Label(top, text=test["code"],
                 font=("Segoe UI", 11, "bold"),
                 bg=CARD, fg=ACCENT).pack(side="left")

        if covered > 0:
            tk.Label(top, text=f"точность {acc}%",
                     font=("Segoe UI", 8),
                     bg=CARD, fg="#999").pack(side="right")

        # --- центр: крупный процент ---
        tk.Label(inner, text=f"{pct}%",
                 font=("Segoe UI", 30, "bold"),
                 bg=CARD, fg=stripe_color).pack(expand=True)

        # --- низ: название, бар, число ---
        bottom = tk.Frame(inner, bg=CARD)
        bottom.pack(fill="x", side="bottom")

        title_text = test["title"] if test["title"] else "—"
        tk.Label(bottom, text=title_text,
                 font=("Segoe UI", 8),
                 bg=CARD, fg="#666",
                 anchor="nw", justify="left",
                 wraplength=CARD_W - 30,
                 height=3).pack(fill="x")

        bar_row = tk.Frame(bottom, bg=CARD)
        bar_row.pack(fill="x", pady=(3, 0))

        bar = ttk.Progressbar(bar_row, value=pct, maximum=100,
                              style="Test.Horizontal.TProgressbar")
        bar.pack(side="left", fill="x", expand=True)

        tk.Label(bar_row, text=f"  {covered}/{total}",
                 font=("Segoe UI", 8),
                 bg=CARD, fg="#888").pack(side="left")

        self._bind_card_click(card, test)

    def _bind_card_click(self, widget, test):
        widget.bind("<Button-1>", lambda e, t=test: self.open_test(t))
        try:
            widget.configure(cursor="hand2")
        except Exception:
            pass
        for child in widget.winfo_children():
            self._bind_card_click(child, test)

    def _pct_color(self, pct):
        if pct >= 90:
            return OK
        if pct >= 50:
            return "#b8860b"
        if pct > 0:
            return ACCENT
        return GREY

    def open_test(self, test):
        self.current_test = test
        self.current_test_key = test["key"]
        meta, qs = load_test(test["path"])
        self.questions = qs
        self.by_id = {q["id"]: q for q in qs}
        self.root.title(
            f"{meta.get('code', test['code'])} — "
            f"{meta.get('title', test['title'])}  •  "
            f"v{DEVELOPER['version']}")
        self.show_menu()

    # ---------------------------------------------------------- меню теста
    def show_menu(self):
        self._clear()
        f = tk.Frame(self.root, bg=BG)
        f.pack(expand=True, fill="both", padx=40, pady=20)

        t = self.current_test
        tk.Label(f, text=t["code"], font=("Segoe UI", 28, "bold"),
                 bg=BG, fg=ACCENT).pack(pady=(10, 0))
        if t["title"]:
            tk.Label(f, text=t["title"], font=("Segoe UI", 11),
                     bg=BG, fg="#444",
                     wraplength=800).pack(pady=(0, 20))

        def btn(text, cmd):
            ttk.Button(f, text=text, command=cmd,
                       style="Big.TButton", width=42).pack(pady=5)

        total = len(self.questions)

        # Сколько сейчас в списке ошибок
        cur = self.conn.cursor()
        mistakes_cnt = cur.execute(
            "SELECT COUNT(*) FROM stats WHERE test_key = ? AND is_mistake = 1",
            (self.current_test_key,)).fetchone()[0]
        wrong_label = f"🔁  Работа над ошибками ({mistakes_cnt})"

        btn(f"🏁  Марафон: {total} вопросов вразнобой",
            lambda: self.start("all"))
        btn(f"📚  Все вопросы по порядку ({total})",
            lambda: self.start("all_ordered"))
        btn("🎲  Случайные 20 вопросов",
            lambda: self.start("random"))
        btn(wrong_label,
            lambda: self.start("wrong"))
        btn("🧹  Очистить список ошибок",
            self.reset_mistakes)
        btn("📊  Статистика",
            self.show_stats)
        btn("🗑  Сбросить прогресс по этому тесту",
            self.reset_progress)
        btn("↩  Выбрать другой тест",
            self.show_test_select)

        self._add_footer(f)

    # ---------------------------------------------------------- старт
    def start(self, mode):
        if mode == "all":
            ids = [q["id"] for q in self.questions]
            random.shuffle(ids)
        elif mode == "all_ordered":
            ids = [q["id"] for q in self.questions]
        elif mode == "random":
            ids = random.sample([q["id"] for q in self.questions],
                                min(20, len(self.questions)))
        elif mode == "wrong":
            cur = self.conn.cursor()
            rows = cur.execute(
                "SELECT qid FROM stats "
                "WHERE test_key = ? AND is_mistake = 1 "
                "ORDER BY last ASC",
                (self.current_test_key,)).fetchall()
            seen = set()
            ids = []
            for r in rows:
                if r[0] not in seen:
                    seen.add(r[0])
                    ids.append(r[0])
            if not ids:
                messagebox.showinfo(
                    "Работа над ошибками",
                    "Список ошибок пуст.\n"
                    "Либо вы всё выучили, либо ещё не ошибались.")
                return
        else:
            return

        self.session = ids
        self.pos = 0
        self.score = 0
        self.wrong_ids = []
        self.mode = mode
        self.show_question()

    # ---------------------------------------------------------- подготовка
    def _prepare_question(self, q):
        q = dict(q)
        if self.mode != "all":
            return q
        order = list(range(len(q["options"])))
        random.shuffle(order)
        new_options = [None] * len(order)
        for new_idx, old_idx in enumerate(order):
            new_options[new_idx] = q["options"][old_idx]
        old_correct = set(q["correct"])
        new_correct = [new_idx for new_idx, old_idx in enumerate(order)
                       if old_idx in old_correct]
        q["options"] = new_options
        q["correct"] = sorted(new_correct)
        return q

    # ---------------------------------------------------------- вопрос
    def show_question(self):
        self._clear()
        if self.pos >= len(self.session):
            self.show_result()
            return

        raw = self.by_id[self.session[self.pos]]
        q = self._prepare_question(raw)
        self.current_q = q
        self.answered = False

        header = tk.Frame(self.root, bg=BG)
        header.pack(fill="x", padx=30, pady=(15, 5))
        tk.Label(header,
                 text=f"Вопрос {self.pos + 1} / {len(self.session)}",
                 font=("Segoe UI", 11, "bold"), bg=BG,
                 fg=ACCENT).pack(side="left")
        tk.Label(header, text=f"Правильно: {self.score}",
                 font=("Segoe UI", 11), bg=BG).pack(side="right")

        card = tk.Frame(self.root, bg=CARD, bd=1, relief="solid")
        card.pack(fill="both", expand=True, padx=30, pady=10)

        tk.Label(card, text=q["question"],
                 font=("Segoe UI", 13, "bold"),
                 bg=CARD, wraplength=900, justify="left",
                 anchor="w").pack(fill="x", padx=20, pady=(18, 12))

        hint = " (выберите несколько, 1–N)" if q.get("multi") else " (1–N)"
        tk.Label(card, text="Варианты ответа" + hint,
                 font=("Segoe UI", 10, "italic"), bg=CARD, fg="#666",
                 anchor="w").pack(fill="x", padx=20)

        if q.get("multi"):
            for i, opt in enumerate(q["options"], start=1):
                v = tk.BooleanVar()
                w = tk.Checkbutton(
                    card, text=f"{i})  {opt}", variable=v, bg=CARD,
                    font=("Segoe UI", 11), wraplength=880,
                    justify="left", anchor="w", activebackground=CARD)
                w.pack(fill="x", padx=30, pady=3)
                self.check_vars.append(v)
                self.option_widgets.append(w)
        else:
            self.selected_var = tk.IntVar(value=-1)
            for i, opt in enumerate(q["options"]):
                w = tk.Radiobutton(
                    card, text=f"{i + 1})  {opt}",
                    variable=self.selected_var, value=i, bg=CARD,
                    font=("Segoe UI", 11), wraplength=880,
                    justify="left", anchor="w", activebackground=CARD)
                w.pack(fill="x", padx=30, pady=3)
                self.option_widgets.append(w)

        self.feedback = tk.Label(card, text="",
                                 font=("Segoe UI", 11, "bold"),
                                 bg=CARD, wraplength=900,
                                 justify="left", anchor="w")
        self.feedback.pack(fill="x", padx=20, pady=(10, 0))

        self.ref_label = tk.Label(card, text="",
                                  font=("Segoe UI", 9, "italic"),
                                  bg=CARD, fg="#555", wraplength=900,
                                  justify="left", anchor="w")
        self.ref_label.pack(fill="x", padx=20, pady=(2, 15))

        bottom = tk.Frame(self.root, bg=BG)
        bottom.pack(fill="x", padx=30, pady=(5, 20))

        ttk.Button(bottom, text="← В меню",
                   command=self.show_menu).pack(side="left")

        tk.Label(bottom,
                 text="Клавиши 1–N — выбрать,  Enter — ответить/далее,  Esc — в меню",
                 font=("Segoe UI", 9), bg=BG, fg=GREY).pack(side="left", padx=20)

        self.action_btn = ttk.Button(bottom, text="Ответить",
                                     command=self.check_answer)
        self.action_btn.pack(side="right")

        self._bind_question_keys()
        self.root.focus_set()

    # ---------------------------------------------------------- клавиатура
    def _bind_question_keys(self):
        self._unbind_keys()
        for i in range(1, 10):
            self.root.bind_all(f"<Key-{i}>",
                               self._make_number_handler(i - 1))
        self.root.bind_all("<Return>",   lambda e: self._on_enter())
        self.root.bind_all("<KP_Enter>", lambda e: self._on_enter())
        self.root.bind_all("<Escape>",   lambda e: self.show_menu())

    def _make_number_handler(self, idx):
        def handler(_event):
            if self.answered or not self.current_q:
                return
            if idx >= len(self.current_q["options"]):
                return
            if self.current_q.get("multi"):
                v = self.check_vars[idx]
                v.set(not v.get())
            else:
                self.selected_var.set(idx)
        return handler

    def _on_enter(self):
        if hasattr(self, "action_btn") and self.action_btn.winfo_exists():
            self.action_btn.invoke()

    # ---------------------------------------------------------- проверка
    def _selected(self, q):
        if q.get("multi"):
            return {i for i, v in enumerate(self.check_vars) if v.get()}
        sel = self.selected_var.get()
        return {sel} if sel >= 0 else set()

    def check_answer(self):
        q = self.current_q
        if q is None:
            return

        if self.answered:
            self.pos += 1
            self.show_question()
            return

        sel = self._selected(q)
        if not sel:
            messagebox.showwarning("Ответ", "Выберите хотя бы один вариант.")
            return

        correct = set(q["correct"])
        is_ok = sel == correct

        self._record(q["id"], is_ok, in_wrong_mode=(self.mode == "wrong"))
        if is_ok:
            self.score += 1
            self.feedback.config(text="✅ Верно!", fg=OK)
        else:
            self.feedback.config(
                text="❌ Неверно. Правильный ответ выделен ниже.", fg=ERR)
            self.wrong_ids.append(q["id"])

        self._highlight(correct)

        if q.get("reference"):
            self.ref_label.config(text=f"Источник: {q['reference']}")

        self.answered = True
        self.action_btn.config(text="Далее →  (Enter)")

    def _highlight(self, correct):
        for i, w in enumerate(self.option_widgets):
            w.config(fg=OK if i in correct else GREY)

    # ---------------------------------------------------------- результат
    def show_result(self):
        self._clear()
        cur = self.conn.cursor()
        cur.execute(
            "INSERT INTO sessions(test_key, mode, total, score, date) "
            "VALUES(?,?,?,?,?)",
            (self.current_test_key, self.mode, len(self.session),
             self.score, datetime.now().isoformat()))
        self.conn.commit()

        total = len(self.session)
        pct = round(self.score / total * 100, 1) if total else 0

        f = tk.Frame(self.root, bg=BG)
        f.pack(expand=True, fill="both", padx=40, pady=30)

        tk.Label(f, text="Результат",
                 font=("Segoe UI", 24, "bold"),
                 bg=BG, fg=ACCENT).pack(pady=(20, 10))
        tk.Label(f, text=f"{self.score} из {total}  ({pct}%)",
                 font=("Segoe UI", 18), bg=BG).pack(pady=5)

        if pct >= 90:
            color, msg = OK, "Отличный результат!"
        elif pct >= 75:
            color, msg = "#b8860b", "Хорошо, но есть что подтянуть."
        else:
            color, msg = ERR, "Стоит повторить материал."

        tk.Label(f, text=msg, font=("Segoe UI", 13),
                 bg=BG, fg=color).pack(pady=10)

        if self.mode == "wrong" and self.wrong_ids:
            tk.Label(f,
                     text=f"Осталось в списке ошибок: "
                          f"{len(self.wrong_ids)}",
                     font=("Segoe UI", 11), bg=BG, fg="#555").pack(pady=(15, 0))
        elif self.wrong_ids:
            tk.Label(f, text="Вопросы, где были ошибки:",
                     font=("Segoe UI", 11, "bold"),
                     bg=BG).pack(pady=(20, 5))
            tk.Label(f, text=", ".join(map(str, self.wrong_ids)),
                     font=("Segoe UI", 10), bg=BG,
                     wraplength=800).pack()

        ttk.Button(f, text="Пройти ещё раз", style="Big.TButton",
                   command=lambda: self.start(self.mode)).pack(pady=(30, 5))
        ttk.Button(f, text="В меню", style="Big.TButton",
                   command=self.show_menu).pack(pady=5)

        self._add_footer(f)

    # ---------------------------------------------------------- статистика
    def show_stats(self):
        self._clear()
        f = tk.Frame(self.root, bg=BG)
        f.pack(expand=True, fill="both", padx=30, pady=20)

        tk.Label(f, text=f"Статистика — {self.current_test['code']}",
                 font=("Segoe UI", 20, "bold"),
                 bg=BG, fg=ACCENT).pack(pady=10)

        cur = self.conn.cursor()
        rows = cur.execute(
            "SELECT ok, fail FROM stats WHERE test_key = ?",
            (self.current_test_key,)).fetchall()
        total_ok = sum(r[0] for r in rows)
        total_fail = sum(r[1] for r in rows)
        covered = len(rows)
        total_q = len(self.questions)
        mistakes = cur.execute(
            "SELECT COUNT(*) FROM stats "
            "WHERE test_key = ? AND is_mistake = 1",
            (self.current_test_key,)).fetchone()[0]

        info = (
            f"Всего вопросов в тесте: {total_q}\n"
            f"Затронуто вопросов:     {covered}\n"
            f"В списке ошибок:        {mistakes}\n"
            f"Правильных ответов:     {total_ok}\n"
            f"Ошибочных ответов:      {total_fail}\n"
            f"Общий процент:          "
            f"{(total_ok / (total_ok + total_fail) * 100) if (total_ok + total_fail) else 0:.1f}%"
        )
        tk.Label(f, text=info, font=("Segoe UI", 12),
                 bg=BG, justify="left").pack(pady=15)

        tk.Label(f, text="Последние сессии",
                 font=("Segoe UI", 12, "bold"), bg=BG).pack(pady=(20, 5))

        cols = ("date", "mode", "total", "score")
        tree = ttk.Treeview(f, columns=cols, show="headings", height=10)
        for c, t, w in zip(cols, ("Дата", "Режим", "Всего", "Верно"),
                           (180, 140, 80, 80)):
            tree.heading(c, text=t)
            tree.column(c, width=w, anchor="center")
        tree.pack(fill="x")

        mode_names = {
            "all": "Марафон",
            "all_ordered": "По порядку",
            "random": "20 случайных",
            "wrong": "Ошибки",
        }
        for r in cur.execute(
                "SELECT date, mode, total, score FROM sessions "
                "WHERE test_key = ? ORDER BY id DESC LIMIT 20",
                (self.current_test_key,)):
            tree.insert("", "end",
                        values=(r[0][:16],
                                mode_names.get(r[1], r[1]),
                                r[2], r[3]))

        ttk.Button(f, text="← В меню",
                   command=self.show_menu).pack(pady=20)

        self._add_footer(f, compact=True)

    def reset_mistakes(self):
        cur = self.conn.cursor()
        cnt = cur.execute(
            "SELECT COUNT(*) FROM stats "
            "WHERE test_key = ? AND is_mistake = 1",
            (self.current_test_key,)).fetchone()[0]

        if not cnt:
            messagebox.showinfo("Очистка ошибок",
                                "Список ошибок уже пуст.")
            return

        if not messagebox.askyesno(
                "Очистка ошибок",
                f"Убрать {cnt} вопрос(ов) из списка ошибок?\n\n"
                "Статистика правильных/неправильных ответов сохранится — "
                "очистится только сам список «надо повторить»."):
            return

        cur.execute(
            "UPDATE stats SET is_mistake = 0 WHERE test_key = ?",
            (self.current_test_key,))
        self.conn.commit()
        messagebox.showinfo("Готово",
                            f"{cnt} вопрос(ов) убрано из списка ошибок.")

    def reset_progress(self):
        if not messagebox.askyesno(
                "Сброс",
                f"Удалить всю статистику по тесту\n"
                f"«{self.current_test['code']}»?\n\n"
                f"Другие тесты не пострадают."):
            return
        cur = self.conn.cursor()
        cur.execute("DELETE FROM stats    WHERE test_key = ?",
                    (self.current_test_key,))
        cur.execute("DELETE FROM sessions WHERE test_key = ?",
                    (self.current_test_key,))
        self.conn.commit()
        messagebox.showinfo("Готово", "Прогресс по этому тесту сброшен.")


if __name__ == "__main__":
    root = tk.Tk()
    app = QuizApp(root)
    root.mainloop()