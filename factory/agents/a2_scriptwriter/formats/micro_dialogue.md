# What a good clip does

- It is one tiny everyday moment the learner can picture, heard in 10-15 seconds.
- It uses the spec's target word naturally, at least `target_repetition_min` times, and the
  grammar point once if it fits. Review words are welcome where they fit.
- It has no hook, explanation, replay, quiz or outro. The vocabulary gloss on screen does the
  teaching.

# Format: micro_dialogue

Use exactly one segment. Its id is `s1`; line ids are `s1l1`, `s1l2`, ...

1. `dialogue` (speed `natural`): 2-4 short lines between two cast members. Use
   `pause_after_ms` of 300-800 on every line.

Put the target word in `vocab` with `is_target: true`. `grammar_notes` holds one short note;
`interaction_prompts` holds one question for the comments.
