#!/usr/bin/env python3
"""
API → Local LLM Transition Advisor

Calculates the optimal month to switch from a cloud LLM API to a local setup,
based on current usage cost, projected growth, device lifecycle, and TCO.

Lifecycle model:
  API phase:        pay per token each month (grows with usage)
  Transition month: one-time device purchase
  Local phase:      device amortization + electricity (~$0 per token)
  Payback:          month where cumulative savings exceed device cost

Key formulas:
  api_cost(month) = current_cost × (1 + growth_rate)^month
  device_monthly  = device_price / 24 + electricity_monthly   (2-yr amortization)
  break_even      = first month where api_cost(m) > device_monthly
  optimal_switch  = month that minimizes 2-year TCO

Usage:
  # From monthly bill + growth rate
  python3 copilot/transition.py --api claude-haiku-4-5 --monthly-cost 15 --growth 10

  # From daily token count
  python3 copilot/transition.py --api gpt-4o-mini --tokens-per-day 80000 --growth 15

  # Target a specific device
  python3 copilot/transition.py --api gpt-4o --monthly-cost 50 --growth 20 \\
    --device mac_mini_m4_32gb

  # Compare all viable devices
  python3 copilot/transition.py --api claude-sonnet-4-6 --monthly-cost 100 \\
    --growth 25 --compare-devices
"""

import argparse
import math
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml

# ── Fallback price table (USD, approximate) ────────────────────────────────
# Used when device has no price_usd field. Verify via price_search_query.
DEVICE_PRICES_USD: dict[str, int] = {
    "macbook_air_8gb":          1099,
    "macbook_16gb":             1299,
    "macbook_pro_32gb":         1999,
    "macbook_pro_m4_max_48gb":  3499,
    "mac_mini_16gb":             599,
    "mac_mini_m4_24gb":          799,
    "mac_mini_m4_32gb":          799,
    "mac_mini_pro_48gb":        1799,
    "mac_studio_m4_max_64gb":   1999,
    "mac_studio_m4_max_128gb":  2599,
    "pc_no_gpu":                   0,   # existing PC — GPU add-on only
    "pc_rtx4060":                400,   # GPU cost only
    "pc_rtx4060ti_16gb":         450,
    "pc_rtx4070ti_super_16gb":   800,
    "pc_rtx4090":               1700,
    "pc_rtx5090_32gb":          2100,
    "pc_amd_rx7900xtx":          900,
    "nvidia_dgx_spark":         3000,
}


# Monthly electricity estimate by device type (USD)
ELECTRICITY_USD: dict[str, float] = {
    "macbook":          1.5,    # mostly battery, some plugged inference
    "mac-mini":         3.0,    # low TDP (~20W), always on
    "mac-studio":       8.0,    # higher TDP
    "pc":              15.0,    # mid-range GPU inference ~200-300W average
    "ai-supercomputer": 8.0,    # DGX Spark ~60-100W typical inference
}

# Amortization period (months)
LIFECYCLE_MONTHS = 24

# ── Data types ─────────────────────────────────────────────────────────────

@dataclass
class UsageProfile:
    api_id:        str
    monthly_cost:  float   # USD
    growth_rate:   float   # decimal, e.g. 0.10 for 10%/month

@dataclass
class DeviceOption:
    id:            str
    label:         str
    price_usd:     int
    electricity:   float
    local_model:   str     # recommended local model
    device_type:   str

@dataclass
class TransitionAnalysis:
    device:              DeviceOption
    monthly_device_cost: float      # amortization + electricity
    break_even_month:    int | None # first month API > device cost
    optimal_switch_month: int       # minimizes 2-year TCO
    tco_api_only:        float      # 2-year API-only cost
    tco_with_transition: float      # 2-year cost with switch at optimal month
    total_savings:       float      # tco_api_only - tco_with_transition

# ── Data loading ───────────────────────────────────────────────────────────

def load_ontology() -> dict:
    for path in [
        Path.home() / ".cache" / "agent-setup-copilot" / "ontology.yaml",
        Path(__file__).parent / "bundle" / "ontology.yaml",
    ]:
        if path.exists():
            return yaml.safe_load(path.read_text(encoding="utf-8"))
    raise FileNotFoundError(
        "ontology.yaml not found. Run: python3 copilot/loader.py --update"
    )

# ── Cost functions ─────────────────────────────────────────────────────────

def tokens_to_monthly_cost(tokens_per_day: int, api: dict) -> float:
    """Convert daily token usage to monthly USD cost."""
    monthly = tokens_per_day * 30
    input_t  = monthly * 0.60
    output_t = monthly * 0.40
    price    = api["pricing"]
    return (input_t / 1_000_000 * price["input_per_1m"]
          + output_t / 1_000_000 * price["output_per_1m"])


def api_cost_at_month(initial: float, growth: float, month: int) -> float:
    """Monthly API cost at a given future month (0-indexed)."""
    return initial * ((1 + growth) ** month)


def cumulative_api_cost(initial: float, growth: float, months: int) -> float:
    """Total API spend over N months."""
    return sum(api_cost_at_month(initial, growth, m) for m in range(months))

# ── Device helpers ─────────────────────────────────────────────────────────

def device_monthly_cost(dev: DeviceOption) -> float:
    return dev.price_usd / LIFECYCLE_MONTHS + dev.electricity


def get_device_price(device_id: str, devices: list[dict]) -> int:
    """Look up device price from ontology or fallback table."""
    for d in devices:
        if d["id"] == device_id and "price_usd" in d:
            return int(d["price_usd"])
    return DEVICE_PRICES_USD.get(device_id, 0)


def build_device_option(d: dict, ontology: dict) -> DeviceOption:
    """Build a DeviceOption from an ontology device entry."""
    # Find recommended local model from relations
    local_model = d.get("max_model", "qwen3.5:9b")

    # Try api_to_local_paths in relations for a better match
    rels = _load_relations()
    if rels:
        for path in rels.get("instances", {}).get("api_to_local_paths", []):
            if path.get("min_device") == d["id"] or path.get("recommended_device") == d["id"]:
                local_model = path.get("local_model", local_model)
                break

    devices = ontology.get("devices", []) + ontology.get("additional_devices", [])
    return DeviceOption(
        id          = d["id"],
        label       = d["label"],
        price_usd   = get_device_price(d["id"], devices),
        electricity = ELECTRICITY_USD.get(d.get("type", "pc"), 10.0),
        local_model = local_model,
        device_type = d.get("type", "pc"),
    )


def _load_relations() -> dict:
    for path in [
        Path.home() / ".cache" / "agent-setup-copilot" / "relations.yaml",
        Path(__file__).parent / "bundle" / "relations.yaml",
    ]:
        if path.exists():
            return yaml.safe_load(path.read_text(encoding="utf-8"))
    return {}

# ── Transition analysis ────────────────────────────────────────────────────

def analyze(profile: UsageProfile, device: DeviceOption,
            horizon: int = 24) -> TransitionAnalysis:
    """Full lifecycle analysis for one device option."""
    dev_monthly = device_monthly_cost(device)

    # Break-even: first month where API cost exceeds device monthly cost
    break_even = None
    for m in range(horizon):
        if api_cost_at_month(profile.monthly_cost, profile.growth_rate, m) >= dev_monthly:
            break_even = m
            break

    # TCO: API-only for full horizon
    tco_api = cumulative_api_cost(profile.monthly_cost, profile.growth_rate, horizon)

    # Find optimal switch month (minimizes total cost over horizon)
    best_month = 0
    best_tco   = float("inf")

    for switch_m in range(0, horizon):
        pre  = cumulative_api_cost(profile.monthly_cost, profile.growth_rate, switch_m)
        post = (horizon - switch_m) * dev_monthly
        total = pre + device.price_usd + post
        if total < best_tco:
            best_tco   = total
            best_month = switch_m

    savings = tco_api - best_tco

    return TransitionAnalysis(
        device              = device,
        monthly_device_cost = dev_monthly,
        break_even_month    = break_even,
        optimal_switch_month= best_month,
        tco_api_only        = round(tco_api, 2),
        tco_with_transition = round(best_tco, 2),
        total_savings       = round(savings, 2),
    )

# ── Report builders ────────────────────────────────────────────────────────

def _month_label(m: int) -> str:
    if m == 0:   return "Now"
    if m == 1:   return "Next month"
    if m < 6:    return f"{m} months from now"
    if m < 12:   return f"~{m} months from now"
    return f"~{m//12} year{'s' if m >= 24 else ''} from now"


def _recommendation_badge(a: TransitionAnalysis) -> str:
    s = a.optimal_switch_month
    sav = a.total_savings
    if sav <= 0:             return "⚪ Stay on API — local not cost-effective yet"
    if s == 0:               return "🔴 Switch now — already exceeds break-even"
    if s <= 3:               return "🟠 Switch soon — payback within 3 months"
    if s <= 6:               return "🟡 Consider switching — payback within 6 months"
    if s <= 12:              return "🟢 Plan ahead — payback within a year"
    return "⚪ Stay on API — revisit when usage grows"


def report_single(profile: UsageProfile, api_data: dict,
                  device: DeviceOption, horizon: int = 24) -> str:
    a = analyze(profile, device, horizon)
    lines = [
        f"=== API → Local Transition Analysis ===",
        f"",
        f"API Service  : {api_data['label']}",
        f"Monthly Cost : ${profile.monthly_cost:.2f}",
        f"Growth Rate  : +{profile.growth_rate*100:.0f}%/month",
        f"",
        f"Target Device: {device.label}",
        f"Device Cost  : ~${device.price_usd:,}  (verify: {_price_search(device.device_type)})",
        f"Monthly (amort + electricity): ${a.monthly_device_cost:.2f}/mo",
        f"Local Model  : {device.local_model}",
        f"",
    ]

    # Cost projection table
    lines.append("── Projected API Cost ──────────────────────────")
    for m in range(min(horizon, 24)):
        cost = api_cost_at_month(profile.monthly_cost, profile.growth_rate, m)
        marker = " ← break-even" if m == a.break_even_month else ""
        marker += " ← optimal switch" if m == a.optimal_switch_month and m != a.break_even_month else ""
        if m % 3 == 0 or marker:
            lines.append(f"  Month {m+1:>2}: ${cost:>7.2f}{marker}")

    lines += [
        f"",
        f"── Break-Even ──────────────────────────────────",
    ]
    if a.break_even_month is not None:
        be_cost = api_cost_at_month(profile.monthly_cost, profile.growth_rate, a.break_even_month)
        lines.append(
            f"  Month {a.break_even_month+1}: API cost ${be_cost:.2f} "
            f"> device monthly ${a.monthly_device_cost:.2f}"
        )
    else:
        lines.append(f"  API cost never exceeds device monthly cost in {horizon} months.")

    lines += [
        f"",
        f"── {horizon}-Month TCO Comparison ──────────────────────",
        f"  API-only        : ${a.tco_api_only:,.2f}",
        f"  With transition : ${a.tco_with_transition:,.2f}  (switch at month {a.optimal_switch_month+1})",
        f"  Savings         : ${a.total_savings:,.2f}",
        f"",
        f"── Recommendation ──────────────────────────────",
        f"  {_recommendation_badge(a)}",
    ]

    if a.total_savings > 0:
        lines += [
            f"",
            f"  Optimal switch : {_month_label(a.optimal_switch_month)} (month {a.optimal_switch_month+1})",
            f"  At that point  : API ~${api_cost_at_month(profile.monthly_cost, profile.growth_rate, a.optimal_switch_month):.2f}/mo → $0/token locally",
            f"  Model to run   : {device.local_model}  (same quality tier)",
        ]

    lines.append(f"\n(Prices approximate. Verify with: python3 copilot/loader.py + web search)")
    return "\n".join(lines)


def report_compare(profile: UsageProfile, api_data: dict,
                   devices: list[DeviceOption], horizon: int = 24) -> str:
    analyses = [(d, analyze(profile, d, horizon)) for d in devices]

    lines = [
        f"=== Transition Comparison — {api_data['label']} ===",
        f"",
        f"Current Cost : ${profile.monthly_cost:.2f}/month",
        f"Growth Rate  : +{profile.growth_rate*100:.0f}%/month",
        f"Horizon      : {horizon} months",
        f"",
        f"{'Device':<32} {'Price':>7} {'Mo.Cost':>8} {'Break-even':>12} {'Switch':>7} {'Savings':>9}  Verdict",
        f"{'─'*32} {'─'*7} {'─'*8} {'─'*12} {'─'*7} {'─'*9}  {'─'*25}",
    ]

    for dev, a in sorted(analyses, key=lambda x: -x[1].total_savings):
        be = f"month {a.break_even_month+1}" if a.break_even_month is not None else "> horizon"
        sw = f"mo {a.optimal_switch_month+1}"
        sav = f"${a.total_savings:,.0f}" if a.total_savings > 0 else "-"
        badge = _recommendation_badge(a).split(" ")[0]   # just the emoji
        lines.append(
            f"{dev.label:<32} ${dev.price_usd:>6,} ${a.monthly_device_cost:>7.2f} "
            f"{be:>12} {sw:>7} {sav:>9}  {badge}"
        )

    # Best pick
    best = max(analyses, key=lambda x: x[1].total_savings)
    if best[1].total_savings > 0:
        lines += [
            f"",
            f"Best pick: {best[0].label}",
            f"  Switch at : month {best[1].optimal_switch_month + 1} "
              f"({_month_label(best[1].optimal_switch_month)})",
            f"  Run model : {best[0].local_model}",
            f"  Save      : ${best[1].total_savings:,.2f} over {horizon} months",
        ]
    else:
        lines += [
            f"",
            f"No device is cost-effective within {horizon} months at current usage.",
            f"Revisit if monthly spend grows beyond ${min(d.monthly_device_cost for _, a in analyses):.0f}.",
        ]

    return "\n".join(lines)


def _price_search(device_type: str) -> str:
    searches = {
        "macbook":    "MacBook price apple.com",
        "mac-mini":   "Mac Mini price apple.com",
        "mac-studio": "Mac Studio price apple.com",
        "pc":         "GPU price [component name]",
    }
    return searches.get(device_type, "search for current price")

# ── CLI ────────────────────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser(description="API → Local LLM transition advisor")

    # Usage input
    p.add_argument("--api",            required=True, help="API service ID (e.g. claude-haiku-4-5)")
    p.add_argument("--monthly-cost",   type=float,    help="Current monthly API bill in USD")
    p.add_argument("--tokens-per-day", type=int,      help="Average daily token usage")
    p.add_argument("--growth",         type=float, default=0,
                   help="Monthly usage growth rate in percent (e.g. 10 for 10%%/mo)")

    # Device options
    p.add_argument("--device",          help="Single target device ID")
    p.add_argument("--device-price",    type=int,  help="Override device price in USD")
    p.add_argument("--compare-devices", action="store_true",
                   help="Compare all viable device options")

    # Analysis parameters
    p.add_argument("--horizon", type=int, default=24,
                   help="Analysis horizon in months (default: 24)")

    args = p.parse_args()

    try:
        ont = load_ontology()
    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    # Resolve API service
    api_data = next(
        (a for a in ont.get("api_services", []) if a["id"] == args.api), None
    )
    if not api_data:
        print(f"ERROR: API service '{args.api}' not found.", file=sys.stderr)
        available = [a["id"] for a in ont.get("api_services", [])]
        print(f"Available: {', '.join(available)}", file=sys.stderr)
        sys.exit(1)

    # Resolve monthly cost
    if args.monthly_cost:
        monthly = args.monthly_cost
    elif args.tokens_per_day:
        monthly = tokens_to_monthly_cost(args.tokens_per_day, api_data)
        print(f"Calculated monthly cost from {args.tokens_per_day:,} tokens/day: ${monthly:.2f}\n")
    else:
        p.error("Provide --monthly-cost or --tokens-per-day")

    profile = UsageProfile(
        api_id       = args.api,
        monthly_cost = monthly,
        growth_rate  = args.growth / 100.0,
    )

    all_devs = ont.get("devices", []) + ont.get("additional_devices", [])

    if args.compare_devices:
        # Filter to devices with known prices and above zero
        options = []
        for d in all_devs:
            if d.get("type") == "pc" and d.get("gpu_vram_gb", 0) == 0:
                continue   # skip CPU-only PC
            opt = build_device_option(d, ont)
            if opt.price_usd > 0:
                options.append(opt)
        print(report_compare(profile, api_data, options, args.horizon))

    elif args.device:
        d = next((x for x in all_devs if x["id"] == args.device), None)
        if not d:
            print(f"ERROR: Device '{args.device}' not found.", file=sys.stderr)
            sys.exit(1)
        opt = build_device_option(d, ont)
        if args.device_price:
            opt.price_usd = args.device_price
        print(report_single(profile, api_data, opt, args.horizon))

    else:
        # Auto-recommend: use api_to_local_paths from relations
        rels = _load_relations()
        rec_device_id = None
        for path in rels.get("instances", {}).get("api_to_local_paths", []):
            if path.get("from_api") == args.api:
                rec_device_id = path.get("recommended_device")
                break

        if rec_device_id:
            d = next((x for x in all_devs if x["id"] == rec_device_id), None)
            if d:
                opt = build_device_option(d, ont)
                print(report_single(profile, api_data, opt, args.horizon))
                return

        # Fallback: compare all
        options = [build_device_option(d, ont) for d in all_devs
                   if get_device_price(d["id"], all_devs) > 0]
        print(report_compare(profile, api_data, options, args.horizon))


if __name__ == "__main__":
    main()
