# ICML 2026 Review And Reply Analysis

## Corpus Coverage

| Tab | Submissions | Forums Harvested | Notes | Official Reviews | Author Rebuttals | Reviewer Acknowledgements | Reply Comments | Decisions |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Accept Spotlight | 538 | 538 | 8490 | 2068 | 2065 | 2000 | 1283 | 536 |
| Accept Regular | 5805 | 5805 | 93779 | 22310 | 22206 | 21353 | 16300 | 5805 |
| Reject | 214 | 214 | 3396 | 821 | 793 | 757 | 597 | 214 |

These counts come from OpenReview bulk `parentInvitations` endpoints, grouped back by forum. The corpus covers Official_Review, Rebuttal, Rebuttal_Acknowledgement, Reply_Rebuttal_Comment, Decision, plus the submission note for each enumerated forum.

## Accept Spotlight

### Review Form Fields

- `summary`: 2068
- `strengths_and_weaknesses`: 2068
- `soundness`: 2068
- `presentation`: 2068
- `significance`: 2068
- `originality`: 2068
- `key_questions_for_authors`: 2068
- `limitations`: 2068
- `overall_recommendation`: 2068
- `confidence`: 2068
- `compliance_with_LLM_reviewing_policy`: 2068
- `code_of_conduct_acknowledgement`: 2068
- `final_justification`: 1674
- `ethical_review_concerns`: 44
- `ethics_expertise_needed`: 8
- `ethical_review_flag`: 7

### Recommendation Values

- 5: 1157
- 4: 754
- 6: 95
- 3: 57
- 2: 5

Confidence: count 2068, mean 3.49, median 4.00, min 1, max 5.

### Rebuttal Acknowledgement Values

- fully_resolved: 1594
- partially_resolved: 345
- partially_resolved_or_unresolved: 61

### Common Review Vocabulary

`affirmed` (4137), `model` (3768), `how` (3389), `models` (3371), `training` (2414), `work` (2397), `experiments` (2390), `proposed` (2228), `data` (2205), `performance` (2198), `while` (2089), `learning` (1906), `theoretical` (1902), `framework` (1892), `analysis` (1889), `weaknesses` (1884), `what` (1816), `methods` (1731), `only` (1710), `evaluation` (1654), `main` (1628), `strengths` (1627), `across` (1617), `between` (1584), `well` (1534), `empirical` (1530), `tasks` (1513), `provide` (1508), `problem` (1506), `reasoning` (1460), `section` (1443), `where` (1440), `different` (1412), `when` (1373), `concerns` (1323)

### Common Reply/Rebuttal Vocabulary

`thank` (4818), `model` (4753), `training` (3259), `models` (3014), `work` (2961), `while` (2820), `table` (2751), `across` (2664), `only` (2599), `performance` (2580), `data` (2329), `under` (2135), `experiments` (2126), `both` (2090), `where` (2080), `time` (2045), `agree` (2032), `each` (1981), `same` (1918), `rather` (1892), `below` (1868), `additional` (1861), `setting` (1802), `analysis` (1766), `response` (1763), `different` (1743), `further` (1718), `section` (1700), `methods` (1691), `evaluation` (1677), `learning` (1644), `when` (1637), `feedback` (1620), `appendix` (1616), `text` (1600)

### Top Primary Areas

- deep_learning->large_language_models: 90
- applications->computer_vision: 28
- deep_learning->generative_models_and_autoencoders: 26
- applications->robotics: 18
- applications->chemistry_physics_and_earth_sciences: 18
- general_machine_learning->evaluation: 17
- social_aspects->accountability_transparency_and_interpretability: 16
- theory->learning_theory: 15
- reinforcement_learning: 12
- deep_learning->foundation_models: 11
- reinforcement_learning->deep_rl: 11
- deep_learning->graph_neural_networks: 11
- applications->neuroscience_cognitive_science: 10
- deep_learning->theory: 10
- general_machine_learning->causality: 10

## Accept Regular

### Review Form Fields

- `summary`: 22310
- `strengths_and_weaknesses`: 22310
- `soundness`: 22310
- `presentation`: 22310
- `significance`: 22310
- `originality`: 22310
- `key_questions_for_authors`: 22310
- `limitations`: 22310
- `overall_recommendation`: 22310
- `confidence`: 22310
- `compliance_with_LLM_reviewing_policy`: 22310
- `code_of_conduct_acknowledgement`: 22310
- `final_justification`: 17606
- `ethical_review_concerns`: 582
- `ethical_review_flag`: 123
- `ethics_expertise_needed`: 105

### Recommendation Values

- 4: 12999
- 5: 5709
- 3: 2839
- 2: 496
- 6: 239
- 1: 28

Confidence: count 22310, mean 3.46, median 4.00, min 1, max 5.

### Rebuttal Acknowledgement Values

- fully_resolved: 14012
- partially_resolved: 5561
- partially_resolved_or_unresolved: 1780

### Common Review Vocabulary

`affirmed` (44621), `model` (41023), `how` (36388), `models` (34429), `proposed` (27163), `training` (27135), `performance` (26207), `experiments` (25776), `data` (23149), `framework` (23072), `work` (23015), `while` (22925), `analysis` (22019), `weaknesses` (21067), `methods` (20530), `evaluation` (20255), `learning` (19793), `only` (19545), `across` (19123), `theoretical` (18873), `strengths` (17972), `what` (17780), `problem` (17315), `provide` (17041), `main` (16870), `empirical` (16807), `tasks` (16782), `between` (16632), `different` (15536), `reasoning` (14750), `baselines` (14621), `where` (14579), `score` (14486), `when` (14402), `under` (14241)

### Common Reply/Rebuttal Vocabulary

`thank` (54299), `model` (54196), `training` (37215), `while` (35189), `table` (34961), `performance` (33943), `across` (33505), `models` (32868), `only` (32384), `work` (32373), `under` (28403), `data` (28093), `rather` (25330), `where` (24175), `time` (23994), `both` (23746), `experiments` (23652), `methods` (23462), `agree` (23318), `evaluation` (22976), `further` (22972), `same` (22773), `analysis` (22556), `response` (22138), `additional` (22102), `setting` (22064), `each` (21476), `below` (21458), `different` (20423), `clarify` (20367), `when` (20143), `address` (20010), `text` (19911), `feedback` (19201), `provide` (18648)

### Top Primary Areas

- deep_learning->large_language_models: 1065
- applications->computer_vision: 487
- deep_learning->generative_models_and_autoencoders: 323
- applications->chemistry_physics_and_earth_sciences: 184
- applications->health_medicine: 154
- applications->robotics: 140
- social_aspects->accountability_transparency_and_interpretability: 124
- reinforcement_learning: 109
- theory->learning_theory: 108
- applications->language_speech_and_dialog: 104
- general_machine_learning->evaluation: 104
- deep_learning->graph_neural_networks: 101
- social_aspects->safety: 100
- deep_learning->foundation_models: 98
- applications->everything_else: 93

## Reject

### Review Form Fields

- `summary`: 821
- `strengths_and_weaknesses`: 821
- `soundness`: 821
- `presentation`: 821
- `significance`: 821
- `originality`: 821
- `key_questions_for_authors`: 821
- `limitations`: 821
- `overall_recommendation`: 821
- `confidence`: 821
- `compliance_with_LLM_reviewing_policy`: 821
- `code_of_conduct_acknowledgement`: 821
- `final_justification`: 622
- `ethical_review_concerns`: 23
- `ethical_review_flag`: 7
- `ethics_expertise_needed`: 4

### Recommendation Values

- 4: 337
- 3: 241
- 2: 112
- 5: 105
- 1: 17
- 6: 9

Confidence: count 821, mean 3.49, median 4.00, min 1, max 5.

### Rebuttal Acknowledgement Values

- fully_resolved: 340
- partially_resolved: 266
- partially_resolved_or_unresolved: 151

### Common Review Vocabulary

`affirmed` (1642), `model` (1579), `how` (1382), `models` (1208), `proposed` (970), `performance` (967), `work` (952), `experiments` (950), `training` (942), `only` (893), `analysis` (892), `framework` (864), `while` (855), `weaknesses` (802), `what` (802), `evaluation` (777), `methods` (755), `theoretical` (732), `data` (695), `learning` (693), `strengths` (658), `main` (651), `across` (636), `empirical` (631), `tasks` (629), `provide` (623), `between` (611), `other` (595), `baselines` (591), `problem` (591), `different` (589), `its` (584), `rather` (576), `section` (569), `whether` (559)

### Common Reply/Rebuttal Vocabulary

`model` (1833), `thank` (1766), `work` (1366), `training` (1205), `table` (1190), `while` (1178), `models` (1149), `performance` (1137), `across` (1128), `only` (1126), `agree` (1050), `response` (1005), `methods` (966), `rather` (936), `where` (906), `analysis` (883), `experiments` (880), `data` (876), `under` (872), `both` (866), `time` (852), `evaluation` (847), `same` (826), `each` (804), `section` (795), `additional` (766), `address` (755), `clarify` (754), `further` (735), `provide` (723), `comparison` (716), `text` (715), `different` (714), `learning` (704), `its` (703)

### Top Primary Areas

- deep_learning->large_language_models: 44
- deep_learning->generative_models_and_autoencoders: 20
- applications->health_medicine: 10
- applications->neuroscience_cognitive_science: 7
- applications->chemistry_physics_and_earth_sciences: 7
- reinforcement_learning: 7
- applications->language_speech_and_dialog: 7
- deep_learning->theory: 6
- applications->computer_vision: 6
- optimization->zeroorder_and_blackbox_optimization: 5
- applications->everything_else: 5
- general_machine_learning: 4
- deep_learning->other_representation_learning: 4
- deep_learning->graph_neural_networks: 4
- general_machine_learning->evaluation: 4

## Cross-Corpus Patterns

- Review structure is extremely consistent across tabs: summary, strengths/weaknesses, soundness, presentation, significance, originality, questions, limitations, recommendation, confidence, policy/code acknowledgements, and often final justification.
- Regular and spotlight accepted papers still have many critical reviews; acceptance tends to correlate with concerns becoming bounded, acknowledged, or camera-ready-fixable after rebuttal.
- Reject papers show a heavier lower-score distribution and many `partially_resolved` / unresolved acknowledgement narratives, despite substantial author rebuttal effort.
- Author replies most often follow a point-by-point structure: thank the reviewer, mirror the reviewer label or concern, give evidence, add ablations/tables/links, and promise precise camera-ready changes.
- Reviewer acknowledgements are useful calibration signals: they expose whether rebuttals changed the reviewer position, fully resolved concerns, or left fundamental issues open.
