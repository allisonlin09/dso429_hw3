"""Answer DSO 429 hourly-quiz questions with plain arithmetic.

Each solver computes the expected value; the option closest to it wins.
Questions that match no known type are reported as unknown.
"""
import re
from datetime import datetime, timedelta

NUM = r"(-?[\d,]*\.?\d+)"


def num(s):
    return float(s.replace(",", ""))


def nums(text):
    return [num(m) for m in re.findall(NUM, text)]


# ---------- solvers: each returns the expected value or None ----------

def compound(q):
    m = re.search(r"\$" + NUM + r" grows at " + NUM + r"% compounded annually.*?after " + NUM + r" years", q)
    if m:
        p, r, n = map(num, m.groups())
        return p * (1 + r / 100) ** n


def discount(q):
    m = re.search(r"listed at \$" + NUM + r" is discounted by " + NUM + r"%", q)
    if m:
        p, d = map(num, m.groups())
        return p * (1 - d / 100)


def revenue(q):
    m = re.search(r"sells " + NUM + r" units at \$" + NUM + r" each", q)
    if m:
        u, p = map(num, m.groups())
        return u * p


def fx(q):
    m = re.search(r"\$" + NUM + r" is converted to \w+ at " + NUM + r" \w+ per", q)
    if m:
        a, r = map(num, m.groups())
        return a * r


def weighted_avg(q):
    m = re.findall(NUM + r" orders averaging \$" + NUM, q)
    if len(m) >= 2:
        pairs = [(num(n), num(a)) for n, a in m]
        return sum(n * a for n, a in pairs) / sum(n for n, _ in pairs)


def gross_margin(q):
    m = re.search(r"\$" + NUM + r" in revenue against \$" + NUM + r" in cost of goods sold", q)
    if m:
        rev, cogs = map(num, m.groups())
        return (rev - cogs) / rev * 100


def break_even(q):
    m = re.search(r"Fixed costs are \$" + NUM + r".*?sells for \$" + NUM + r".*?variable cost of \$" + NUM, q)
    if m:
        f, p, v = map(num, m.groups())
        return f / (p - v)


def probability(q):
    if "probability" not in q:
        return None
    counts = {w.lower(): num(n) for n, w in re.findall(NUM + r" (\w+) tickets", q)}
    m = re.search(r"it is an? (\w+) ticket", q)
    if counts and m and m.group(1).lower() in counts:
        return counts[m.group(1).lower()] / sum(counts.values()) * 100


def pct_change(q):
    m = re.search(r"from \$" + NUM + r" to \$" + NUM + r".*percentage change", q)
    if m:
        a, b = map(num, m.groups())
        return (b - a) / a * 100


def ratio_split(q):
    m = re.search(r"\$" + NUM + r" .*?ratio " + NUM + r":" + NUM + r".*?(first|second) channel", q)
    if m:
        total, a, b = map(num, m.groups()[:3])
        share = a if m.group(4) == "first" else b
        return total * share / (a + b)


def series(q):
    m = re.search(r"series runs ([\d,.\s-]+?)\. If the pattern", q)
    if m:
        xs = [num(x) for x in m.group(1).split(",") if x.strip()]
        diffs = {round(b - a, 9) for a, b in zip(xs, xs[1:])}
        if len(diffs) == 1:
            return xs[-1] + diffs.pop()
        if all(x != 0 for x in xs):
            ratios = {round(b / a, 9) for a, b in zip(xs, xs[1:])}
            if len(ratios) == 1:
                return xs[-1] * ratios.pop()
        # second differences (quadratic patterns)
        d = [b - a for a, b in zip(xs, xs[1:])]
        dd = {round(b - a, 9) for a, b in zip(d, d[1:])}
        if len(dd) == 1:
            return xs[-1] + d[-1] + dd.pop()


def settle_date(q):
    m = re.search(r"signed on (\d{1,2} \w+ \d{4}) has an? " + NUM + r"-day", q)
    if m:
        start = datetime.strptime(m.group(1), "%d %B %Y")
        return start + timedelta(days=int(num(m.group(2))))


SOLVERS = [compound, discount, revenue, fx, weighted_avg, gross_margin,
           break_even, probability, pct_change, ratio_split, series, settle_date]


# ---------- option matching ----------

def parse_option(s):
    s = s.strip()
    try:
        return datetime.strptime(s, "%d %B %Y")
    except ValueError:
        pass
    m = re.search(NUM, s.replace("$", ""))
    return num(m.group(1)) if m else None


def solve(question, options):
    """Return (letter, solver_name) or (None, None) if unsolved."""
    for f in SOLVERS:
        try:
            target = f(question)
        except (ValueError, ZeroDivisionError):
            target = None
        if target is None:
            continue
        best, best_d = None, None
        for letter, opt in zip("ABCD", options):
            v = parse_option(opt)
            if v is None or type(v) is not type(target):
                continue
            d = abs((v - target).days) if isinstance(v, datetime) else abs(v - target)
            if best_d is None or d < best_d:
                best, best_d = letter, d
        if best:
            return best, f.__name__
    return None, None
