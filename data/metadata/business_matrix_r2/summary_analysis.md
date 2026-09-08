# Business-matrix audit (analysis) — 2026-09-08T16:59:46.471429+00:00

**Verdict:** PASS — 29/29 checks passed, 0 warnings

| Result | Check | Detail |
|---|---|---|
| PASS | matrix: copilot_reply differs across businesses (max pair jaccard 0.17 = POLL/TUITION, mean 0.05, threshold 0.35) |  |
| PASS | matrix: no two businesses got an identical copilot_reply | [] |
| PASS | matrix: roles differs across businesses (max pair jaccard 0.14 = ELDER/KITCHEN, mean 0.07, threshold 0.3) |  |
| PASS | matrix: no two businesses got an identical roles | [] |
| PASS | matrix: persona_descriptions differs across businesses (max pair jaccard 0.15 = SAVINGS/TUITION, mean 0.05, threshold 0.35) |  |
| PASS | matrix: no two businesses got an identical persona_descriptions | [] |
| PASS | matrix: persona_attributes differs across businesses (max pair jaccard 0.13 = SAVINGS/TUITION, mean 0.07, threshold 0.35) |  |
| PASS | matrix: no two businesses got an identical persona_attributes | [] |
| PASS | matrix: script differs across businesses (max pair jaccard 0.07 = KETTLE/POLL, mean 0.04, threshold 0.3) |  |
| PASS | matrix: no two businesses got an identical script | [] |
| PASS | matrix: ai_review differs across businesses (max pair jaccard 0.45 = DERM/TUITION, mean 0.20, threshold 0.45) |  |
| PASS | matrix: no two businesses got an identical ai_review | [] |
| PASS | matrix: no boilerplate 8-grams repeated across ≥3 businesses in copilot_reply |  |
| PASS | matrix: no boilerplate 6-grams repeated across ≥3 businesses in roles |  |
| PASS | matrix: no boilerplate 6-grams repeated across ≥3 businesses in persona_descriptions |  |
| PASS | matrix: no boilerplate 6-grams repeated across ≥3 businesses in persona_attributes |  |
| PASS | matrix: no boilerplate 8-grams repeated across ≥3 businesses in script |  |
| PASS | matrix: no boilerplate 8-grams repeated across ≥3 businesses in interview_answers |  |
| PASS | matrix: no boilerplate 6-grams repeated across ≥3 businesses in behavioral_rationale |  |
| PASS | matrix: no boilerplate 6-grams repeated across ≥3 businesses in report_summary |  |
| PASS | matrix: no boilerplate 6-grams repeated across ≥3 businesses in report_findings |  |
| PASS | matrix: no boilerplate 6-grams repeated across ≥3 businesses in report_recommendations |  |
| PASS | matrix: no boilerplate 6-grams repeated across ≥3 businesses in ai_review |  |
| PASS | matrix: no persona name is reused across businesses | {} |
| PASS | matrix: no business's distinctive vocabulary leaked into another's artefacts | [] |
| PASS | matrix: pollution vs food business share no role names | set() |
| PASS | matrix: pollution vs food business share no persona occupations | set() |
| PASS | matrix: no role name appears in EVERY business (would be a fixed list) | set() |
| PASS | matrix: AI review scores are not one constant | [20, 60, 0, 0, 20] |

## Structure per business

| Business | roles | findings | recs | review | routes |
|---|---|---|---|---|---|
| DERM | 10 | 0 | 0 | 20 | {'copilot': 'ollama/llama3.2:3b', 'personas': ['ollama/llama3.2:3b'], 'ai_review': 'ollama/llama3.2:3b'} |
| ELDER | 10 | 3 | 3 | 60 | {'copilot': 'ollama/llama3.2:3b', 'personas': ['kilo/openrouter/free'], 'script': 'ollama/llama3.2:3b', 'interview': ['o |
| KETTLE | 10 | 0 | 0 | 0 | {'copilot': 'ollama/llama3.2:3b', 'personas': ['ollama/llama3.2:3b'], 'script': 'ollama/llama3.2:3b', 'ai_review': 'olla |
| KITCHEN | 10 | 0 | 0 | None | {'copilot': 'ollama/llama3.2:3b', 'personas': ['ollama/llama3.2:3b'], 'script': 'ollama/llama3.2:3b'} |
| POLL | 9 | 0 | 0 | None | {'copilot': 'ollama/llama3.2:3b', 'personas': ['ollama/llama3.2:3b'], 'script': 'ollama/llama3.2:3b'} |
| SAAS | 10 | 0 | 0 | None | {'copilot': 'ollama/llama3.2:3b', 'personas': ['ollama/llama3.2:3b']} |
| SAVINGS | 9 | 0 | 0 | 0 | {'copilot': 'ollama/llama3.2:3b', 'personas': ['ollama/llama3.2:3b'], 'script': 'ollama/llama3.2:3b', 'ai_review': 'olla |
| TUITION | 8 | 0 | 0 | 20 | {'copilot': 'ollama/llama3.2:3b', 'personas': ['ollama/llama3.2:3b'], 'script': 'ollama/llama3.2:3b', 'ai_review': 'olla |

## Boilerplate phrases shared by ≥3 businesses

