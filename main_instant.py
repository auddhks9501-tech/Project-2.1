#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
부호 층 복사 자동화  —  APT_PIT 층 뿌리기 v1.5-즉시실행

원본 AHK(PasteAndReplace) 로직을 GUI + 전역 단축키로 재구성.

동작 순서:
  1) 창1(산출창)에서 Enter → Ctrl+C   (부호 복사, 예: "1:W1-1")
  2) F3                              (창2 · 복사창으로 전환)
  3) Ctrl+V                          (붙여넣기)
  4) Home → Delete×N                 (앞 층수 삭제, N=시작층 표기 글자수)
  5) Down → Up                       (전체 텍스트 선택)
  6) Ctrl+X                          (접미사 ":W1-1" 잘라내기 → 클립보드 보관)
  7) 각 목표층 라벨에 대해 반복:
       라벨 타이핑 → Ctrl+V(잘라낸 접미사 붙여넣기) → Down(다음 칸 이동)
       ※ 반복 중에는 Enter를 누르지 않음 — 이 프로그램에서 Enter는 새 부호 생성으로 인식됨
  8) 최상층까지 모두 입력 완료 후 마무리로 Enter 1회

지하층 지원: "B5" 형식 입력 시 자동으로 지하층으로 인식.
"""

import sys, os, threading, time

try:
    import tkinter as tk
    from tkinter import ttk, messagebox
except Exception as e:
    sys.exit(f"tkinter 오류: {e}")

try:
    import pyautogui; pyautogui.FAILSAFE=True; pyautogui.PAUSE=0.005; HAS_PAG=True
except ImportError:
    HAS_PAG=False

try:
    import keyboard; HAS_KB=True
except ImportError:
    HAS_KB=False


# ══════════════════════════════════════════════════════════════
#  층 파싱 / 포맷
# ══════════════════════════════════════════════════════════════
def parse_floor(s):
    """'B5' -> -5, '17' -> 17"""
    s = s.strip().upper()
    if not s:
        raise ValueError("층 값이 비어 있습니다.")
    if s.startswith('B'):
        num = s[1:].strip()
        if not num.isdigit():
            raise ValueError(f"잘못된 지하층 표기: '{s}' (예: B5)")
        return -int(num)
    neg = s.startswith('-')
    core = s[1:] if neg else s
    if not core.isdigit():
        raise ValueError(f"잘못된 층 표기: '{s}'")
    return -int(core) if neg else int(core)


def format_floor(n):
    """-5 -> 'B5', 17 -> '17'"""
    return f"B{abs(n)}" if n < 0 else str(n)


def build_floor_sequence(start_str, end_str):
    """시작층→종료층 방향으로 정렬된 층 리스트(0 제외, 시작층 포함)"""
    s = parse_floor(start_str)
    e = parse_floor(end_str)
    lo, hi = min(s, e), max(s, e)
    seq = [n for n in range(lo, hi + 1) if n != 0]
    if s > e:
        seq = list(reversed(seq))
    return seq


def build_labels(start_str, end_str, individual_str, mark_end_e):
    """
    최종 뿌릴 라벨 리스트 생성 (시작층 자체는 제외)
    개별 지정 층은 그대로, 나머지 연속 구간은 'A~B' 로 그룹핑,
    mark_end_e=True 이면 마지막 층에 'E' 접미사
    """
    seq = build_floor_sequence(start_str, end_str)
    if len(seq) < 2:
        return []

    body = seq[1:]  # 시작층(기존 부호) 제외

    individual_set = set()
    for tok in individual_str.split(','):
        tok = tok.strip()
        if tok:
            individual_set.add(parse_floor(tok))

    end_floor = body[-1] if mark_end_e else None

    labels = []
    i, n = 0, len(body)
    while i < n:
        f = body[i]
        if mark_end_e and f == end_floor:
            labels.append(format_floor(f) + "E")
            i += 1
            continue
        if f in individual_set:
            labels.append(format_floor(f))
            i += 1
            continue
        j = i
        run = []
        sign = 1 if f >= 0 else -1  # 지하/지상 경계에서 그룹 분리
        while j < n:
            g = body[j]
            g_sign = 1 if g >= 0 else -1
            if (mark_end_e and g == end_floor) or (g in individual_set) or (g_sign != sign):
                break
            run.append(g)
            j += 1
        if len(run) == 1:
            labels.append(format_floor(run[0]))
        else:
            labels.append(f"{format_floor(run[0])}~{format_floor(run[-1])}")
        i = j
    return labels


# ══════════════════════════════════════════════════════════════
#  키 입력
#  ※ keyboard 라이브러리는 전역 단축키(Shift+F1/ESC) 감지 전용으로만 사용.
#     실제 키 전송(injection)은 pyautogui 로 일원화한다.
#     keyboard.write()/press_and_release() 를 전송에 함께 쓰면 한글 키보드
#     레이아웃에서 스캔코드가 잘못 매핑되어 Shift 꼬임·가짜 Insert 입력·
#     방향키 먹통 같은 증상이 발생하는 것이 확인되어, 전송 경로를 분리했다.
# ══════════════════════════════════════════════════════════════
def _key(k):
    if HAS_PAG:
        if '+' in k: pyautogui.hotkey(*k.split('+'))
        else: pyautogui.press(k)
    elif HAS_KB:
        keyboard.press_and_release(k)

def _type(text):
    s = str(text)
    if HAS_PAG: pyautogui.typewrite(s, interval=0.02)
    elif HAS_KB: keyboard.write(s, delay=0.015)

def _sleep(ms): time.sleep(ms / 1000.0)


def run_floor_spread(labels, start_display, delay_ms, stop_fn):
    """전체 자동화 실행"""
    if stop_fn(): return

    # ① 창1에서 부호 복사
    _key('enter');    _sleep(delay_ms)
    _key('ctrl+c');   _sleep(delay_ms)

    # ② 창2로 전환
    _key('f3');       _sleep(delay_ms)

    # ③ 붙여넣기
    _key('ctrl+v');   _sleep(delay_ms)

    # ④ 앞 층수 삭제 (시작층 표기 글자수만큼)
    _key('home');     _sleep(delay_ms)
    for _ in range(len(start_display)):
        if stop_fn(): return
        _key('delete'); _sleep(delay_ms)

    # ⑤ 전체 텍스트 선택
    _key('down');     _sleep(delay_ms)
    _key('up');       _sleep(delay_ms)

    # ⑥ 접미사 잘라내기 (클립보드 보관)
    _key('ctrl+x');   _sleep(delay_ms)

    # ⑦ 각 목표층 라벨 반복 (Enter 없이 붙여넣기 후 Down으로만 이동)
    for label in labels:
        if stop_fn(): return
        _type(label);     _sleep(delay_ms)
        _key('ctrl+v');   _sleep(delay_ms)
        _key('down');     _sleep(delay_ms)

    # ⑧ 최상층까지 모두 입력 완료 후 마무리 Enter
    if stop_fn(): return
    _key('enter');    _sleep(delay_ms)


# ══════════════════════════════════════════════════════════════
#  색상 팔레트
# ══════════════════════════════════════════════════════════════
BG='#0f1117'; PANEL='#161b27'; CARD='#1e2536'; DARK='#111827'
ACC='#38bdf8'; GRN='#34d399'; RED='#fb7185'; YLW='#fbbf24'
TXT='#f1f5f9'; SUB='#64748b'; BDR='#2d3a50'; PUR='#a78bfa'


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("부호 층 복사 자동화  —  APT_PIT 층 뿌리기  v1.5-즉시실행")
        self.geometry("560x680")
        self.resizable(False, False)
        self.configure(bg=BG)
        self.lift(); self.focus_force()
        try:
            from ctypes import windll
            windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass

        self._stop_flag = False
        self._thread = None

        self._build()
        self._lib_check()
        self._bind_hotkeys()
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    # ─── 빌더 ────────────────────────────────────────────────
    def _card(self, title, color):
        w = tk.Frame(self, bg=BG); w.pack(fill='x', padx=16, pady=(8,0))
        h = tk.Frame(w, bg=color, height=26); h.pack(fill='x'); h.pack_propagate(False)
        tk.Label(h, text=f"  {title}", bg=color, fg='#000',
                 font=('맑은 고딕',10,'bold')).pack(side='left')
        body = tk.Frame(w, bg=CARD, highlightbackground=color, highlightthickness=1)
        body.pack(fill='x')
        return body

    def _build(self):
        # 헤더
        h = tk.Frame(self, bg=PANEL, height=48); h.pack(fill='x'); h.pack_propagate(False)
        tk.Label(h, text="부호 층 복사 자동화", bg=PANEL, fg=ACC,
                 font=('맑은 고딕',13,'bold')).pack(side='left', padx=(16,6), pady=12)
        tk.Label(h, text="APT_PIT 층 뿌리기  v1.5-즉시실행", bg=PANEL, fg=SUB,
                 font=('맑은 고딕',9)).pack(side='left', pady=16)
        bf = tk.Frame(h, bg=PANEL); bf.pack(side='right', padx=12)
        self._lib_lbl = {}
        for nm in ['keyboard','pyautogui']:
            lb = tk.Label(bf, text=f" ? {nm} ", bg=CARD, fg=SUB,
                          font=('Consolas',7), padx=4, pady=2)
            lb.pack(side='left', padx=1); self._lib_lbl[nm] = lb

        # 층 범위 설정
        body = self._card("층 범위 설정", PUR)
        row1 = tk.Frame(body, bg=CARD); row1.pack(fill='x', padx=14, pady=(12,6))

        def field(parent, label):
            f = tk.Frame(parent, bg=CARD); f.pack(side='left', fill='x', expand=True, padx=4)
            tk.Label(f, text=label, bg=CARD, fg=SUB, font=('맑은 고딕',9), anchor='w').pack(fill='x')
            v = tk.StringVar()
            e = tk.Entry(f, textvariable=v, bg=DARK, fg=TXT,
                        font=('맑은 고딕',11), relief='flat', insertbackground=TXT)
            e.pack(fill='x', ipady=4)
            return v

        self.v_start = field(row1, "시작층 (기존 부호, 예: 1 또는 B5)")
        self.v_start.set("1")
        self.v_end = field(row1, "종료층 (예: 17 또는 B1)")
        self.v_end.set("17")

        row2 = tk.Frame(body, bg=CARD); row2.pack(fill='x', padx=14, pady=(0,6))
        tk.Label(row2, text="개별 처리할 층 (콤마 구분, 예: B2,B1,2,3)",
                 bg=CARD, fg=SUB, font=('맑은 고딕',9), anchor='w').pack(fill='x')
        self.v_individual = tk.StringVar(value="2, 3")
        tk.Entry(row2, textvariable=self.v_individual, bg=DARK, fg=TXT,
                 font=('맑은 고딕',11), relief='flat', insertbackground=TXT
                 ).pack(fill='x', ipady=4, pady=(2,0))

        row3 = tk.Frame(body, bg=CARD); row3.pack(fill='x', padx=14, pady=(4,4))
        self.v_mark_e = tk.BooleanVar(value=True)
        tk.Checkbutton(row3, text="최상층에 E 표시 (예: 17E)",
                       variable=self.v_mark_e, bg=CARD, fg=TXT,
                       selectcolor=DARK, activebackground=CARD,
                       activeforeground=TXT, font=('맑은 고딕',9),
                       cursor='hand2', command=self._update_preview
                       ).pack(anchor='w')

        for v in (self.v_start, self.v_end, self.v_individual):
            v.trace_add('write', lambda *a: self._update_preview())

        tk.Button(body, text="🔄 미리보기 갱신", bg='#334155', fg=TXT,
                  font=('맑은 고딕',9), relief='flat', cursor='hand2',
                  pady=4, command=self._update_preview
                  ).pack(fill='x', padx=14, pady=(2,12))

        # 미리보기
        prev = self._card("미리보기 — 생성될 라벨 순서", ACC)
        self.txt_preview = tk.Text(prev, height=4, bg=DARK, fg=GRN,
                                   font=('Consolas',10), relief='flat',
                                   state='disabled', padx=8, pady=8, wrap='word')
        self.txt_preview.pack(fill='x', padx=10, pady=10)

        # 실행 옵션
        opt = self._card("실행 옵션  (즉시 실행 버전)", '#059669')
        or1 = tk.Frame(opt, bg=CARD); or1.pack(fill='x', padx=14, pady=(10,4))
        tk.Label(or1, text="속도", bg=CARD, fg=SUB, font=('맑은 고딕',9)).pack(side='left')
        self.v_speed = tk.StringVar(value='보통')
        for lbl,c in [('빠름',GRN),('보통',ACC),('느림',YLW)]:
            tk.Radiobutton(or1, text=lbl, variable=self.v_speed, value=lbl,
                           bg=CARD, fg=c, selectcolor=CARD,
                           activebackground=CARD, activeforeground=c,
                           font=('맑은 고딕',9), cursor='hand2').pack(side='left', padx=8)

        tk.Label(opt,
            text="⚡ 대기시간 없이 단축키 즉시 실행됩니다.\n"
                 "※ 창1(산출창)에서 부호가 선택된 상태에서 실행하세요\n"
                 "   실행 즉시 창1→창2(F3 전환)로 자동 진행됩니다",
            bg=CARD, fg=YLW, font=('맑은 고딕',8), anchor='w', justify='left'
            ).pack(fill='x', padx=14, pady=(4,12))

        # 실행 버튼
        runf = tk.Frame(self, bg=BG); runf.pack(fill='x', padx=16, pady=(10,4))
        self.btn_run = tk.Button(runf, text="▶  층 뿌리기 시작   [ Shift+F1 ]",
            bg='#f59e0b', fg='#000', font=('맑은 고딕',12,'bold'),
            relief='flat', cursor='hand2', pady=10,
            command=lambda: self._run())
        self.btn_run.pack(fill='x')

        self.btn_stop = tk.Button(runf, text="⏹  중단   [ ESC ]",
            bg=RED, fg='#000', font=('맑은 고딕',9,'bold'),
            relief='flat', cursor='hand2', pady=5, state='disabled',
            command=self._do_stop)
        self.btn_stop.pack(fill='x', pady=(6,0))

        # 상태
        self.v_status = tk.StringVar(value="준비 완료 (즉시 실행) — Shift+F1 로 바로 시작, ESC 로 중단")
        tk.Label(self, textvariable=self.v_status, bg=BG, fg=SUB,
                 font=('맑은 고딕',9), anchor='w', wraplength=520
                 ).pack(fill='x', padx=18, pady=(6,2))

        sty = ttk.Style(); sty.theme_use('default')
        sty.configure("app.Horizontal.TProgressbar",
                      troughcolor=CARD, background=ACC, thickness=6)
        self.pb = ttk.Progressbar(self, style="app.Horizontal.TProgressbar",
                                  orient='horizontal', mode='indeterminate', length=520)
        self.pb.pack(padx=18, pady=(0,10))

        self._update_preview()

    # ─── 미리보기 갱신 ───────────────────────────────────────
    def _update_preview(self):
        self.txt_preview.config(state='normal')
        self.txt_preview.delete('1.0','end')
        try:
            labels = build_labels(
                self.v_start.get(), self.v_end.get(),
                self.v_individual.get(), self.v_mark_e.get())
            if labels:
                self.txt_preview.insert('end', '  →  '.join(labels))
            else:
                self.txt_preview.insert('end', '(입력값을 확인하세요 — 최소 2개 층 필요)')
        except Exception as e:
            self.txt_preview.insert('end', f'⚠ {e}')
        self.txt_preview.config(state='disabled')

    # ─── 라이브러리 체크 ─────────────────────────────────────
    def _lib_check(self):
        for nm, ok in [('keyboard',HAS_KB), ('pyautogui',HAS_PAG)]:
            self._lib_lbl[nm].config(text=f" {'✓' if ok else '✗'} {nm} ",
                                     fg=GRN if ok else RED)
        if not (HAS_KB or HAS_PAG):
            self._status("⚠ keyboard / pyautogui 없음", RED)
            self.btn_run.config(state='disabled')

    # ─── 단축키 ──────────────────────────────────────────────
    def _bind_hotkeys(self):
        def safe_run():
            if self._thread and self._thread.is_alive():
                return
            self.after(0, self._run)
        self._safe_run_fn = safe_run
        self._run_hotkey_handle = None

        if HAS_KB:
            self._register_run_hotkey()
            keyboard.add_hotkey('esc', self._do_stop, suppress=False)
        else:
            self.bind('<Shift-F1>', lambda e: safe_run())
            self.bind('<Escape>', lambda e: self._do_stop())

    def _register_run_hotkey(self):
        """Shift+F1 실행 단축키 등록 (자동화 실행 중에는 해제되어야 함)"""
        if not HAS_KB or self._run_hotkey_handle is not None:
            return
        self._run_hotkey_handle = keyboard.add_hotkey(
            'shift+f1', self._safe_run_fn, suppress=True)

    def _unregister_run_hotkey(self):
        """자동화 시작 직전 실행 단축키를 해제 —
        suppress=True 전역 후킹이 우리가 보내는 키(방향키/F1~F3/Backspace 등)를
        되받아 간섭하면서 방향키·F키 먹통, 백스페이스 순서 꼬임 등이 발생하므로
        실행 도중에는 이 후킹을 완전히 꺼둔다."""
        if not HAS_KB or self._run_hotkey_handle is None:
            return
        try:
            keyboard.remove_hotkey(self._run_hotkey_handle)
        except Exception:
            pass
        self._run_hotkey_handle = None

    def on_close(self):
        if HAS_KB:
            try: keyboard.unhook_all_hotkeys()
            except Exception: pass
        self.destroy()

    # ─── 실행 ────────────────────────────────────────────────
    def _status(self, msg, c=SUB):
        self.v_status.set(msg)

    def _get_delay(self):
        return {'빠름':20,'보통':40,'느림':80}[self.v_speed.get()]

    def _set_busy(self, busy):
        self.btn_run.config(state='disabled' if busy else 'normal')
        self.btn_stop.config(state='normal' if busy else 'disabled')
        if busy:
            self.pb.config(mode='indeterminate'); self.pb.start(10)
        else:
            self.pb.stop(); self.pb.config(mode='determinate', value=0)

    def _do_stop(self):
        self._stop_flag = True

    def _run(self):
        try:
            labels = build_labels(
                self.v_start.get(), self.v_end.get(),
                self.v_individual.get(), self.v_mark_e.get())
        except Exception as e:
            messagebox.showerror("입력 오류", str(e))
            return
        if not labels:
            messagebox.showwarning("알림", "생성할 라벨이 없습니다. 층 범위를 확인하세요.")
            return

        self._stop_flag = False
        delay = self._get_delay()
        start_display = self.v_start.get().strip()
        stop = lambda: self._stop_flag

        # 실행 직전: Shift+F1 전역 후킹을 해제 —
        # 이 후킹이 살아있는 채로 우리가 방향키/F1~F3/Backspace 등을 보내면
        # 후킹이 그 입력들을 다시 가로채면서 키 먹통·순서 꼬임이 발생함
        self._unregister_run_hotkey()

        def worker():
            # Shift+F1 로 실행 직후 물리 Shift 키가 아직 눌린 상태일 수 있어
            # 숫자 입력 시 '2' 대신 '@' 같은 특수문자가 입력되는 문제 방지.
            # ※ ctrl/alt 를 함께 release 하면 Windows가 Ctrl+Shift 로 오인해
            #    키보드 레이아웃(2벌식/3벌식, 한/영)을 전환시켜 버리는 부작용이
            #    있었음 → Shift 만, 충분한 지연을 두고 해제
            # Shift 해제도 pyautogui 로 통일 (keyboard.release 는
            # 위와 같은 이유로 레이아웃에 따라 오작동할 수 있음)
            if HAS_PAG:
                try: pyautogui.keyUp('shift')
                except Exception: pass
            elif HAS_KB:
                try: keyboard.release('shift')
                except Exception: pass
            time.sleep(0.25)

            self.after(0, lambda: self._status(f"⌨  실행 중...  (총 {len(labels)}개 층)"))
            try:
                run_floor_spread(labels, start_display, delay, stop)
                msg = "⏹ 중단됨" if stop() else f"✓ 완료! 총 {len(labels)}개 층 입력됨"
                self.after(0, lambda m=msg: self._finish(m, SUB if stop() else GRN))
            except Exception as e:
                self.after(0, lambda err=str(e): messagebox.showerror("오류", err))
                self.after(0, lambda err=str(e): self._finish(f"✗ 오류: {err}", RED))

        self._set_busy(True)
        self._thread = threading.Thread(target=worker, daemon=True)
        self._thread.start()

    def _finish(self, msg, c):
        self._status(msg, c)
        self._set_busy(False)
        # 자동화 종료 후 Shift+F1 단축키 재등록
        self._register_run_hotkey()


if __name__ == '__main__':
    try:
        App().mainloop()
    except Exception as e:
        try:
            r = tk.Tk(); r.withdraw()
            messagebox.showerror("실행 오류", str(e)); r.destroy()
        except Exception:
            pass
