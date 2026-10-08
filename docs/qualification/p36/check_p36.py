import json
from decimal import Decimal
from pathlib import Path


HERE = Path(__file__).resolve().parent


def load_json(name):
    return json.loads((HERE / name).read_text(encoding="utf-8"))


def decimal_text(value):
    return format(value.normalize(), "f")


def check():
    profile = load_json("qualification.json")
    fixture = load_json("reference_cases.json")
    values = fixture["inputs"]
    expected = fixture["expected"]

    if profile["assessment"] != "UNRESOLVED":
        raise ValueError("P36 must remain unresolved until the listed choices are adopted")
    if fixture["status"] != "ILLUSTRATIVE_UNADOPTED":
        raise ValueError("the mechanics fixture must remain explicitly unadopted")
    if [item["id"] for item in profile["acceptance_checks"]] != [
        "LP-01", "LP-02", "LP-03", "LP-04", "LP-05"
    ]:
        raise ValueError("all five issue acceptance checks must remain mapped in order")
    if set(profile["action_semantics"]) != {"add", "remove", "rebalance", "collect"}:
        raise ValueError("all four LP action meanings must remain explicit")
    if any(not meaning.startswith("UNRESOLVED") for meaning in profile["action_semantics"].values()):
        raise ValueError("no LP action meaning has been adopted for P36")

    initial_base = Decimal(values["initial_base"])
    initial_quote = Decimal(values["initial_quote"])
    if initial_base <= 0 or initial_quote <= 0 or Decimal(values["final_price"]) <= 0:
        raise ValueError("fixture reserves and prices must be positive")
    if initial_quote / initial_base != Decimal(values["initial_price"]):
        raise ValueError("initial reserves must match the fixture's independently declared price")
    final_price = Decimal(values["final_price"])
    invariant = initial_base * initial_quote
    base_end = (invariant / final_price).sqrt()
    quote_end = (invariant * final_price).sqrt()
    lp_inventory = base_end * final_price + quote_end
    comparator = initial_base * final_price + initial_quote
    fees = Decimal(values["fees_collected_quote"])
    gas = Decimal(values["gas_cost_quote"])
    rebalance = Decimal(values["rebalance_cost_quote"])
    actual = {
        "lp_inventory_value": lp_inventory,
        "holding_comparator_value": comparator,
        "gross_fees": fees,
        "impermanent_loss": lp_inventory - comparator,
        "gas_cost": gas,
        "rebalance_cost": rebalance,
        "net_benefit": lp_inventory + fees - gas - rebalance - comparator,
    }

    for name, value in actual.items():
        if value != Decimal(expected[name]):
            raise ValueError(f"fixture {name} was {value}, expected independent literal {expected[name]}")

    return {
        "assessment": profile["assessment"],
        "fixture_status": fixture["status"],
        "reference_case": {
            name: decimal_text(value) for name, value in actual.items()
        },
    }


if __name__ == "__main__":
    print(json.dumps(check(), indent=2, sort_keys=True))
