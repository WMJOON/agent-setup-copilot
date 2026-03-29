#!/usr/bin/env python3
"""
Performance Estimator — estimates LLM inference speed and use-case suitability.

All estimates are approximate (±25%). Real-world speed depends on
quantization method, context length, concurrent requests, and hardware state.

Formulas:
  Dense model:  t/s ≈ bandwidth_gbs / (params_b × BYTES_PER_PARAM)
  MoE model:    t/s ≈ bandwidth_gbs / (active_params_b × MOE_FACTOR × BYTES_PER_PARAM)

  BYTES_PER_PARAM = 0.5625  (Q4_K_M ≈ 4.5 bits/param ÷ 8)
  MOE_FACTOR      = 3.5     (empirical: attention layers + routing overhead)

  Model memory:  params_b × 0.5625 GB  (Q4_K_M)
  KV cache:      ~0.5-2 GB extra (8K context)

Usage:
  python3 copilot/estimator.py --device mac_mini_m4_32gb --model qwen3.5:35b-a3b
  python3 copilot/estimator.py --gpu rtx-4090 --ram-gb 64 --model qwen3.5:27b
  python3 copilot/estimator.py --device mac_mini_m4_32gb --compare-models
  python3 copilot/estimator.py --model qwen3.5:9b --compare-devices
  python3 copilot/estimator.py --gpu rtx-4090 --ram-gb 64 --use-cases all
"""

import argparse
import sys
from pathlib import Path

import yaml

# ── Constants ──────────────────────────────────────────────────────────────

BYTES_PER_PARAM = 0.5625   # Q4_K_M: 4.5 bits/param ÷ 8
MOE_FACTOR      = 3.5      # attention + routing overhead multiplier
KV_CACHE_GB     = 1.0      # approximate KV cache at 8K context
VRAM_HEADROOM   = 1.15     # 15% overhead buffer

# Tokens-per-second thresholds
TPS_UNUSABLE    = 3
TPS_SLOW        = 8
TPS_USABLE      = 15
TPS_GOOD        = 25
TPS_EXCELLENT   = 50

# ── Data loading ───────────────────────────────────────────────────────────

_INSTANCE_ENTITIES = [
    "use_case", "device", "model", "framework",
    "api_service", "component", "repo", "setup_profile",
]

_SECTION_MAP = {
    "use_case": "use_cases", "device": "devices", "model": "models",
    "framework": "frameworks", "api_service": "api_services",
    "component": "components", "repo": "repos", "setup_profile": "setup_profiles",
}


def _read_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _load_instance(entity: str) -> list:
    """Load one entity list from cache or bundle."""
    fname = f"instances/{entity}.yaml"
    for base in [
        Path.home() / ".cache" / "agent-setup-copilot",
        Path(__file__).parent / "bundle",
    ]:
        path = base / fname
        if path.exists():
            data = _read_yaml(path)
            section = _SECTION_MAP[entity]
            # file may wrap list under plural key
            return (data.get(section) or data.get(f"{entity}s") or []) if data else []
    return []


def load_ontology() -> dict:
    """Assemble flat ontology dict from per-entity instance files."""
    onto: dict = {}
    for entity in _INSTANCE_ENTITIES:
        section = _SECTION_MAP[entity]
        items = _load_instance(entity)
        if items:
            onto[section] = items
    if not onto:
        raise FileNotFoundError(
            "No ontology data found. Run: "
            "python3 skills/agent-setup-copilot/script/loader.py --update"
        )
    return onto

# ── Core estimation functions ──────────────────────────────────────────────

def effective_params(model: dict) -> float:
    """Return the effective parameter count for bandwidth calculation."""
    if model.get("type") == "MoE":
        active = model.get("active_params_b", model["params_b"] * 0.1)
        return active * MOE_FACTOR
    return model["params_b"]


def model_size_gb(model: dict) -> float:
    """Disk/VRAM footprint for Q4_K_M quantization."""
    return model["params_b"] * BYTES_PER_PARAM


def estimate_tps(bandwidth_gbs: float, model: dict) -> float:
    """Estimate tokens/second given memory bandwidth and model."""
    eff = effective_params(model)
    if eff <= 0:
        return 0.0
    return round(bandwidth_gbs / (eff * BYTES_PER_PARAM), 1)


def fits_in_memory(available_gb: float, model: dict) -> tuple[bool, float, float]:
    """
    Returns (fits, model_gb, required_gb).
    required_gb includes model + KV cache + overhead.
    """
    m_gb = model_size_gb(model)
    required = m_gb * VRAM_HEADROOM + KV_CACHE_GB
    return required <= available_gb, round(m_gb, 1), round(required, 1)


def tps_label(tps: float) -> str:
    if tps < TPS_UNUSABLE:  return "❌ Too slow for interactive use"
    if tps < TPS_SLOW:      return "⚠️  Slow — batch tasks only"
    if tps < TPS_USABLE:    return "△  Usable — some wait time"
    if tps < TPS_GOOD:      return "✅ Good"
    if tps < TPS_EXCELLENT: return "✅ Fast"
    return "✅ Excellent"


def use_case_suitability(tps: float, model_quality: str, uc: dict) -> str:
    """Rate suitability of a setup for a use case."""
    # Memory already checked upstream; here we check quality and speed
    min_mem = uc.get("min_memory_gb", 0)
    quality_rank = {"light": 0, "standard": 1, "standard-plus": 2, "pro": 3}
    quality_needed = _min_quality_for_use_case(uc["id"])
    has_quality = quality_rank.get(model_quality, 0) >= quality_rank.get(quality_needed, 0)

    if not has_quality:
        return f"△  Model quality ({model_quality}) below recommended ({quality_needed})"
    if tps < TPS_UNUSABLE:
        return "❌ Too slow"
    if tps < TPS_SLOW:
        return "⚠️  Very slow — suitable for offline batch only"
    if tps < TPS_USABLE:
        return "△  Usable with patience"
    if tps < TPS_GOOD:
        return "✅ Good"
    return "✅ Excellent"


def _min_quality_for_use_case(uc_id: str) -> str:
    """Minimum model quality recommended per use case."""
    pro_cases = {"agent_monitoring", "multi_agent", "code_review", "deep_research"}
    std_plus   = {"code_generation", "document_rag", "web_research", "fine_tuning"}
    if uc_id in pro_cases:    return "pro"
    if uc_id in std_plus:     return "standard-plus"
    return "standard"

# ── Spec resolvers ─────────────────────────────────────────────────────────

def resolve_device_spec(device_id: str, ontology: dict) -> dict | None:
    """Return bandwidth and memory for a device."""
    devices = ontology.get("devices", []) + ontology.get("additional_devices", [])
    for d in devices:
        if d["id"] == device_id:
            return {
                "label":     d["label"],
                "bandwidth": d.get("memory_bandwidth_gbs", 50),   # PC default
                "memory_gb": d.get("memory_gb", 0),
                "vram_gb":   d.get("gpu_vram_gb", 0),
                "kind":      "apple" if d["type"] != "pc" else "pc",
            }
    return None


def resolve_gpu_spec(gpu_id: str, ontology: dict) -> dict | None:
    for c in ontology.get("components", []):
        if c["id"] == gpu_id and c["component_type"] == "gpu":
            return {
                "label":     c["label"],
                "bandwidth": c.get("memory_bandwidth_gbs", 0),
                "vram_gb":   c.get("vram_gb", 0),
            }
    return None


def resolve_model(model_id: str, ontology: dict) -> dict | None:
    for m in ontology.get("models", []):
        if m["id"] == model_id:
            return m
    return None

# ── Report builders ────────────────────────────────────────────────────────

def report_device_model(device_id: str, model_id: str, ontology: dict) -> str:
    spec  = resolve_device_spec(device_id, ontology)
    model = resolve_model(model_id, ontology)

    if not spec:
        return f"Device '{device_id}' not found in ontology."
    if not model:
        return f"Model '{model_id}' not found in ontology."

    # Apple Silicon: model must fit in unified memory
    if spec["kind"] == "apple":
        avail = spec["memory_gb"]
        infer_bw = spec["bandwidth"]
    else:
        # PC: check GPU VRAM first, then CPU fallback
        avail    = spec["vram_gb"]
        infer_bw = spec.get("bandwidth", 50)  # GPU bandwidth when fits

    fits, m_gb, req_gb = fits_in_memory(avail, model)
    tps = estimate_tps(infer_bw, model) if fits else estimate_tps(30.0, model)
    # CPU fallback when doesn't fit: rough 30 GB/s DDR5 bandwidth

    lines = [
        f"=== Performance Estimate ===",
        f"",
        f"Setup   : {spec['label']}",
        f"Model   : {model['label']}  [{model['type']}, {model['params_b']}B params]",
        f"",
        f"── Memory ──────────────────────────────────",
        f"  Model size (Q4_K_M) : {m_gb:.1f} GB",
        f"  Required (+ overhead): {req_gb:.1f} GB",
        f"  Available            : {avail:.0f} GB",
    ]

    if fits:
        lines.append(f"  Status               : ✅ Fits comfortably")
    else:
        lines.append(f"  Status               : ⚠️  Exceeds memory — CPU offload / swap")
        lines.append(f"  (Falling back to CPU bandwidth estimate ~30 GB/s)")

    lines += [
        f"",
        f"── Speed ───────────────────────────────────",
        f"  Estimated t/s  : ~{tps} tokens/second",
        f"  Rating         : {tps_label(tps)}",
    ]

    if model.get("type") == "MoE":
        lines.append(
            f"  Note (MoE)     : active {model.get('active_params_b')}B params × {MOE_FACTOR} overhead factor"
        )

    lines += ["", "── Use Case Suitability ─────────────────────"]
    for uc in ontology.get("use_cases", []):
        rating = use_case_suitability(tps, model["quality"], uc)
        lines.append(f"  {uc['id']:<22} {rating}")

    lines += ["", f"(Estimates ±25%. Assumes Q4_K_M quantization, 8K context.)"]
    return "\n".join(lines)


def report_gpu_model(gpu_id: str, ram_gb: int, model_id: str, ontology: dict) -> str:
    gpu   = resolve_gpu_spec(gpu_id, ontology)
    model = resolve_model(model_id, ontology)

    if not gpu:
        return f"GPU '{gpu_id}' not found in components."
    if not model:
        return f"Model '{model_id}' not found in models."

    fits, m_gb, req_gb = fits_in_memory(gpu["vram_gb"], model)

    if fits:
        bw  = gpu["bandwidth"]
        src = "GPU VRAM"
    else:
        bw  = 50.0  # typical DDR5 system RAM bandwidth
        src = f"CPU RAM (spillover — GPU VRAM {gpu['vram_gb']}GB < {req_gb:.1f}GB needed)"

    tps = estimate_tps(bw, model)

    lines = [
        f"=== Performance Estimate (PC Build) ===",
        f"",
        f"GPU     : {gpu['label']}  [{gpu['vram_gb']}GB VRAM, {gpu['bandwidth']} GB/s]",
        f"RAM     : {ram_gb}GB system RAM",
        f"Model   : {model['label']}  [{model['type']}, {model['params_b']}B params]",
        f"",
        f"── Memory ──────────────────────────────────",
        f"  Model size (Q4_K_M) : {m_gb:.1f} GB",
        f"  Required (+ overhead): {req_gb:.1f} GB",
        f"  GPU VRAM             : {gpu['vram_gb']} GB",
        f"  Inference path       : {src}",
        f"",
        f"── Speed ───────────────────────────────────",
        f"  Bandwidth used : {bw} GB/s",
        f"  Estimated t/s  : ~{tps} tokens/second",
        f"  Rating         : {tps_label(tps)}",
    ]

    if not fits:
        lines.append(
            f"  ⚠️  Upgrade to a GPU with ≥{req_gb:.0f}GB VRAM for full speed."
        )

    lines += ["", "── Use Case Suitability ─────────────────────"]
    for uc in ontology.get("use_cases", []):
        rating = use_case_suitability(tps, model["quality"], uc)
        lines.append(f"  {uc['id']:<22} {rating}")

    lines += ["", "(Estimates ±25%. Assumes Q4_K_M quantization, 8K context.)"]
    return "\n".join(lines)


def report_compare_models(device_id: str, ontology: dict) -> str:
    spec = resolve_device_spec(device_id, ontology)
    if not spec:
        return f"Device '{device_id}' not found."

    avail = spec["memory_gb"] if spec["kind"] == "apple" else spec["vram_gb"]
    bw    = spec["bandwidth"]

    lines = [
        f"=== Model Comparison — {spec['label']} ===",
        f"Memory: {avail}GB  |  Bandwidth: {bw} GB/s",
        f"",
        f"{'Model':<22} {'Params':>8} {'Size(GB)':>10} {'Fits':>6} {'t/s':>7}  {'Rating'}",
        f"{'─'*22} {'─'*8} {'─'*10} {'─'*6} {'─'*7}  {'─'*20}",
    ]

    for m in ontology.get("models", []):
        m_gb   = model_size_gb(m)
        req_gb = m_gb * VRAM_HEADROOM + KV_CACHE_GB
        fits   = req_gb <= avail
        tps    = estimate_tps(bw if fits else 30.0, m)
        fit_s  = "✅" if fits else "⚠️ "
        lines.append(
            f"{m['id']:<22} {m['params_b']:>7}B {m_gb:>9.1f} {fit_s:>6} {tps:>6}  {tps_label(tps)}"
        )

    lines.append("\n(⚠️  = exceeds memory, falls back to ~30 GB/s CPU estimate)")
    return "\n".join(lines)


def report_compare_devices(model_id: str, ontology: dict) -> str:
    model = resolve_model(model_id, ontology)
    if not model:
        return f"Model '{model_id}' not found."

    lines = [
        f"=== Device Comparison — {model['label']} ===",
        f"",
        f"{'Device':<32} {'Mem':>5} {'BW':>7} {'Fits':>6} {'t/s':>7}  {'Rating'}",
        f"{'─'*32} {'─'*5} {'─'*7} {'─'*6} {'─'*7}  {'─'*20}",
    ]

    all_devices = ontology.get("devices", []) + ontology.get("additional_devices", [])
    for d in all_devices:
        avail = d.get("memory_gb", 0) if d.get("type") != "pc" else d.get("gpu_vram_gb", 0)
        bw    = d.get("memory_bandwidth_gbs", 50)
        _, m_gb, req_gb = fits_in_memory(avail, model)
        fits   = req_gb <= avail
        tps    = estimate_tps(bw if fits else 30.0, model)
        fit_s  = "✅" if fits else "⚠️ "
        lines.append(
            f"{d['id']:<32} {avail:>4}G {bw:>6}  {fit_s:>6} {tps:>6}  {tps_label(tps)}"
        )

    return "\n".join(lines)

# ── CLI ────────────────────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser(description="LLM performance estimator")

    p.add_argument("--device",          help="Device ID (e.g. mac_mini_m4_32gb)")
    p.add_argument("--gpu",             help="GPU component ID (e.g. rtx-4090)")
    p.add_argument("--ram-gb", type=int, default=32, help="System RAM in GB (PC builds)")
    p.add_argument("--model",           help="Model ID (e.g. qwen3.5:9b)")
    p.add_argument("--compare-models",  action="store_true",
                   help="Compare all models on the given device")
    p.add_argument("--compare-devices", action="store_true",
                   help="Compare all devices for the given model")

    args = p.parse_args()

    try:
        ont = load_ontology()
    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    if args.compare_models and args.device:
        print(report_compare_models(args.device, ont))
    elif args.compare_devices and args.model:
        print(report_compare_devices(args.model, ont))
    elif args.device and args.model:
        print(report_device_model(args.device, args.model, ont))
    elif args.gpu and args.model:
        print(report_gpu_model(args.gpu, args.ram_gb, args.model, ont))
    else:
        p.print_help()
        print("\nExamples:")
        print("  python3 copilot/estimator.py --device mac_mini_m4_32gb --model qwen3.5:35b-a3b")
        print("  python3 copilot/estimator.py --gpu rtx-4090 --ram-gb 64 --model qwen3.5:27b")
        print("  python3 copilot/estimator.py --device mac_mini_m4_32gb --compare-models")
        print("  python3 copilot/estimator.py --model qwen3.5:9b --compare-devices")


if __name__ == "__main__":
    main()
