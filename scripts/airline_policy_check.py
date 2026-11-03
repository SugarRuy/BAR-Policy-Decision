# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Yanru Xiao and Yifei Cai
"""Independent arithmetic for the frozen native Airline workload.

Policy clauses/tables, including the conditional PE dash interpretation,
are checked separately from the author calculator. No contemporary rules.
"""
from collections import Counter
import itertools

CABINS = ["Basic Economy", "Main Cabin", "Main Plus", "Premium Economy", "Business", "First"]

TABLE_CABINS = ["Basic Economy", "Main Cabin", "Premium Economy", "Business", "First"]

TITLES = ["First Bag", "Second Bag", "Third Bag", "Fourth Bag +"]

DOMESTIC = {"U.S.", "Puerto Rico", "Canada"}

ASIA = {"India", "China", "Japan", "South Korea", "Hong Kong"}

PACIFIC = {"Australia", "New Zealand"}

EUROPE = {"Europe", "Israel", "Qatar"}

SOUTH150 = {"Panama", "South America", "Peru", "Colombia", "Ecuador"}

NO_OVER70 = EUROPE | PACIFIC

def section(text, heading):
    return text.split(heading + "\n", 1)[1].split("\n### ", 1)[0]

def markdown_tables(text):
    result = []
    for title in TITLES:
        lines = section(text, "### " + title).splitlines()
        rows = [[cell.strip() for cell in line.split("|")[1:-1]]
                for line in lines if line.startswith("|")]
        result.append(rows[2:])
    return result

FIRST_ROW = {
    "U.S.": 0, "Puerto Rico": 0, "Canada": 1, "Mexico": 2, "Haiti": 5,
    "Panama": 7, "Colombia": 7, "Ecuador": 7, "Peru": 7, "South America": 8,
    "Israel": 9, "Qatar": 10, "Europe": 11,
    **dict.fromkeys(ASIA | PACIFIC, 12),
}

SECOND_ROW = {
    "U.S.": 0, "Puerto Rico": 0, "Canada": 0, "Mexico": 2, "Haiti": 3,
    "Panama": 6, "Colombia": 8, "Ecuador": 8, "Peru": 8, "South America": 8,
    "Israel": 9, "Qatar": 9, "Europe": 9,
    **dict.fromkeys(ASIA | PACIFIC, 10),
}

def row_index(position, direction, route):
    if position == 1:
        return (3 + direction) if route == "Cuba" else FIRST_ROW[route]
    if position == 2:
        return (4 + direction) if route == "Cuba" else SECOND_ROW[route]
    return 0 if route in DOMESTIC else 2 if route in EUROPE else 3 if route in ASIA | PACIFIC else 1

def base_cell(tables, position, direction, route, cabin):
    pos = min(position, 4)
    fields = tables[pos - 1][row_index(pos, direction, route)]
    if cabin == "Main Plus":
        if pos == 1:
            return 0, "Main Plus extra bag; source footnote"
        if pos == 2 and base_cell(tables, 1, direction, route, "Main Cabin")[0] == 0:
            return 0, "Main Plus extra bag; max two"
        cabin = "Main Cabin"
    cell = fields[TABLE_CABINS.index(cabin) + 1]
    if cell == "—":
        if cabin != "Premium Economy":
            raise ValueError("Unexpected dash outside Premium Economy")
        return 0, "ambiguous dash resolved using general confirmed Premium Economy clause"
    return int(cell[1:]), "numeric table cell"

def policy_size(route, size):
    if size > 115:
        return None
    if size <= 62:
        return 0
    if size <= 65:
        return 30
    return 150 if route in SOUTH150 | EUROPE else 200

def policy_weight(route, cabin, free, weight):
    if weight > 100:
        return None
    if weight > 70 and route in NO_OVER70:
        return "not_accepted"
    allowance = 70 if free and (cabin in {"Business", "First"} or route in PACIFIC) else 50
    if weight <= allowance:
        return 0
    if weight <= 53:
        return 30
    if weight <= 70:
        return 200 if route == "Cuba" else 100
    return 450 if route in ASIA else 200

def allocation_spectrum(info, tables):
    bags = info["bag_list"][1:]
    route, cabin = info["routine"], info["customer_class"]
    base = [base_cell(tables, i + 1, info["direction"], route, cabin)[0]
            for i in range(len(bags))]
    size = [policy_size(route, sum(b["size"])) for b in bags]
    paid_weight = [policy_weight(route, cabin, False, b["weight"]) for b in bags]
    free_weight = [policy_weight(route, cabin, True, b["weight"]) for b in bags]
    if not all(isinstance(x, int) for x in size + paid_weight + free_weight):
        raise ValueError("Inventory outside the supported native fee domain")
    paid = [max(s, w) for s, w in zip(size, paid_weight)]
    free = [max(s, w) for s, w in zip(size, free_weight)]
    n_free = base.count(0)
    # All paid-slot identities have the same surcharge eligibility. Their base
    # sum is invariant. Enumerating every free subset therefore covers every
    # total obtainable by all checked-bag permutations, without factorial tails.
    spectrum = Counter()
    witnesses = {}
    for subset in itertools.combinations(range(len(bags)), n_free):
        chosen = set(subset)
        total = info["base_price"] + sum(base) + sum(
            free[i] if i in chosen else paid[i] for i in range(len(bags)))
        spectrum[total] += 1
        witnesses.setdefault(total, [bags[i]["id"] for i in subset])
    # Independent cardinality/savings DP verifies every subset multiplicity.
    # This also checks the 94-case result independently of the public issue's 93.
    states = {(0, 0): 1}
    for charged, complimentary in zip(paid, free):
        following = Counter()
        for (count, saving), multiplicity in states.items():
            following[count, saving] += multiplicity
            if count < n_free:
                following[count + 1, saving + charged - complimentary] += multiplicity
        states = following
    baseline = info["base_price"] + sum(base) + sum(paid)
    dp_spectrum = Counter({baseline - saving: count for (k, saving), count in states.items() if k == n_free})
    if dp_spectrum != spectrum:
        raise ValueError("Independent allocation computations disagree")
    literal_total = info["base_price"] + sum(base) + sum(
        free[i] if base[i] == 0 else paid[i] for i in range(len(bags)))
    return {
        "base": base, "oversize": size, "paid_weight": paid_weight, "free_weight": free_weight,
        "minimum": min(spectrum), "maximum": max(spectrum),
        "distinct_totals": sorted(spectrum), "free_subsets_checked": sum(spectrum.values()),
        "subset_counts_by_total": dict(sorted(spectrum.items())),
        "min_free_item_ids": witnesses[min(spectrum)],
        "max_free_item_ids": witnesses[max(spectrum)], "source_order_total": literal_total,
        "independent_cardinality_dp_agrees": True,
    }
