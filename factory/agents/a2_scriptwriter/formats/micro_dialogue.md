# What a good clip does

- It is one tiny everyday moment the learner can picture, heard in 10-15 seconds.
- It shows the spec's theme: a clip about a surprise party has a surprise or a party in it.
- It uses the spec's target word naturally, at least `target_repetition_min` times, and the
  grammar point once if it fits. It uses every review word at least once.
- It has no hook, explanation, replay, quiz or outro. The vocabulary gloss on screen does the
  teaching.

# Format: micro_dialogue

Use exactly one segment. Its id is `s1`; line ids are `s1l1`, `s1l2`, ...

1. `dialogue` (speed `natural`): 2-4 short lines between two cast members. Use
   `pause_after_ms` of 300-800 on every line.

Before writing, decide the exchange: an opening line (a question or a news item), a reply that
answers it directly, and an optional reaction. Every line must follow from the one before:
"Yes" or "No" only answers a yes/no question, an answer answers the question that was asked,
and a thing keeps its name (a flat stays a flat, not a house).

Put the target word in `vocab` with `is_target: true`. `grammar_notes` holds one short note;
`interaction_prompts` holds one question for the comments.
