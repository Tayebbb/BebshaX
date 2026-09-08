# Business-matrix audit (matrix) — 2026-09-08T14:24:55.288094+00:00

**Verdict:** FAIL — 233/264 checks passed, 3 warnings

| Result | Check | Detail |
|---|---|---|
| PASS | POLL: signup |  |
| PASS | POLL: create study |  |
| PASS | POLL: study title is not the canonical fallback | A Network of Low-Cost Air-Quality Sensors Sold |
| PASS | POLL: copilot reply |  |
| PASS | POLL: copilot names its route | ollama/llama3.2:3b |
| PASS | POLL: copilot reply is about the idea | You're developing an air-quality monitoring system for municipalities in northern Italy's Po Valley, providing affordabl |
| PASS | POLL: suggest roles |  |
| PASS | POLL: roles are idea-specific | MUNICIPAL OFFICIAL; RESIDENT PO VALLEY; MUNICIPAL ENGINEER; AIR QUALITY EXPERT; SMALL BUSINESS OWNER PO VALLEY; ENVIRONMENTAL ACTIVIST PO VALLEY; RESIDENT WITH  |
| PASS | POLL: ≥4 distinct roles | 9 roles |
| PASS | POLL: generate personas |  |
| PASS | POLL: at least one persona | 2 personas, 0 failed roles |
| PASS | POLL: persona generation names its routes | ['ollama/llama3.2:3b'] |
| PASS | POLL: personas live in the idea's market (IT) | country_codes=['IT'] |
| PASS | POLL: personas reference the idea's domain |  |
| PASS | POLL: persona created_at is not the prompt's example timestamp | [None, None] |
| PASS | POLL: persona names are distinct | ['Jesús Mancini', 'Alessandra Bianchi'] |
| PASS | POLL: generate script |  |
| PASS | POLL: script source is the model | source='llm' served_by='ollama/llama3.2:3b' |
| PASS | POLL: script has the requested 3 questions | 3 questions |
| PASS | POLL: script is idea-specific | Can you describe your current experience with air quality monitoring in your community, and how often do you check for u |
| PASS | POLL: script questions are distinct |  |
| PASS | POLL: start batch interview |  |
| FAIL | POLL: interview completed | status='failed' completed=0 failed=1 |
| FAIL | POLL: create behavioral pricing test | HTTP 409 error_code='conflict' detail='The request conflicts with existing data (duplicate or referenced record).' |
| FAIL | POLL: generate report | HTTP 503 error_code='all_candidates_failed' detail='No AI route could serve this request — all candidates failed.' |
| FAIL | POLL: AI review | HTTP 503 error_code='all_candidates_failed' detail='No AI route could serve this request — all candidates failed.' |
| PASS | POLL: no Bangladesh/seed default leaked (hard markers) | leaked=[] |
| PASS | POLL: no seed-domain phrasing leaked (soft markers) | leaked=[] |
| PASS | KITCHEN: signup |  |
| PASS | KITCHEN: create study |  |
| PASS | KITCHEN: study title is not the canonical fallback | A Ghost Kitchen in Lagos, Nigeria |
| PASS | KITCHEN: copilot reply |  |
| PASS | KITCHEN: copilot names its route | ollama/llama3.2:3b |
| PASS | KITCHEN: copilot reply is about the idea | So, you're looking to validate the demand for your ghost kitchen's lunch delivery service in Lagos, targeting office wor |
| PASS | KITCHEN: suggest roles |  |
| PASS | KITCHEN: roles are idea-specific | OFFICE WORKER; WhatsApp CHAT OPERATOR; DELIVERY RIDER; PARENT WORKING OFFICE; INFLUENCER IN THE FOOD INDUSTRY; channel PARTNER MANAGER; SKEPTICAL OFFICE WORKER; |
| PASS | KITCHEN: ≥4 distinct roles | 10 roles |
| PASS | KITCHEN: generate personas |  |
| PASS | KITCHEN: at least one persona | 2 personas, 0 failed roles |
| PASS | KITCHEN: persona generation names its routes | ['ollama/llama3.2:3b'] |
| PASS | KITCHEN: personas live in the idea's market (NG) | country_codes=['NG'] |
| PASS | KITCHEN: personas reference the idea's domain |  |
| PASS | KITCHEN: persona created_at is not the prompt's example timestamp | [None, None] |
| PASS | KITCHEN: persona names are distinct | ['Adesina Oluwade', 'Aisha Bello'] |
| PASS | KITCHEN: generate script |  |
| PASS | KITCHEN: script source is the model | source='llm' served_by='ollama/llama3.2:3b' |
| PASS | KITCHEN: script has the requested 3 questions | 3 questions |
| PASS | KITCHEN: script is idea-specific | What do you usually do when you're running late for work and can't get to a restaurant that serves Nigerian home-style l |
| PASS | KITCHEN: script questions are distinct |  |
| PASS | KITCHEN: start batch interview |  |
| FAIL | KITCHEN: interview completed | status='failed' completed=0 failed=1 |
| FAIL | KITCHEN: create behavioral pricing test | HTTP 409 error_code='conflict' detail='The request conflicts with existing data (duplicate or referenced record).' |
| FAIL | KITCHEN: generate report | HTTP 503 error_code='all_candidates_failed' detail='No AI route could serve this request — all candidates failed.' |
| FAIL | KITCHEN: AI review | HTTP 503 error_code='all_candidates_failed' detail='No AI route could serve this request — all candidates failed.' |
| PASS | KITCHEN: no Bangladesh/seed default leaked (hard markers) | leaked=[] |
| PASS | KITCHEN: no seed-domain phrasing leaked (soft markers) | leaked=[] |
| PASS | SAAS: signup |  |
| PASS | SAAS: create study |  |
| PASS | SAAS: study title is not the canonical fallback | A Compliance-Automation SaaS for Mid-Sized German |
| PASS | SAAS: copilot reply |  |
| PASS | SAAS: copilot names its route | ollama/llama3.2:3b |
| PASS | SAAS: copilot reply is about the idea | You're developing a SaaS to help mid-sized German manufacturers comply with EU CSRD sustainability reporting requirement |
| PASS | SAAS: suggest roles |  |
| PASS | SAAS: roles are idea-specific | MANAGER OF OPERATIONS; SUSTAINABILITY OFFICER FOR MANUFACTURING; COMPLIANCE SPECIALIST FOR MANUFACTURING; CHANNEL PARTNER FOR ERP SYSTEMS; MANUFACTURING INFLUEN |
| PASS | SAAS: ≥4 distinct roles | 10 roles |
| PASS | SAAS: generate personas |  |
| PASS | SAAS: at least one persona | 2 personas, 0 failed roles |
| PASS | SAAS: persona generation names its routes | ['ollama/llama3.2:3b'] |
| PASS | SAAS: personas live in the idea's market (DE) | country_codes=['DE'] |
| PASS | SAAS: personas reference the idea's domain |  |
| PASS | SAAS: persona created_at is not the prompt's example timestamp | [None, None] |
| PASS | SAAS: persona names are distinct | ['Dorothea Meyer', 'Anna Weber'] |
| FAIL | SAAS: generate script | HTTP 502 error_code='script_unparseable' detail="The model's reply could not be turned into interview questions after 2 attempts; no template was substituted. Please try again." |
| FAIL | SAAS: create behavioral pricing test | HTTP 409 error_code='conflict' detail='The request conflicts with existing data (duplicate or referenced record).' |
| FAIL | SAAS: generate report | HTTP 503 error_code='all_candidates_failed' detail='No AI route could serve this request — all candidates failed.' |
| FAIL | SAAS: AI review | HTTP 503 error_code='all_candidates_failed' detail='No AI route could serve this request — all candidates failed.' |
| PASS | SAAS: no Bangladesh/seed default leaked (hard markers) | leaked=[] |
| PASS | SAAS: no seed-domain phrasing leaked (soft markers) | leaked=[] |
| PASS | SAVINGS: signup |  |
| PASS | SAVINGS: create study |  |
| PASS | SAVINGS: study title is not the canonical fallback | A Micro-Savings App for Motorbike Ride-Hailing Drivers |
| PASS | SAVINGS: copilot reply |  |
| PASS | SAVINGS: copilot names its route | ollama/llama3.2:3b |
| PASS | SAVINGS: copilot reply is about the idea | You're developing a micro-savings app specifically designed for motorbike ride-hailing drivers in Jakarta, aiming to hel |
| PASS | SAVINGS: suggest roles |  |
| PASS | SAVINGS: roles are idea-specific | MOTORBIKE RIDER; JAKARTA RESIDENT; RIDE-HAILING DRIVER; INSURANCE PROVIDER; FINANCIAL INSTITUTION; CHANNEL PARTNER; MOTORCYCLE MANUFACTURER; WEEKEND WARRIOR; TR |
| PASS | SAVINGS: ≥4 distinct roles | 9 roles |
| PASS | SAVINGS: generate personas |  |
| PASS | SAVINGS: at least one persona | 2 personas, 0 failed roles |
| PASS | SAVINGS: persona generation names its routes | ['ollama/llama3.2:3b'] |
| PASS | SAVINGS: personas live in the idea's market (ID) | country_codes=['ID'] |
| PASS | SAVINGS: personas reference the idea's domain |  |
| PASS | SAVINGS: persona created_at is not the prompt's example timestamp | [None, None] |
| PASS | SAVINGS: persona names are distinct | ['Joan Puspita Utari', 'Jayanti Widyati'] |
| PASS | SAVINGS: generate script |  |
| PASS | SAVINGS: script source is the model | source='llm' served_by='ollama/llama3.2:3b' |
| PASS | SAVINGS: script has the requested 3 questions | 3 questions |
| PASS | SAVINGS: script is idea-specific | Can you walk me through your typical day as a motorbike ride-hailing driver in Jakarta, including how you currently save |
| PASS | SAVINGS: script questions are distinct |  |
| PASS | SAVINGS: start batch interview |  |
| FAIL | SAVINGS: interview completed | status='failed' completed=0 failed=1 |
| FAIL | SAVINGS: create behavioral pricing test | HTTP 409 error_code='conflict' detail='The request conflicts with existing data (duplicate or referenced record).' |
| FAIL | SAVINGS: generate report | HTTP 500 error_code='internal_error' detail='Internal server error' |
| PASS | SAVINGS: AI review |  |
| PASS | SAVINGS: review carries dimension scores | {'grounding': 0, 'specificity': 0, 'consistency': 0, 'honesty': 0, 'actionability': 0} |
| PASS | SAVINGS: review names its route | ollama/llama3.2:3b |
| PASS | SAVINGS: review is about this study | The personas lack specificity and grounding in the study brief. They do not clearly articulate the target audience's pai |
| PASS | SAVINGS: no Bangladesh/seed default leaked (hard markers) | leaked=[] |
| WARN | SAVINGS: no seed-domain phrasing leaked (soft markers) | leaked=['exam'] |
| PASS | DERM: signup |  |
| PASS | DERM: create study |  |
| PASS | DERM: study title is not the canonical fallback | A Tele-Dermatology Service for Rural Clinics in Kenya |
| PASS | DERM: copilot reply |  |
| PASS | DERM: copilot names its route | ollama/llama3.2:3b |
| FAIL | DERM: copilot reply is about the idea | Conversational explanation and question to display to the user |
| PASS | DERM: suggest roles |  |
| PASS | DERM: roles are idea-specific | RURAL CLINIC NURSE; RURAL CLINIC MANAGER; HEALTH INSURANCE PAYER; TECH-SAVVY RURAL RESIDENT; RURAL CLINIC PATIENT; HEALTH INFORMATION EXCHANGE INFLUENCER; TELE- |
| PASS | DERM: ≥4 distinct roles | 10 roles |
| PASS | DERM: generate personas |  |
| PASS | DERM: at least one persona | 2 personas, 0 failed roles |
| PASS | DERM: persona generation names its routes | ['ollama/llama3.2:3b'] |
| PASS | DERM: personas live in the idea's market (KE) | country_codes=['KE'] |
| PASS | DERM: personas reference the idea's domain |  |
| PASS | DERM: persona created_at is not the prompt's example timestamp | [None, None] |
| PASS | DERM: persona names are distinct | ['Kamru Wanjiru', 'Joan Kamau'] |
| FAIL | DERM: generate script | HTTP 502 error_code='script_unparseable' detail="The model's reply could not be turned into interview questions after 2 attempts; no template was substituted. Please try again." |
| FAIL | DERM: create behavioral pricing test | HTTP 409 error_code='conflict' detail='The request conflicts with existing data (duplicate or referenced record).' |
| FAIL | DERM: generate report | HTTP 500 error_code='internal_error' detail='Internal server error' |
| PASS | DERM: AI review |  |
| PASS | DERM: review carries dimension scores | {'grounding': 0, 'specificity': 0, 'consistency': 0, 'honesty': 0, 'actionability': 0} |
| PASS | DERM: review names its route | ollama/llama3.2:3b |
| FAIL | DERM: review is about this study | The personas lack grounding in the study brief, specificity to the idea, consistency with each other, honesty about limi |
| PASS | DERM: no Bangladesh/seed default leaked (hard markers) | leaked=[] |
| PASS | DERM: no seed-domain phrasing leaked (soft markers) | leaked=[] |
| PASS | KETTLE: signup |  |
| PASS | KETTLE: create study |  |
| PASS | KETTLE: study title is not the canonical fallback | A Modular, Fully Repairable Electric Kettle Sold |
| PASS | KETTLE: copilot reply |  |
| PASS | KETTLE: copilot names its route | ollama/llama3.2:3b |
| PASS | KETTLE: copilot reply is about the idea | You're considering a modular, fully repairable electric kettle with a 10-year parts guarantee and mail-in element replac |
| PASS | KETTLE: suggest roles |  |
| PASS | KETTLE: roles are idea-specific | ACTIVE YOUNG PROFESSIONAL; SUSAN CRITICALLY CONSCIOUS; BUSINESS OWNER WITH SUSTAINABILITY OBLIGATIONS; DIY ENTHUSIAST WITH ELECTRONIC SKILLS; ENVIRONMENTAL ACTI |
| PASS | KETTLE: ≥4 distinct roles | 10 roles |
| PASS | KETTLE: generate personas |  |
| PASS | KETTLE: at least one persona | 2 personas, 0 failed roles |
| PASS | KETTLE: persona generation names its routes | ['ollama/llama3.2:3b'] |
| PASS | KETTLE: personas live in the idea's market (GB/UK) | country_codes=['GB'] |
| PASS | KETTLE: personas reference the idea's domain |  |
| PASS | KETTLE: persona created_at is not the prompt's example timestamp | [None, None] |
| PASS | KETTLE: persona names are distinct | ['Lily Brown', 'Lily Patel'] |
| PASS | KETTLE: generate script |  |
| PASS | KETTLE: script source is the model | source='llm' served_by='ollama/llama3.2:3b' |
| PASS | KETTLE: script has the requested 3 questions | 3 questions |
| PASS | KETTLE: script is idea-specific | What is your current go-to method for replacing worn-out elements in your electric kettle, and how often do you need to  |
| PASS | KETTLE: script questions are distinct |  |
| PASS | KETTLE: start batch interview |  |
| FAIL | KETTLE: interview completed | status='failed' completed=0 failed=1 |
| FAIL | KETTLE: create behavioral pricing test | HTTP 409 error_code='conflict' detail='The request conflicts with existing data (duplicate or referenced record).' |
| FAIL | KETTLE: generate report | HTTP 502 error_code='report_synthesis_failed' detail="The model's report reply could not be used after 2 attempts; no template report was written." |
| PASS | KETTLE: AI review |  |
| PASS | KETTLE: review carries dimension scores | {'grounding': 0, 'specificity': 0, 'consistency': 0, 'honesty': 0, 'actionability': 0} |
| PASS | KETTLE: review names its route | ollama/llama3.2:3b |
| FAIL | KETTLE: review is about this study | The study brief, target audience, and personas are unclear. Without concrete evidence claims, pain points, and willingne |
| PASS | KETTLE: no Bangladesh/seed default leaked (hard markers) | leaked=[] |
| WARN | KETTLE: no seed-domain phrasing leaked (soft markers) | leaked=['exam'] |
| PASS | TUITION: signup |  |
| PASS | TUITION: create study |  |
| PASS | TUITION: study title is not the canonical fallback | A Bkash-Integrated Tuition-Fee Installment Plan |
| PASS | TUITION: copilot reply |  |
| PASS | TUITION: copilot names its route | ollama/llama3.2:3b |
| PASS | TUITION: copilot reply is about the idea | You're exploring a financing solution for private university students in Chattogram, Bangladesh. To validate your idea,  |
| PASS | TUITION: suggest roles |  |
| PASS | TUITION: roles are idea-specific | PARENT CAREGIVER; PRIVATE UNIVERSITY STUDENT; FAMILY FINANCE MANAGER; PRIVATE UNIVERSITY ADMINISTRATOR; BANK REPRESENTATIVE (bKASH); INFLUENCER (MOM BLOGGERS OR |
| PASS | TUITION: ≥4 distinct roles | 8 roles |
| PASS | TUITION: generate personas |  |
| PASS | TUITION: at least one persona | 2 personas, 0 failed roles |
| PASS | TUITION: persona generation names its routes | ['ollama/llama3.2:3b'] |
| PASS | TUITION: personas live in the idea's market (BD) | country_codes=['BD'] |
| PASS | TUITION: personas reference the idea's domain |  |
| PASS | TUITION: persona created_at is not the prompt's example timestamp | [None, None] |
| PASS | TUITION: persona names are distinct | ['Rashida Begum', 'Nur Parveen Rashid'] |
| PASS | TUITION: generate script |  |
| PASS | TUITION: script source is the model | source='llm' served_by='ollama/llama3.2:3b' |
| PASS | TUITION: script has the requested 3 questions | 3 questions |
| PASS | TUITION: script is idea-specific | Can you describe your current process of paying tuition fees for your child's private university education in Chattogram |
| PASS | TUITION: script questions are distinct |  |
| PASS | TUITION: start batch interview |  |
| FAIL | TUITION: interview completed | status='failed' completed=0 failed=1 |
| FAIL | TUITION: create behavioral pricing test | HTTP 409 error_code='conflict' detail='The request conflicts with existing data (duplicate or referenced record).' |
| FAIL | TUITION: generate report | HTTP 500 error_code='internal_error' detail='Internal server error' |
| PASS | TUITION: AI review |  |
| PASS | TUITION: review carries dimension scores | {'grounding': 0, 'specificity': 0, 'consistency': 0, 'honesty': 0, 'actionability': 0} |
| PASS | TUITION: review names its route | ollama/llama3.2:3b |
| FAIL | TUITION: review is about this study | The artefacts lack grounding, specificity, consistency, honesty, and actionability. The personas are missing, and there  |
| WARN | TUITION: no seed-domain phrasing leaked (soft markers) | leaked=['semester'] |
| PASS | ELDER: signup |  |
| PASS | ELDER: create study |  |
| PASS | ELDER: study title is not the canonical fallback | A Vetted Home-Care Companion Marketplace for Elderly |
| PASS | ELDER: copilot reply |  |
| PASS | ELDER: copilot names its route | ollama/llama3.2:3b |
| PASS | ELDER: copilot reply is about the idea | I've heard you're creating a vetted home-care companion marketplace for elderly residents of Osaka, Japan, booked and pa |
| PASS | ELDER: suggest roles |  |
| PASS | ELDER: roles are idea-specific | BUSINESS OWNER; ELDERLY CAREGIVER; HEALTHCARE PROFESSIONAL; PAYER (INSURANCE COMPANY); channel PARTNER (AGENCY); EDGE CASE (UNABLE TO CARE FOR ELDERLY); POWER U |
| PASS | ELDER: ≥4 distinct roles | 10 roles |
| PASS | ELDER: generate personas |  |
| PASS | ELDER: at least one persona | 2 personas, 0 failed roles |
| PASS | ELDER: persona generation names its routes | ['kilo/openrouter/free'] |
| PASS | ELDER: personas live in the idea's market (JP) | country_codes=['JP'] |
| PASS | ELDER: personas reference the idea's domain |  |
| PASS | ELDER: persona created_at is not the prompt's example timestamp | [None, None] |
| PASS | ELDER: persona names are distinct | ['Takumi Yamamoto', 'Yuki Suzuki'] |
| PASS | ELDER: generate script |  |
| PASS | ELDER: script source is the model | source='llm' served_by='ollama/llama3.2:3b' |
| PASS | ELDER: script has the requested 3 questions | 3 questions |
| PASS | ELDER: script is idea-specific | How do you currently find and book home-care services for your elderly relatives when living far away from them? |
| PASS | ELDER: script questions are distinct |  |
| PASS | ELDER: start batch interview |  |
| PASS | ELDER: interview completed | status='completed' completed=1 failed=0 |
| PASS | ELDER: interview answers are on-topic | 3 persona turns |
| PASS | ELDER: interview has one answer per question | 3 answers / 3 questions |
| PASS | ELDER: interview answers are distinct |  |
| PASS | ELDER: persona speaks in first person | 3/3 answers use first person |
| PASS | ELDER: persona does not narrate itself in third person |  |
| FAIL | ELDER: create behavioral pricing test | HTTP 409 error_code='conflict' detail='The request conflicts with existing data (duplicate or referenced record).' |
| PASS | ELDER: generate report |  |
| PASS | ELDER: report synthesis is model-written | synthesis_source='llm' served_by='llm7/codestral-latest' |
| PASS | ELDER: report summary is idea-specific | The study validates the demand for a vetted home-care companion marketplace targeting elderly residents of Osaka, Japan, with adult children |
| PASS | ELDER: recommendations are idea-specific | ["develop a robust verification process for caregivers", "build a trusted platform with a focus on personal connections and word-of-mouth re |
| PASS | ELDER: report does not claim real-user validation |  |
| PASS | ELDER: AI review |  |
| PASS | ELDER: review carries dimension scores | {'grounding': 100, 'specificity': 80, 'consistency': 70, 'honesty': 90, 'actionability': 50} |
| PASS | ELDER: review names its route | ollama/llama3.2:3b |
| PASS | ELDER: review is about this study | The study provides a solid foundation for understanding the demand for a vetted home-care companion marketplace targetin |
| PASS | ELDER: no Bangladesh/seed default leaked (hard markers) | leaked=[] |
| PASS | ELDER: no seed-domain phrasing leaked (soft markers) | leaked=[] |
| PASS | matrix: copilot_reply differs across businesses (max pair jaccard 0.17 = POLL/TUITION, mean 0.05, threshold 0.35) |  |
| PASS | matrix: no two businesses got an identical copilot_reply | [] |
| PASS | matrix: roles differs across businesses (max pair jaccard 0.14 = KITCHEN/ELDER, mean 0.07, threshold 0.3) |  |
| PASS | matrix: no two businesses got an identical roles | [] |
| PASS | matrix: persona_descriptions differs across businesses (max pair jaccard 0.15 = SAVINGS/TUITION, mean 0.05, threshold 0.35) |  |
| PASS | matrix: no two businesses got an identical persona_descriptions | [] |
| PASS | matrix: persona_attributes differs across businesses (max pair jaccard 0.13 = SAVINGS/TUITION, mean 0.07, threshold 0.35) |  |
| PASS | matrix: no two businesses got an identical persona_attributes | [] |
| PASS | matrix: script differs across businesses (max pair jaccard 0.07 = POLL/KETTLE, mean 0.04, threshold 0.3) |  |
| PASS | matrix: no two businesses got an identical script | [] |
| PASS | matrix: ai_review differs across businesses (max pair jaccard 0.45 = DERM/TUITION, mean 0.20, threshold 0.45) |  |
| PASS | matrix: no two businesses got an identical ai_review | [] |
| PASS | matrix: no boilerplate 6-grams repeated across ≥3 businesses in copilot_reply |  |
| PASS | matrix: no boilerplate 6-grams repeated across ≥3 businesses in roles |  |
| PASS | matrix: no boilerplate 6-grams repeated across ≥3 businesses in persona_descriptions |  |
| PASS | matrix: no boilerplate 6-grams repeated across ≥3 businesses in persona_attributes |  |
| FAIL | matrix: no boilerplate 6-grams repeated across ≥3 businesses in script | would you be willing to pay (1 phrases) |
| PASS | matrix: no boilerplate 6-grams repeated across ≥3 businesses in interview_answers |  |
| PASS | matrix: no boilerplate 6-grams repeated across ≥3 businesses in behavioral_rationale |  |
| PASS | matrix: no boilerplate 6-grams repeated across ≥3 businesses in report_summary |  |
| PASS | matrix: no boilerplate 6-grams repeated across ≥3 businesses in report_findings |  |
| PASS | matrix: no boilerplate 6-grams repeated across ≥3 businesses in report_recommendations |  |
| PASS | matrix: no boilerplate 6-grams repeated across ≥3 businesses in ai_review |  |
| PASS | matrix: no persona name is reused across businesses | {} |
| FAIL | matrix: no business's distinctive vocabulary leaked into another's artefacts | [{'in': 'SAVINGS', 'from': 'SAAS', 'terms': ['manufacturer']}, {'in': 'ELDER', 'from': 'DERM', 'terms': ['nurse']}] |
| PASS | matrix: pollution vs food business share no role names | set() |
| PASS | matrix: pollution vs food business share no persona occupations | set() |
| PASS | matrix: no role name appears in EVERY business (would be a fixed list) | set() |
| PASS | matrix: AI review scores are not one constant | [0, 20, 0, 20, 60] |

## Structure per business

| Business | roles | findings | recs | review | routes |
|---|---|---|---|---|---|
| POLL | 9 | 0 | 0 | None | {'copilot': 'ollama/llama3.2:3b', 'personas': ['ollama/llama3.2:3b'], 'script': 'ollama/llama3.2:3b'} |
| KITCHEN | 10 | 0 | 0 | None | {'copilot': 'ollama/llama3.2:3b', 'personas': ['ollama/llama3.2:3b'], 'script': 'ollama/llama3.2:3b'} |
| SAAS | 10 | 0 | 0 | None | {'copilot': 'ollama/llama3.2:3b', 'personas': ['ollama/llama3.2:3b']} |
| SAVINGS | 9 | 0 | 0 | 0 | {'copilot': 'ollama/llama3.2:3b', 'personas': ['ollama/llama3.2:3b'], 'script': 'ollama/llama3.2:3b', 'ai_review': 'olla |
| DERM | 10 | 0 | 0 | 20 | {'copilot': 'ollama/llama3.2:3b', 'personas': ['ollama/llama3.2:3b'], 'ai_review': 'ollama/llama3.2:3b'} |
| KETTLE | 10 | 0 | 0 | 0 | {'copilot': 'ollama/llama3.2:3b', 'personas': ['ollama/llama3.2:3b'], 'script': 'ollama/llama3.2:3b', 'ai_review': 'olla |
| TUITION | 8 | 0 | 0 | 20 | {'copilot': 'ollama/llama3.2:3b', 'personas': ['ollama/llama3.2:3b'], 'script': 'ollama/llama3.2:3b', 'ai_review': 'olla |
| ELDER | 10 | 3 | 3 | 60 | {'copilot': 'ollama/llama3.2:3b', 'personas': ['kilo/openrouter/free'], 'script': 'ollama/llama3.2:3b', 'interview': ['o |

## Boilerplate phrases shared by ≥3 businesses

**script**
- “would you be willing to pay” — ELDER, KETTLE, KITCHEN, POLL, SAVINGS
