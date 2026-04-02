# Cloud Deployment Reference

## deployment_target detection

| Keyword | deployment_target |
|---|---|
| EC2, S3, SageMaker, AWS | aws |
| RunPod, Pod, GPU rental | runpod |
| Azure, OpenAI Service, network isolation | azure |
| "cloud", "rent a server" | ask once: "Which cloud platform are you thinking of?" |
| none / "my computer" | local |

---

## AWS (primary type: Builder)

```
Recommended path:
  1. EC2 (g4dn / g5) + Ollama + Docker
     - AMI: Deep Learning Base (Ubuntu 22.04)
     - Architecture note: g4dn=x86_64, Graviton (m7g etc.)=ARM — different Ollama binaries
     - Security Group: restrict port 11434 (Ollama) inbound (no 0.0.0.0)
     - Cost optimization: Spot Instances (up to 70% off On-Demand)
  2. SageMaker correction required:
     - SageMaker ≠ Ollama hosting — it's for training/inference pipelines
     - EC2 is the right fit for running Ollama directly
  3. Instances not in estimator.py: g4dn.xlarge (16GB VRAM), g5.xlarge (24GB VRAM)
     → State directly: "Estimated ~X t/s for 7B model on g4dn.xlarge"
```

---

## RunPod (primary type: Optimizer)

```
Recommended path:
  1. Secure Cloud vs Community Cloud:
     - Secure Cloud: dedicated hardware, data isolation guarantee — sensitive data / enterprise
     - Community Cloud: shared environment, lower cost — experiments / personal projects
  2. Network Volume: required for checkpoint persistence (local storage deleted when Pod stops)
  3. QLoRA fine-tuning: A100 40GB+ recommended (80GB minimum for 70B)
  4. deo_resolver.py: if data security constraint → include Secure Cloud only
```

---

## Azure (primary type: Decider)

```
2×2 matrix (security compliance × implementation complexity):

  High security / High complexity:  Azure OpenAI + Private Endpoint + APIM + Azure AI Search
  High security / Low complexity:   Azure OpenAI + Managed VNet + Customer-Managed Keys
  Low security  / Low complexity:   Azure OpenAI standard (public/education use)
  Low security  / High complexity:  N/A (not recommended)

Required correction:
  Azure OpenAI ≠ OpenAI API — isolated instance, prompts not used for model training
  (Microsoft Data, Privacy, Security commitments)

On detection of financial/government regulation keywords:
  - Korea Central region enforcement (Azure Policy)
  - Private Endpoint (block internet exposure)
  - Microsoft Purview audit logs (data retention compliance)
  - Customer-Managed Keys (CMK) encryption
```

---

## Common: deo_resolver.py for cloud constraints

```bash
# Network isolation / data isolation constraint
python3 skills/agent-setup-copilot/script/deo_resolver.py \
  --json '{"positive":["cloud_deployment","rag"],"negative":["internet_exposure"],"constraints":{"hard":["data_isolation"],"soft":["korea_region"]}}'
```
