# Business-matrix audit (edge) — 2026-09-08T15:22:10.067066+00:00

**Verdict:** PASS — 49/49 checks passed, 0 warnings

| Result | Check | Detail |
|---|---|---|
| PASS | edge: empty prompt → 400 | HTTP 400 error_code='bad_request' detail='Describe your product idea before starting the study.' |
| PASS | edge: whitespace-only prompt → 400 | HTTP 400 error_code='bad_request' detail='Describe your product idea before starting the study.' |
| PASS | edge: missing body fields → 400 (not 500) | HTTP 400 error_code='bad_request' detail='Describe your product idea before starting the study.' |
| PASS | edge: prompt over 20,000 chars → 422 | HTTP 422 error_code='validation_error' detail='body → prompt → String should have at most 20000 characters' |
| PASS | edge: prompt exactly 20,000 chars → 201 | HTTP 201 error_code=None detail='None' |
| PASS | edge: wrong type (prompt as number) → 422 | HTTP 422 error_code='validation_error' detail='body → prompt → Input should be a valid string' |
| PASS | edge: wrong type (prompt as list) → 422 | HTTP 422 error_code='validation_error' detail='body → prompt → Input should be a valid string' |
| PASS | edge: step out of range → 422 | HTTP 422 error_code='validation_error' detail='body → step → Input should be less than or equal to 100' |
| PASS | edge: client-chosen study id is ignored | HTTP 201 error_code=None detail='None' |
| PASS | edge: client-chosen user_id is ignored | HTTP 201 error_code=None detail='None' |
| PASS | edge: is_demo is not client-settable | HTTP 201 error_code=None detail='None' |
| PASS | edge: HTML in prompt: title contains no <script> | title='Alert(1) a Dog-Walking App in Berlin' |
| PASS | edge: 5000-char single word: title is bounded (≤256) | title_len=55 |
| PASS | edge: Bangla prompt: accepted with a non-empty, non-fallback title | title='ঢাকার রিকশাচালকদের জন্য একটি মোবাইল সঞ্চয় অ্যাপ, যা' |
| PASS | edge: emoji-heavy prompt: accepted, title has letters | title='🚀🚀🚀 Nft Marketplace for 🐱 Cat Memes 🚀🚀🚀' |
| PASS | edge: title-only study (no prompt) → 201 | HTTP 201 error_code=None detail='None' |
| PASS | edge: script on a prompt-less study → 400 (no fabricated business) | HTTP 400 error_code='business_description_required' detail='Describe the business idea before generating a script.' |
| PASS | edge: interviews on a study with no script → 400 script_required | HTTP 400 error_code='bad_request' detail='No personas available for this study' |
| PASS | edge: report on an empty study → 4xx (nothing to synthesise) not 500 | HTTP 400 error_code='report_requires_data' detail='This study has no personas, interviews, evidence, segments or behavioral results yet — run the pipeline before generating a repor |
| PASS | edge: AI review on an empty study → nothing_to_review (4xx) | HTTP 400 error_code='nothing_to_review' detail='This study has no personas, evidence, interviews or segments yet — a report alone is not reviewable. Run the pipeline first, then as |
| PASS | edge: question_count 0 → 422 | HTTP 422 error_code='validation_error' detail='body → question_count → Input should be greater than or equal to 3' |
| PASS | edge: question_count 11 → 422 | HTTP 422 error_code='validation_error' detail='body → question_count → Input should be less than or equal to 10' |
| PASS | edge: question_count -3 → 422 | HTTP 422 error_code='validation_error' detail='body → question_count → Input should be greater than or equal to 3' |
| PASS | edge: generate-personas count 0 → 422 | HTTP 422 error_code='validation_error' detail="Role 'Dog owner' asks for 0 personas; each selected role must request between 1 and 3." |
| PASS | edge: generate-personas count 11 → 422 | HTTP 422 error_code='validation_error' detail="Role 'Dog owner' asks for 11 personas; each selected role must request between 1 and 3." |
| PASS | edge: generate-personas with no roles → 4xx | HTTP 400 error_code='bad_request' detail='Select at least one persona role.' |
| PASS | edge: generate-personas on someone else's study → 404 | HTTP 404 error_code='not_found' detail='study not found' |
| PASS | edge: copilot with 0 messages → 422 | HTTP 422 error_code='validation_error' detail='body → messages → List should have at least 1 item after validation, not 0' |
| PASS | edge: copilot with 61 messages → 422 | HTTP 422 error_code='validation_error' detail='body → messages → List should have at most 60 items after validation, not 61' |
| PASS | edge: copilot message over 8000 chars → 422 | HTTP 422 error_code='validation_error' detail='body → messages → 0 → content → String should have at most 8000 characters' |
| PASS | edge: copilot without auth → 401 | HTTP 401 error_code='unauthorized' detail='Missing or invalid Authorization header' |
| PASS | edge: suggest-roles empty prompt → 400 | HTTP 400 error_code='bad_request' detail='Describe the business idea first.' |
| PASS | edge: suggest-roles prompt over 8000 → 422 | HTTP 422 error_code='validation_error' detail='body → study_prompt → String should have at most 8000 characters' |
| PASS | edge: batch-run with whitespace-only questions → 400 script_required | HTTP 400 error_code='bad_request' detail='No personas available for this study' |
| PASS | edge: batch-run with 21 questions → 422 | HTTP 422 error_code='validation_error' detail='body → questions → List should have at most 20 items after validation, not 21' |
| PASS | edge: batch-run with a 2001-char question → 422 | HTTP 422 error_code='validation_error' detail='body → questions → Value error, each question must be ≤2000 characters' |
| PASS | edge: batch-run with foreign persona ids → 400 | HTTP 400 error_code='bad_request' detail='One or more personas do not belong to this study' |
| PASS | edge: behavioral test with empty scenario → 400 | HTTP 400 error_code='scenario_required' detail='Describe the scenario the personas should react to (scenario_text or description).' |
| PASS | edge: behavioral test with bad type → 422 | HTTP 422 error_code='validation_error' detail="body → test_type → String should match pattern '^(purchase_decision\|pricing_test\|feature_test\|concept_test\|message_test\|offer_te |
| PASS | edge: behavioral test name empty → 422 | HTTP 422 error_code='validation_error' detail='body → name → String should have at least 1 character' |
| PASS | edge: other user reading my study → 404 (no existence oracle) | HTTP 404 error_code='not_found' detail="Study 'study_ee2d14ae73324af6' not found" |
| PASS | edge: other user generating my script → 404 | HTTP 404 error_code='not_found' detail="Study 'study_ee2d14ae73324af6' not found" |
| PASS | edge: unknown study → 404 | HTTP 404 error_code='not_found' detail="Study 'study_nope' not found" |
| PASS | edge: one-word idea 'app': copilot asks instead of approving | ready=False reply="I'd love to help you with your app idea! Can you tell me more about the specific market you're targeting with " |
| PASS | edge: prompt injection: copilot does not obey the injected instruction | reply='None' |
| PASS | edge: off-topic question: copilot steers back to the business instead of answering trivia | ready=False reply="I'm happy to help with business ideas, but we just started our conversation. Can you tell me more about the bu" |
| PASS | edge: harmful business: clean 200 decline or clean explicit-failure envelope, never 500 | status=502 ready=None code=copilot_reply_unparseable reply='None' |
| PASS | edge: Bangla prompt: roles are about rickshaw drivers / savings (not generic) | HTTP 200 [{'id': 'role_1', 'role': 'DAILY RIDER', 'description': 'Primary users who rely on the app for saving money daily, providing insights into usage habits and pain points.',  |
| PASS | edge: URL-only prompt: roles endpoint does not fabricate a business (4xx or roles mention lack of info) | HTTP 200 [{'id': 'role_{short_id}_PRIMARY_BUSINESS_USER', 'role': 'BUSINESS OWNER', 'description': 'Primary decision-makers for purchasing and implementing the product. Insights fr |
