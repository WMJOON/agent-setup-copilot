---
name: agent-setup-copilot
description: >
  로컬 AI Agent 환경설정 상담 코파일럿.
  사용자의 목적·장비·예산에 맞는 디바이스·모델·프레임워크 스택을 추천한다.
  온톨로지(agent-setup-ontology)를 SOT로 참조해 추론하며,
  API 키나 별도 설치 없이 Claude Code만으로 동작한다.
  트리거 예시: "어떤 장비 사야 해", "OpenClaw 쓰려면", "qwen3.5 추천",
  "로컬 Agent 시작하고 싶어", "내 맥북으로 뭘 할 수 있어",
  "agent-copilot", "agent setup", "로컬 AI 추천".
---

# agent-setup-copilot

로컬 AI Agent 환경설정 상담 코파일럿.
**Claude Code 자체가 LLM** — Ollama나 API 키 없이 동작한다.

## 스크립트

```
copilot/
├── loader.py      # ontology + concepts + relations fetch → stdout
├── estimator.py   # 성능 추산: t/s 계산, 메모리 적합 여부, use-case 적합도
└── transition.py  # API → 로컬 전환 시점 분석: 비용 성장, 손익분기, 최적 전환 월
```

---

## 워크플로우

### 1단계 — 온톨로지 + 컨셉 로드

```bash
python3 copilot/loader.py
```

`agent-setup-ontology`의 `ontology.yaml`(인스턴스)과 `concepts.yaml`(의미 정의)을
GitHub raw에서 fetch해 stdout에 출력한다.
실패 시 `copilot/bundle/`의 fallback 사용.

출력 구조:
```
# === ONTOLOGY ===   ← 디바이스·모델·프레임워크·use_case 인스턴스
# === CONCEPTS ===   ← tier/quality/kind/runtime 등의 의미 정의
```

### 2단계 — 추론

로드된 온톨로지를 컨텍스트로 삼아 사용자 질문에 답한다.

**파악할 것:**
1. 보유 장비 (없으면 구매 예정 여부)
2. 원하는 사용 목적 (use_case taxonomy 매핑)
3. 예산·제약 조건
4. 현재 API 사용량 (있다면 — 전환 시점 추천에 활용)

**응답 형식:**
- 추천 스택 (디바이스 or 컴포넌트 + 모델 + 프레임워크)
- 추천 이유 (한두 문장)
- 설치 명령어 (`ollama pull ...`)
- 시작 코드 10줄 이내
- 업그레이드 경로 (있다면)

### 2-b단계 — 성능 추산 (필요 시)

사용자가 성능을 묻거나, 디바이스·컴포넌트 추천 전 검증이 필요할 때 실행.

```bash
# 완성품 디바이스 + 모델 조합
python3 copilot/estimator.py --device mac_mini_m4_32gb --model qwen3.5:35b-a3b

# PC 빌드: GPU + RAM + 모델
python3 copilot/estimator.py --gpu rtx-4090 --ram-gb 64 --model qwen3.5:27b

# 특정 디바이스에서 모든 모델 비교
python3 copilot/estimator.py --device mac_mini_m4_32gb --compare-models

# 특정 모델을 모든 디바이스에서 비교
python3 copilot/estimator.py --model qwen3.5:9b --compare-devices
```

출력 예시:
```
=== Performance Estimate ===
Setup   : Mac Mini M4 32GB
Model   : qwen3.5:35b-a3b  [MoE, 35B params]

── Memory ──────────────────────────────────
  Model size (Q4_K_M) : 19.7 GB
  Required (+ overhead): 23.7 GB
  Available            : 32 GB
  Status               : ✅ Fits comfortably

── Speed ───────────────────────────────────
  Estimated t/s  : ~20.4 tokens/second
  Rating         : ✅ Good

── Use Case Suitability ─────────────────────
  web_automation         ✅ Excellent
  code_generation        ✅ Excellent
  agent_monitoring       ✅ Good
  fine_tuning            △  Model quality (pro) below recommended ...
```

### 2-c단계 — 전환 시점 분석 (사용량 정보 제공 시)

사용자가 현재 API 비용이나 토큰 사용량을 알려주면 전환 시점을 계산한다.

```bash
# 월 비용 + 성장률로 분석
python3 copilot/transition.py --api claude-haiku-4-5 --monthly-cost 15 --growth 10

# 일 토큰 수로 계산
python3 copilot/transition.py --api gpt-4o-mini --tokens-per-day 80000 --growth 15

# 특정 디바이스와 비교
python3 copilot/transition.py --api gpt-4o --monthly-cost 50 --growth 20 \
  --device mac_mini_m4_32gb

# 모든 디바이스 비교표
python3 copilot/transition.py --api claude-sonnet-4-6 --monthly-cost 100 \
  --growth 25 --compare-devices
```

출력 예시 (`--compare-devices`):
```
Device                         Price  Mo.Cost   Break-even  Switch  Savings  Verdict
Mac Mini M4 32GB               $799   $36.29     month 4    mo 3    $251     🟠
Mac Mini M4 16GB               $599   $27.96     month 2    mo 2    $217     🟠
Mac Mini M4 Pro 48GB          $1,799  $78.96    > horizon   mo 6     $89     🟢
```

### 2-d단계 — 가격 조회 (필요 시)

온톨로지의 `price_search_query` 필드를 사용해 **웹 검색**으로 현재 가격을 가져온다.
가격은 온톨로지에 하드코딩하지 않는다 — 자주 변하기 때문.

```
예시:
component.price_search_query: "NVIDIA RTX 4090 24GB GPU price"
→ 웹 검색 실행 → 현재 시세 응답에 포함

device.price_search_query: "Mac Mini M4 32GB price"
→ 웹 검색 실행 → Apple Store 또는 리셀러 현재가 응답에 포함
```

PC 빌드 견적 요청 시 GPU + RAM `price_search_query`를 합산해 총 비용 추정.

---

## 온톨로지 SOT

```
https://github.com/WMJOON/agent-setup-ontology
```

온톨로지 업데이트:
```bash
python3 copilot/loader.py --update
```

---

## Claude 사용 가이드

```
"맥미니 M4 32GB로 OpenClaw 쓰고 싶어"
→ loader.py 실행 → 온톨로지 로드 → 디바이스+use_case 매핑 → 추천

"qwen3.5:35b-a3b 랑 27b 중에 뭐가 빨라?"
→ estimator.py --device mac_mini_m4_32gb --compare-models 실행 → 속도 비교

"RTX 4090에서 27B 모델 얼마나 빠를까?"
→ estimator.py --gpu rtx-4090 --ram-gb 64 --model qwen3.5:27b 실행

"내 맥북 16GB에서 어떤 모델까지 쓸 수 있어?"
→ estimator.py --device macbook_16gb --compare-models 실행

"RTX 4060 Ti 16GB 지금 얼마야?"
→ component.price_search_query "NVIDIA RTX 4060 Ti 16GB price" 웹 검색

"50만원 이하로 시작하려면?"
→ devices + components price_range 필터링 → 최저 비용 조합 추천

"Claude Haiku 한 달 $15 쓰는데 언제 맥미니 사면 이득이야?"
→ transition.py --api claude-haiku-4-5 --monthly-cost 15 --growth 10 실행
→ 손익분기 월 + 최적 전환 시점 + 2년 TCO 비교 출력

"사용량이 매달 20%씩 늘고 있어. 언제 로컬로 바꿔야 해?"
→ transition.py --api [현재 API] --monthly-cost [비용] --growth 20 --compare-devices 실행

"지금 GPT-4o 하루 50만 토큰 쓰는데 RTX 4090 사면 이득이야?"
→ transition.py --api gpt-4o --tokens-per-day 500000 --device pc_rtx4090 실행

"맥미니 + DGX Spark 조합으로 세팅하면 어때?"
→ setup_profiles에서 setup-mac-mini-dgx-hybrid 로드 → 역할 분리 + 세팅 명령어 제공

"OpenClaw 써보고 싶은데 어떻게 세팅해?"
→ repos에서 repo-openclaw 로드 → install steps + 최소 모델 요구사항 안내

"DGX Spark 뭐야? LLM에 좋아?"
→ devices에서 nvidia_dgx_spark 로드 → Grace Blackwell, 128GB, 72B 모델 가능 설명
```
