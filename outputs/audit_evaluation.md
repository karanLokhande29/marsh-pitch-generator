# Audit evaluation - planted hallucinations (LLM + deterministic mode)

Clean deck: **PASS** (score 100.0, 42/42 policy claims supported, 0 false alarms expected)

Deck with 8 planted errors: **FAIL** (score 87.0)

**Detection rate: 8/8**

| # | Error type | Planted claim | Verdict | Flags | Caught |
|---|---|---|---|---|---|
| 1 | Exclusion stated as benefit | HDFC ERGO Optima Secure+ covers maternity expenses as a standard benefit. | CONTRADICTED | OPTIONAL_PRESENTED_AS_STANDARD, CONFLICTS_WITH_EXCLUSION | Yes |
| 2 | Condition dropped | Care Supreme covers road ambulance up to 100% of sum insured. | PARTIAL | CONDITION_OMITTED | Yes |
| 3 | Wrong figure | Optima Secure+ covers 60 days pre- and 90 days post-hospitalisation. | CONTRADICTED | NUMBER_MISMATCH | Yes |
| 4 | Wrong insurer | Niva Bupa ReAssure 2.0 grows the sum insured to 6X base by year 6 via Super Credit. | UNSUPPORTED | NUMBER_MISMATCH | Yes |
| 5 | Optional shown as standard | Care Supreme includes Claim Shield covering 68 listed non-payable items. | PARTIAL | OPTIONAL_PRESENTED_AS_STANDARD | Yes |
| 6 | Plan-specific shown as general | Activ One provides global cover for emergency and planned treatment abroad. | PARTIAL | PLAN_CONDITION_OMITTED | Yes |
| 7 | Fabricated benefit | Optima Secure+ gives every employee a free annual gym membership and dental cover. | UNSUPPORTED | - | Yes |
| 8 | Wrong limit | Niva Bupa ReAssure 2.0 covers air ambulance up to INR 5,00,000 per hospitalisation. | CONTRADICTED | NUMBER_MISMATCH | Yes |
