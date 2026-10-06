"""Renders the code and terminal screenshots used in the Methodology section.

Code figures are taken from the real source files (with their real line numbers);
terminal figures are the real output of demo/demo.sh.
Usage: [RR=/path/to/RangeReduce] python make_code_figs.py <demo_output.txt>
The paper's figures use: N=200000 Q=60 bash demo/demo.sh > demo_output.txt
"""
import os
import pathlib
import re
import sys
import textwrap

from PIL import Image, ImageDraw, ImageFont
from pygments import highlight
from pygments.formatters import ImageFormatter
from pygments.lexers import CppLexer

FIG = pathlib.Path(__file__).resolve().parent.parent / "figures"
FIG.mkdir(exist_ok=True)
RR = pathlib.Path(os.environ.get("RR", pathlib.Path.home() / "RangeReduce"))  # patched RangeReduce checkout
MONO = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
MONO_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"
SCALE = 3  # render at 3x so the figure stays sharp when printed at column width


def add_title_bar(img, title, dark=False):
    bar_h = 18 * SCALE
    out = Image.new("RGB", (img.width, img.height + bar_h), "white")
    d = ImageDraw.Draw(out)
    d.rectangle([0, 0, img.width, bar_h], fill="#3c3c3c" if dark else "#dddddd")
    for i, colour in enumerate(["#ff5f56", "#ffbd2e", "#27c93f"]):
        cx = (10 + i * 14) * SCALE
        d.ellipse([cx - 4 * SCALE, bar_h // 2 - 4 * SCALE, cx + 4 * SCALE, bar_h // 2 + 4 * SCALE], fill=colour)
    font = ImageFont.truetype(MONO, 9 * SCALE)
    d.text((56 * SCALE, bar_h // 2), title, fill="#eeeeee" if dark else "#222222", font=font, anchor="lm")
    out.paste(img, (0, bar_h))
    d.rectangle([0, 0, out.width - 1, out.height - 1], outline="#888888", width=SCALE)
    return out


def code_figure(path, first, last, title, out, highlight_lines=()):
    lines = path.read_text().splitlines()[first - 1:last]
    fmt = ImageFormatter(font_name="DejaVu Sans Mono", font_size=9 * SCALE, line_numbers=True,
                         line_number_start=first, line_number_bg="#f0f0f0", line_number_fg="#888888",
                         line_pad=2 * SCALE, image_pad=6 * SCALE, style="default",
                         hl_lines=[n - first + 1 for n in highlight_lines], hl_color="#fff3b0")
    tmp = FIG / "_tmp_code.png"
    tmp.write_bytes(highlight("\n".join(lines) + "\n", CppLexer(), fmt))
    img = add_title_bar(Image.open(tmp).convert("RGB"), title)
    tmp.unlink()
    img.save(FIG / out, dpi=(300, 300))
    print("wrote", out, img.size)


def terminal_figure(text, title, out, width_chars=None):
    font = ImageFont.truetype(MONO, 9 * SCALE)
    bold = ImageFont.truetype(MONO_BOLD, 9 * SCALE)
    rows = text.rstrip("\n").split("\n")
    cw = font.getbbox("M")[2]
    lh = int(12.5 * SCALE)
    w = (width_chars or max(len(r) for r in rows)) * cw + 16 * SCALE
    h = len(rows) * lh + 12 * SCALE
    img = Image.new("RGB", (w, h), "#1e1e1e")
    d = ImageDraw.Draw(img)
    y = 6 * SCALE
    for r in rows:
        if r.startswith("$ "):
            d.text((8 * SCALE, y), "user@pc:~$ ", fill="#4ec94e", font=bold)
            d.text((8 * SCALE + 11 * cw, y), r[2:], fill="#ffffff", font=bold)
        else:
            d.text((8 * SCALE, y), r, fill="#d4d4d4", font=font)
        y += lh
    img = add_title_bar(img, title, dark=True)
    img.save(FIG / out, dpi=(300, 300))
    print("wrote", out, img.size)


def section(text, header):
    """Lines of demo output belonging to one '### Step' block."""
    block = text.split(header, 1)[1].split("### Step", 1)[0]
    return [l for l in block.split("\n")[1:] if l.strip()]  # drop the rest of the header line


tracker = RR / "lib/rocksdb/db/range_heat_tracker.h"
code_figure(tracker, 47, 83, "range_heat_tracker.h  (RecordAndAdmit)", "code_admit.png")
code_figure(tracker, 126, 147, "range_heat_tracker.h  (Decay and Bucket)", "code_decay.png")
code_figure(RR / "lib/rocksdb/db/arena_wrapped_db_iter.cc", 408, 426,
            "arena_wrapped_db_iter.cc  (hook added to RocksDB)", "code_hook.png", highlight_lines=range(416, 424))

demo = pathlib.Path(sys.argv[1]).read_text()
gen = section(demo, "### Step 1")
n_ins, n_upd, n_rq = re.match(r"wrote (\d+) inserts, (\d+) updates, (\d+) range", gen[0]).groups()
data = ["$ python3 gen_workload.py --pattern hotcold \\",
        f"    -I {n_ins} -U {n_upd} -S {n_rq} -Y 0.1 -o workload.txt",
        *textwrap.wrap(gen[0], 62), "$ head -3 workload.txt | cut -c1-60", *gen[2:5],
        "$ grep -m2 '^S' workload.txt", *gen[5:7]]
terminal_figure("\n".join(l[:64] for l in data), "Terminal - dataset (workload.txt)", "term_dataset.png")

disk = section(demo, "### Step 3")
inspect = section(demo, "### Step 4")
inspect = [l for l in inspect if not re.match(r"^\s+\d\s+0\s+0\s*$", l)]  # hide empty levels
sst = [l for l in disk if l.endswith(".sst")]
other = [l for l in disk if not l.endswith(".sst")]
if len(sst) > 6:
    sst = sst[:5] + [f"... ({len(sst)} .sst data files in total)"]
db = ["$ ls -lh db | awk '{print $5, $9}'", *sst, *other,
      "$ ./inspect_db db", *inspect]
terminal_figure("\n".join(l[:64] for l in db), "Terminal - RocksDB database contents", "term_db.png")
