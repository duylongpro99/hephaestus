# What a good episode does

- It opens with a hook that makes the listener want to hear the story.
- It teaches the spec's target words and grammar point through a small, concrete story the
  learner can picture, then explains them simply, then lets the learner hear the story again.
- Every target word is used naturally at least the minimum number of times in the band
  (`target_repetition_min`), counted across all spoken lines including the replay.
- It reuses the spec's review words where they fit.
- It ends with a short quiz and an interaction prompt that invites a comment.

# Format: slow_dialogue_explain_replay

Use these segments in this order. Segment ids are `s1`, `s2`, ...; line ids are the segment
id plus `l1`, `l2`, ... (for example `s2l3`); quiz item ids are the segment id plus `q1`, ...

1. `hook` (speed `natural`): the host greets the listener and sets up the story in 2-4 lines.
2. `dialogue` (speed `slow`): a 2-person scene from the cast, 14-24 lines, that uses the
   target words and the grammar point naturally.
3. `explanation` (speed `slow`): the host explains each target word with a simple example
   and explains the grammar point with 2-3 examples. Speak to the listener directly.
4. `replay` (speed `natural`): the same dialogue again, line for line, with the same text.
5. `quiz` (speed `slow`): the host asks 3 questions about the story. Each question is a
   spoken line followed by a pause, and also a quiz item with 2-3 options.
6. `outro` (speed `natural`): a short goodbye with the interaction prompt.
