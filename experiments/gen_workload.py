"""Generates RangeReduce-compatible workloads (I/U/S lines) with controllable range-query skew."""
import argparse
import random
import string

ALPHABET = string.ascii_letters + string.digits


def random_keys(n, key_len, rng):
    keys = set()
    while len(keys) < n:
        keys.add("".join(rng.choices(ALPHABET, k=key_len)))
    keys = sorted(keys)  # a set's order changes between Python runs; sort so the seed alone decides the order
    rng.shuffle(keys)
    return keys


def value_source(val_len, rng, pool_size=1 << 22):
    pool = "".join(rng.choices(ALPHABET, k=pool_size))
    limit = pool_size - val_len

    def next_value():
        start = rng.randrange(limit)
        return pool[start:start + val_len]

    return next_value


def hot_centres(pattern, phases):
    if pattern == "shifting":
        return [(i + 1) / (phases + 1) for i in range(phases)]
    return [0.5]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--pattern", choices=["uniform", "hotcold", "shifting"], required=True)
    p.add_argument("-I", "--inserts", type=int, required=True)
    p.add_argument("-U", "--updates", type=int, required=True)
    p.add_argument("-S", "--range_queries", type=int, required=True)
    p.add_argument("-Y", "--selectivity", type=float, required=True)
    p.add_argument("-E", "--entry_size", type=int, default=128)
    p.add_argument("--key_len", type=int, default=16)
    p.add_argument("--hot_frac", type=float, default=0.8)
    p.add_argument("--hot_width", type=float, default=0.05)
    p.add_argument("--phases", type=int, default=3)
    p.add_argument("--seed", type=int, default=2026)
    p.add_argument("-o", "--output", default="workload.txt")
    a = p.parse_args()

    rng = random.Random(a.seed)
    val_len = a.entry_size - a.key_len
    keys = random_keys(a.inserts, a.key_len, rng)
    sorted_keys = sorted(keys)
    n = len(sorted_keys)
    next_value = value_source(val_len, rng)
    centres = hot_centres(a.pattern, a.phases)
    span = a.selectivity

    def range_query(i):
        hot = a.pattern != "uniform" and rng.random() < a.hot_frac
        if hot:
            centre = centres[min(len(centres) - 1, i * len(centres) // a.range_queries)]
            lo = max(0.0, centre - a.hot_width / 2 - span / 2)
            hi = min(1.0 - span, centre + a.hot_width / 2 - span / 2)
            start = rng.uniform(lo, max(lo, hi))
        else:
            start = rng.uniform(0.0, 1.0 - span)
        s = int(start * n)
        e = min(n - 1, s + max(1, int(span * n)))
        return f"S {sorted_keys[s]} {sorted_keys[e]}\n", hot

    ops = ["U"] * a.updates + ["S"] * a.range_queries
    rng.shuffle(ops)

    hot_count = 0
    with open(a.output, "w") as f:
        for k in keys:
            f.write(f"I {k} {next_value()}\n")
        rq_index = 0
        for op in ops:
            if op == "U":
                f.write(f"U {keys[rng.randrange(n)]} {next_value()}\n")
            else:
                line, hot = range_query(rq_index)
                hot_count += hot
                rq_index += 1
                f.write(line)
    print(f"wrote {a.inserts} inserts, {a.updates} updates, {a.range_queries} range queries "
          f"({hot_count} hot) to {a.output}")


if __name__ == "__main__":
    main()
