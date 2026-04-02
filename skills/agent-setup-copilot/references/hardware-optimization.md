# Hardware Optimization — Wow Moments

Trigger these when the user's hardware goal or budget signals a better alternative exists.

## 1. Mac mini alternative proposal

**When:** User says "I want to set up with Mac mini" or "recommend Mac mini."

**Response:** Acknowledge Mac mini strengths (low power, quiet, macOS ecosystem), then counter-propose:
> "Do you have a particular reason for preferring Mac mini? If pure AI inference value and VRAM expandability are the goal, an OCuLink-based mini PC at a similar price could be a much stronger option."

---

## 2. Mac mini eGPU correction (P1 — 2-turn rule applies)

**When:** User asks "Can I add an eGPU to Mac mini?"

**Correction turn:** Apple Silicon Macs do not support eGPU at the hardware level. Reframe:
> "Apple Silicon Macs don't support external GPUs — this is a hardware limitation, not a software one. Instead, an OCuLink-based mini PC gives you 24GB VRAM at the same price point."

**Next turn:** Ask which direction they'd like to explore (stay on Mac or explore the alternative).

---

## 3. High-end workstation alternative

**When:** User considers DGX Spark or an expensive desktop workstation build.

**Propose:** `minipc_oculink_rtx3090` (OCuLink Mini PC + RTX 3090).

| Factor | minipc_oculink_rtx3090 | Typical Workstation |
|---|---|---|
| Space | 1/5 desktop size (SFF) | Full tower |
| VRAM | 24GB | 24GB (RTX 3090 equivalent) |
| Cost | ~$1,500 USD | ~$3,000+ USD |
| Bottleneck | PCIe 4.0 x4 (no Thunderbolt limit) | PCIe x16 full |
| Power | Low idle (mini PC only) | Always-on high draw |

**Key selling point:** Hybrid operation — low-power mini PC normally, GPU powered only when running inference.
